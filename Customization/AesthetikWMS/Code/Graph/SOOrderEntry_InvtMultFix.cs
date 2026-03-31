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

        /// <summary>
        /// Provide InvtMult default from SOOrderTypeOperation when the framework
        /// cannot resolve it (e.g. PC order type). Runs at FieldDefaulting so the
        /// value is set before PXDefaultAttribute validates at RowPersisting.
        /// </summary>
        protected void _(Events.FieldDefaulting<SOLine, SOLine.invtMult> e)
        {
            if (e.Row == null || e.NewValue != null) return;

            SOLine line = e.Row;
            if (line.OrderType == null) return;

            SOOrderTypeOperation operation = SelectFrom<SOOrderTypeOperation>
                .Where<SOOrderTypeOperation.orderType.IsEqual<@P.AsString>
                    .And<SOOrderTypeOperation.operation.IsEqual<@P.AsString>>>
                .View.Select(Base, line.OrderType, line.Operation ?? SOOperation.Issue);

            if (operation != null)
            {
                e.NewValue = operation.InvtMult ?? (short)1;
            }
        }

        /// <summary>
        /// Fix existing orders with null InvtMult: set it during RowSelected
        /// so it's populated before save even triggers RowPersisting.
        /// </summary>
        protected void _(Events.RowSelected<SOLine> e)
        {
            if (e.Row == null) return;

            SOLine line = e.Row;

            if (line.InvtMult == null && line.InventoryID != null && line.OrderType != null)
            {
                SOOrderTypeOperation operation = SelectFrom<SOOrderTypeOperation>
                    .Where<SOOrderTypeOperation.orderType.IsEqual<@P.AsString>
                        .And<SOOrderTypeOperation.operation.IsEqual<@P.AsString>>>
                    .View.Select(Base, line.OrderType, line.Operation ?? SOOperation.Issue);

                if (operation != null)
                {
                    short invtMult = operation.InvtMult ?? (short)1;
                    e.Cache.SetValue<SOLine.invtMult>(line, invtMult);
                }
            }
        }
    }
}
