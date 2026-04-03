using System;
using PX.Data;
using PX.Objects.PO;

namespace HeritageFabrics.PO
{
    public class POOrderEntry_Extension : PXGraphExtension<POOrderEntry>
    {
        public static bool IsActive() => true;

        protected void _(Events.FieldDefaulting<POLine, POLineExt.usrExpArrivalDate> e)
        {
            if (e.Row == null) return;
            POOrder header = Base.Document.Current;
            if (header == null) return;
            POOrderExt headerExt = header.GetExtension<POOrderExt>();
            if (headerExt?.UsrExpArrivalDate != null)
            {
                e.NewValue = headerExt.UsrExpArrivalDate;
                e.Cancel = true;
            }
        }

        protected void _(Events.FieldUpdated<POOrder, POOrderExt.usrExpArrivalDate> e)
        {
            if (e.Row == null) return;
            DateTime? oldValue = (DateTime?)e.OldValue;
            DateTime? newValue = e.Row.GetExtension<POOrderExt>()?.UsrExpArrivalDate;
            if (newValue == null) return;
            if (oldValue == newValue) return;
            foreach (POLine line in Base.Transactions.Select())
            {
                POLineExt lineExt = line.GetExtension<POLineExt>();
                if (lineExt == null) continue;
                bool isInherited = lineExt.UsrExpArrivalDate == null || lineExt.UsrExpArrivalDate == oldValue;
                if (isInherited)
                {
                    lineExt.UsrExpArrivalDate = newValue;
                    Base.Transactions.Update(line);
                }
            }
        }
    }
}
