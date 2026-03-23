// Stub — tabled pending Fusion WMS deprecation.
// File must exist because it was previously imported into Acumatica's
// customization project database. Removing from git doesn't remove from
// Acumatica — an empty compilable stub prevents CR Validation errors.

using PX.Data;

namespace HeritageFabrics.SO
{
    public class SOShipmentLabelExt : PXCacheExtension<PX.Objects.SO.SOShipment>
    {
        public static bool IsActive() => false;
    }
}
