using System;
using PX.Data;
using PX.Data.BQL;
using PX.Data.BQL.Fluent;
using PX.Objects.IN;
using PX.Objects.SO;

namespace HeritageFabrics.SO
{
    /// <summary>
    /// Fixes "InvtMult cannot be empty" error on SOLine and SOLineSplit persist.
    ///
    /// InvtMult is set by SOOrderEntry when Operation is defaulted, but certain
    /// order types (e.g. PC) or data-repair scenarios can leave it null.
    /// This extension catches the gap at FieldDefaulting and RowSelected to
    /// default InvtMult from SOOrderTypeOperation before PXDefaultAttribute
    /// validates at RowPersisting.
    ///
    /// Covers both SOLine (original fix) and SOLineSplit (auto-allocation
    /// creates splits that inherit null InvtMult from parent line).
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
        /// Fix existing orders with null InvtMult at persist time.
        /// Previously used RowSelected + SetValue, but that marks rows dirty
        /// during read-only ContractBased API access, causing InvalidOperationException
        /// on GET and empty $expand=Details results.
        /// RowPersisting only fires on save, so it's safe for API reads.
        /// </summary>
        protected void _(Events.RowPersisting<SOLine> e)
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

        /// <summary>
        /// Provide InvtMult default for SOLineSplit when the framework cannot
        /// resolve it (auto-allocation creates splits inheriting null from parent).
        /// </summary>
        protected void _(Events.FieldDefaulting<SOLineSplit, SOLineSplit.invtMult> e)
        {
            if (e.Row == null || e.NewValue != null) return;

            SOLineSplit split = e.Row;
            if (split.OrderType == null) return;

            SOOrderTypeOperation operation = SelectFrom<SOOrderTypeOperation>
                .Where<SOOrderTypeOperation.orderType.IsEqual<@P.AsString>
                    .And<SOOrderTypeOperation.operation.IsEqual<@P.AsString>>>
                .View.Select(Base, split.OrderType, split.Operation ?? SOOperation.Issue);

            if (operation != null)
            {
                e.NewValue = operation.InvtMult ?? (short)1;
            }
        }

        /// <summary>
        /// Fix existing splits with null InvtMult at persist time.
        /// Same fix as SOLine — moved from RowSelected to RowPersisting
        /// to avoid marking rows dirty during ContractBased API reads.
        /// </summary>
        protected void _(Events.RowPersisting<SOLineSplit> e)
        {
            if (e.Row == null) return;

            SOLineSplit split = e.Row;

            if (split.InvtMult == null && split.InventoryID != null && split.OrderType != null)
            {
                SOOrderTypeOperation operation = SelectFrom<SOOrderTypeOperation>
                    .Where<SOOrderTypeOperation.orderType.IsEqual<@P.AsString>
                        .And<SOOrderTypeOperation.operation.IsEqual<@P.AsString>>>
                    .View.Select(Base, split.OrderType, split.Operation ?? SOOperation.Issue);

                if (operation != null)
                {
                    short invtMult = operation.InvtMult ?? (short)1;
                    e.Cache.SetValue<SOLineSplit.invtMult>(split, invtMult);
                }
            }
        }
    }
}
