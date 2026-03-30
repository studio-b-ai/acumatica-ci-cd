using System;
using System.Collections.Generic;
using PX.Data;
using PX.Objects.IN;

namespace Aesthetik.WMS
{
    /// <summary>
    /// Emergency CustomizationPlugin: Restore missing INUnit self-reference records.
    ///
    /// ROOT CAUSE — 2026-03-29 P0 outage:
    ///   The UomRenamePieceToYds migration updated InventoryItem.BaseUnit from PIECE→YDS
    ///   but wiped all item-level INUnit records (UnitType=1). Without a BaseUnit→BaseUnit
    ///   self-reference in INUnit, Acumatica fires INUnitAttribute.UnitVerifying(unit=null)
    ///   on every Sales Order line, blocking all order entry and modification.
    ///
    /// FIX:
    ///   For every active InventoryItem, insert missing INUnit records:
    ///     1. BaseUnit→BaseUnit (self-reference, Rate=1.0, MultiDiv=M) — required for all UOM validation
    ///     2. SalesUnit→BaseUnit (if SalesUnit ≠ BaseUnit, e.g. IN→YDS at Rate=36)
    ///     3. PurchaseUnit→BaseUnit (if PurchaseUnit ≠ BaseUnit and ≠ SalesUnit)
    ///
    /// IDEMPOTENT: Checks PXDatabase.Exists before every insert. Safe to re-publish.
    ///
    /// SEE: memory/context/aar-2026-03-29-uom-migration-outage.md
    /// </summary>
    public class UomUnitConversionRestore : CustomizationPlugin
    {
        // Known conversion rates (FromUnit → ToUnit = Rate with MultiDiv=M)
        // Source: INUnit.xml from 2026-03-23 database snapshot (pre-outage)
        // For any unknown pair the plugin logs a warning and skips (safe — does NOT default 1.0
        // for unknown conversions, because a wrong rate is worse than a missing record).
        private static readonly Dictionary<(string from, string to), decimal> KnownRates =
            new Dictionary<(string from, string to), decimal>
            {
                { ("YDS",   "YDS"),   1.0m  },
                { ("EA",    "EA"),    1.0m  },
                { ("IN",    "IN"),    1.0m  },
                { ("CUT",   "CUT"),   1.0m  },
                { ("PIECE", "PIECE"), 1.0m  },
                { ("FT",    "FT"),    1.0m  },
                { ("LBS",   "LBS"),   1.0m  },
                { ("IN",    "YDS"),   36.0m },  // 36 inches per yard
                { ("FT",    "YDS"),   3.0m  },  // 3 feet per yard
            };

        public override void UpdateDatabase()
        {
            try
            {
                int selfRefsInserted  = 0;
                int convRefsInserted  = 0;
                int skippedUnknown    = 0;

                WriteLog("UomUnitConversionRestore: starting INUnit self-reference restore...");

                PXDataRecord[] items = PXDatabase.SelectMulti<InventoryItem>(
                    new PXDataField<InventoryItem.inventoryID>(),
                    new PXDataField<InventoryItem.baseUnit>(),
                    new PXDataField<InventoryItem.salesUnit>(),
                    new PXDataField<InventoryItem.purchaseUnit>(),
                    new PXDataFieldValue<InventoryItem.deletedDatabaseRecord>(false)
                );

                foreach (PXDataRecord item in items)
                {
                    int?   inventoryID = item.GetInt32(0);
                    string baseUnit    = item.GetString(1);
                    string salesUnit   = item.GetString(2);
                    string purchUnit   = item.GetString(3);

                    if (inventoryID == null || string.IsNullOrEmpty(baseUnit)) continue;

                    // 1. BaseUnit→BaseUnit self-reference (mandatory for all UOM validation)
                    EnsureConversion(inventoryID.Value, baseUnit, baseUnit,
                        ref selfRefsInserted, ref skippedUnknown);

                    // 2. SalesUnit→BaseUnit (if different)
                    if (!string.IsNullOrEmpty(salesUnit) && salesUnit != baseUnit)
                    {
                        EnsureConversion(inventoryID.Value, salesUnit, baseUnit,
                            ref convRefsInserted, ref skippedUnknown);

                        // SalesUnit self-reference (needed for SalesUnit validation)
                        EnsureConversion(inventoryID.Value, salesUnit, salesUnit,
                            ref selfRefsInserted, ref skippedUnknown);
                    }

                    // 3. PurchaseUnit→BaseUnit (if different from both BaseUnit and SalesUnit)
                    if (!string.IsNullOrEmpty(purchUnit)
                        && purchUnit != baseUnit
                        && purchUnit != salesUnit)
                    {
                        EnsureConversion(inventoryID.Value, purchUnit, baseUnit,
                            ref convRefsInserted, ref skippedUnknown);

                        // PurchaseUnit self-reference
                        EnsureConversion(inventoryID.Value, purchUnit, purchUnit,
                            ref selfRefsInserted, ref skippedUnknown);
                    }
                }

                WriteLog(
                    $"UomUnitConversionRestore: COMPLETE — " +
                    $"self-refs inserted: {selfRefsInserted}, " +
                    $"conversions inserted: {convRefsInserted}, " +
                    $"unknown pairs skipped: {skippedUnknown}."
                );
            }
            catch (Exception ex)
            {
                WriteLog($"UomUnitConversionRestore: FAILED — {ex.GetType().Name}: {ex.Message}");
                throw;
            }
        }

        private void EnsureConversion(
            int inventoryID, string fromUnit, string toUnit,
            ref int insertCount, ref int skipCount)
        {
            // Check existence before insert (idempotent)
            bool exists = PXDatabase.Exists<INUnit>(
                new PXDataFieldValue<INUnit.unitType>((short)INUnitType.InventoryItem),
                new PXDataFieldValue<INUnit.inventoryID>(inventoryID),
                new PXDataFieldValue<INUnit.fromUnit>(fromUnit),
                new PXDataFieldValue<INUnit.toUnit>(toUnit)
            );

            if (exists) return;

            // Look up the conversion rate — skip unknown pairs with a warning
            // (wrong rate is worse than a missing record)
            if (!KnownRates.TryGetValue((fromUnit, toUnit), out decimal rate))
            {
                WriteLog(
                    $"UomUnitConversionRestore: SKIP — unknown conversion " +
                    $"{fromUnit}→{toUnit} for InventoryID {inventoryID}. " +
                    $"Add rate to KnownRates and re-publish."
                );
                skipCount++;
                return;
            }

            PXDatabase.Insert<INUnit>(
                new PXDataFieldAssign<INUnit.unitType>((short)INUnitType.InventoryItem),
                new PXDataFieldAssign<INUnit.itemClassID>(0),
                new PXDataFieldAssign<INUnit.inventoryID>(inventoryID),
                new PXDataFieldAssign<INUnit.fromUnit>(fromUnit),
                new PXDataFieldAssign<INUnit.toUnit>(toUnit),
                new PXDataFieldAssign<INUnit.unitMultDiv>(INUnitMultDiv.Multiply),
                new PXDataFieldAssign<INUnit.unitRate>(rate),
                new PXDataFieldAssign<INUnit.priceAdjustmentMultiplier>(1.0m)
            );

            insertCount++;
        }
    }
}
