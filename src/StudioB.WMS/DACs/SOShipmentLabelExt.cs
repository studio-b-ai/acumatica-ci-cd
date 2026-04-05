using PX.Data;

namespace HeritageFabrics.SO
{
    public class SOShipmentLabelExt : PXCacheExtension<PX.Objects.SO.SOShipment>
    {
        public static bool IsActive() => false;
    }
}