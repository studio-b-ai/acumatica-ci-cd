using System;
using PX.Data;
using PX.Data.BQL;
using PX.Data.BQL.Fluent;
using PX.Objects.IN;
using PX.Objects.SO;

namespace HeritageFabrics.SO
{
    /// <summary>
    /// Fixes "InvtMult cannot be empty" error on SOLine persist.
    ///
    /// InvtMult is set by SOOrderEntry when Operation is defaulted, but certain
    /// order types (e.g. PC) or data-repair scenarios can leave it null.
    /// This extension catches the gap at RowPersisting and defaults InvtMult
    /// from SOOrderTypeOperation, preventing the PXDefaultAttribute error.
    ///
    /// Issue: acumatica-ci-cd#101
    /// Repro: Sales Order PC S004709 (FABRICUT) — Save throws
    ///        "Error: 'InvtMult' cannot be empty"
    /// </summary>
    public class SOOrderEntry_InvtMultFix : PXGraphExtension<SOOrderEntry>
    {
        public static bool IsActive() => true;

        private bool _invtMultGuard;

        protected void _(Events.RowPersisting<SOLine> e)
        {
            if (e.Row == null || _invtMultGuard) return;

            SOLine line = e.Row;

            if (line.InvtMult == null && line.InventoryID != null)
            {
                _invtMultGuard = true;
                try
                {
                    // Look up the operation config for this order type + operation
                    SOOrderTypeOperation operation = SelectFrom<SOOrderTypeOperation>
                        .Where<SOOrderTypeOperation.orderType.IsEqual<@P.AsString>
                            .And<SOOrderTypeOperation.operation.IsEqual<@P.AsString>>>
                        .View.Select(Base, line.OrderType, line.Operation ?? SOOperation.Issue);

                    if (operation != null)
                    {
                        short invtMult = operation.InvtMult ?? (short)1;
                        Base.Transactions.Cache.SetValueExt<SOLine.invtMult>(line, invtMult);
                    }
                }
                finally
                {
                    _invtMultGuard = false;
                }
            }
        }
    }
}
