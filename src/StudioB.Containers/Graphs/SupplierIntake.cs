using System;
using PX.Data;

namespace StudioB.Containers
{
    /// <summary>
    /// Minimal graph for SB501200 — Supplier Intake shell.
    /// Renders a single PXHtmlView with a link to heritage-wms MOQ intake.
    /// </summary>
    public class SupplierIntake : PXGraph<SupplierIntake>
    {
        [Serializable]
        [PXVirtual]
        public class IntakeFilter : PXBqlTable, IBqlTable
        {
            public abstract class intakeUrl : PX.Data.BQL.BqlString.Field<intakeUrl> { }
            [PXString(IsUnicode = true)]
            [PXUIField(DisplayName = "Intake URL")]
            public virtual string IntakeUrl { get; set; }
        }

        public PXFilter<IntakeFilter> Filter;

        protected virtual void _(Events.RowSelected<IntakeFilter> e)
        {
            if (e.Row == null) return;
            e.Row.IntakeUrl = BuildIntakeHtml();
        }

        private string BuildIntakeHtml()
        {
            return @"<div style='text-align:center;padding:40px;'>
                <h2 style='color:#1d3557;font-family:""Segoe UI"",system-ui,sans-serif;'>Supplier Intake</h2>
                <p style='color:#4a5568;margin:20px 0;font-family:""Segoe UI"",system-ui,sans-serif;'>Submit MOQ data and vendor terms via the Heritage WMS portal.</p>
                <a href='https://wms.asthetik.com/moq-bulk' target='_blank'
                   style='display:inline-block;padding:12px 32px;background:#1d3557;color:white;
                          text-decoration:none;border-radius:4px;font-size:14px;font-family:""Segoe UI"",system-ui,sans-serif;'>
                    OPEN MOQ INTAKE
                </a>
                <p style='color:#718096;font-size:12px;margin-top:16px;font-family:""Segoe UI"",system-ui,sans-serif;'>Opens in a new window</p>
            </div>";
        }
    }
}
