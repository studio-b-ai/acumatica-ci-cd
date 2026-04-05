using System.Collections;
using System.Collections.Generic;
using PX.Data;
using PX.Objects.SO;

namespace HeritageFabrics.SO
{
    /// <summary>
    /// Absorbed from WMSynergy.HF.CutHangTagLabel.
    /// Adds a "Print Cut Hang Tag" toolbar action to the Shipment screen (SO302000).
    /// Launches report WM302000 (Cut Roll Hang Tag) pre-populated with the
    /// current shipment number.
    /// </summary>
    public class SOShipmentEntry_CutHangTag : PXGraphExtension<SOShipmentEntry>
    {
        public static bool IsActive() => true;

        #region Actions

        public PXAction<SOShipment> PrintCutHangTag;

        [PXButton(CommitChanges = true)]
        [PXUIField(DisplayName = "Print Cut Hang Tag",
            MapEnableRights = PXCacheRights.Select,
            MapViewRights = PXCacheRights.Select)]
        protected virtual IEnumerable printCutHangTag(PXAdapter adapter)
        {
            SOShipment shipment = Base.Document.Current;
            if (shipment != null)
            {
                var parameters = new Dictionary<string, string>
                {
                    ["ShipmentNbr"] = shipment.ShipmentNbr?.Trim()
                };
                throw new PXReportRequiredException(parameters, "WM302000", "Cut Roll Hang Tag");
            }
            return adapter.Get();
        }

        #endregion
    }
}
