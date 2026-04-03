using PX.Data;
using PX.Objects.IN;

namespace Aesthetik.WMS
{
    /// <summary>
    /// Graph extension for INSetupMaint (IN.20.10.00 — Inventory Preferences).
    /// Surfaces the Piece Goods WMS configuration fields on the Inventory Preferences screen.
    /// This extension adds a "Piece Goods" tab/section to the preferences form.
    /// </summary>
    public class INSetupMaintExt : PXGraphExtension<INSetupMaint>
    {
        public static bool IsActive() => true;

        #region Event Handlers

        /// <summary>
        /// Sets default values for Piece Goods fields when the INSetup record is first created.
        /// </summary>
        protected virtual void _(Events.RowInserted<INSetup> e)
        {
            if (e.Row == null) return;

            var ext = e.Row.GetExtension<INSetupExt>();
            if (ext == null) return;

            ext.UsrPGMinRemnant    ??= PieceGoodsConstants.DefaultMinRemnantYardage;
            ext.UsrPGAutoQtyMode   ??= PieceGoodsConstants.DefaultAutoQuantityMode;
            ext.UsrPGAutoPrint     ??= PieceGoodsConstants.DefaultAutoPrintLabel;
            ext.UsrPGCutSuffix     ??= PieceGoodsConstants.DefaultCutSerialSuffix;
            ext.UsrPGPreRecv       ??= PieceGoodsConstants.DefaultPreReceivingEnabled;
            ext.UsrPGCrossDock     ??= PieceGoodsConstants.DefaultCrossDockEnabled;
            ext.UsrPGXDockAge      ??= PieceGoodsConstants.DefaultCrossDockAgeDays;
            ext.UsrPGInTransitWt   ??= PieceGoodsConstants.DefaultInTransitAllocWeight;
            ext.UsrPGYardageVar    ??= PieceGoodsConstants.DefaultYardageVarianceThreshold;
            ext.UsrPGWtExact       ??= PieceGoodsConstants.DefaultWeight_ExactMatch;
            ext.UsrPGWtRemnant     ??= PieceGoodsConstants.DefaultWeight_MinimizeRemnant;
            ext.UsrPGWtDyeLot      ??= PieceGoodsConstants.DefaultWeight_DyeLotMatch;
            ext.UsrPGWtLocation    ??= PieceGoodsConstants.DefaultWeight_LocationPref;
            ext.UsrPGWtFIFO        ??= PieceGoodsConstants.DefaultWeight_FIFOAge;
        }

        /// <summary>
        /// Validates Piece Goods configuration values on save.
        /// </summary>
        protected virtual void _(Events.RowPersisting<INSetup> e)
        {
            if (e.Row == null || e.Operation == PXDBOperation.Delete) return;

            var ext = e.Row.GetExtension<INSetupExt>();
            if (ext == null) return;

            // Min remnant must be non-negative
            if (ext.UsrPGMinRemnant < 0)
            {
                e.Cache.RaiseExceptionHandling<INSetupExt.usrPGMinRemnant>(
                    e.Row, ext.UsrPGMinRemnant,
                    new PXSetPropertyException("Minimum remnant yardage cannot be negative."));
            }

            // Cross-dock age must be positive
            if (ext.UsrPGXDockAge.HasValue && ext.UsrPGXDockAge <= 0)
            {
                e.Cache.RaiseExceptionHandling<INSetupExt.usrPGXDockAge>(
                    e.Row, ext.UsrPGXDockAge,
                    new PXSetPropertyException("Cross-dock age limit must be greater than zero."));
            }

            // Yardage variance threshold must be between 0 and 1
            if (ext.UsrPGYardageVar < 0 || ext.UsrPGYardageVar > 1)
            {
                e.Cache.RaiseExceptionHandling<INSetupExt.usrPGYardageVar>(
                    e.Row, ext.UsrPGYardageVar,
                    new PXSetPropertyException(
                        "Yardage variance threshold must be between 0.00 and 1.00 (0% to 100%)."));
            }

            // Optimizer weights should be non-negative
            ValidateWeight<INSetupExt.usrPGWtExact>(e.Cache, e.Row, ext.UsrPGWtExact, "Exact Match");
            ValidateWeight<INSetupExt.usrPGWtRemnant>(e.Cache, e.Row, ext.UsrPGWtRemnant, "Minimize Remnant");
            ValidateWeight<INSetupExt.usrPGWtDyeLot>(e.Cache, e.Row, ext.UsrPGWtDyeLot, "Dye Lot Match");
            ValidateWeight<INSetupExt.usrPGWtLocation>(e.Cache, e.Row, ext.UsrPGWtLocation, "Location Preference");
            ValidateWeight<INSetupExt.usrPGWtFIFO>(e.Cache, e.Row, ext.UsrPGWtFIFO, "FIFO Age");

            // Cut serial suffix must contain {0} placeholder
            if (!string.IsNullOrEmpty(ext.UsrPGCutSuffix) && !ext.UsrPGCutSuffix.Contains("{0}"))
            {
                e.Cache.RaiseExceptionHandling<INSetupExt.usrPGCutSuffix>(
                    e.Row, ext.UsrPGCutSuffix,
                    new PXSetPropertyException(
                        "Cut serial suffix must contain {{0}} placeholder for the sequence number."));
            }
        }

        #endregion

        #region Private Helpers

        private static void ValidateWeight<TField>(PXCache cache, INSetup row, int? value, string fieldName)
            where TField : IBqlField
        {
            if (value.HasValue && value < 0)
            {
                cache.RaiseExceptionHandling<TField>(
                    row, value,
                    new PXSetPropertyException($"Pick optimizer weight '{fieldName}' cannot be negative."));
            }
        }

        #endregion
    }
}
