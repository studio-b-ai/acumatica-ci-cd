using PX.Data;
using PX.Data.BQL;
using PX.Objects.CR;
using PX.Objects.IN;

namespace StudioB.Containers
{
    /// <summary>
    /// Replaces IIG UsrIGCMDefaultInTransitSiteID on Vendor.
    /// Default in-transit warehouse for vendor ocean containers.
    /// Targets BAccount (not Vendor) because columns live on BAccount table,
    /// and Vendor maps to Vendor_Vendor view which does not expose Usr* columns.
    /// </summary>
    public sealed class BAccountContainerExt : PXCacheExtension<BAccount>
    {
        public static bool IsActive() => true;

        #region UsrDefaultInTransitSiteID
        public abstract class usrDefaultInTransitSiteID : BqlInt.Field<usrDefaultInTransitSiteID> { }
        [PXDBInt]
        [PXUIField(DisplayName = "Default In-Transit Warehouse")]
        [PXSelector(typeof(Search<INSite.siteID, Where<INSite.active, Equal<True>>>),
            SubstituteKey = typeof(INSite.siteCD),
            DescriptionField = typeof(INSite.descr))]
        public int? UsrDefaultInTransitSiteID { get; set; }
        #endregion

        #region UsrDefaultCarrierCode
        public abstract class usrDefaultCarrierCode : BqlString.Field<usrDefaultCarrierCode> { }
        [PXDBString(20, IsUnicode = true)]
        [PXUIField(DisplayName = "Default Carrier")]
        [PXStringList(new string[] { "MAERSK", "CHR", "OTS", "OTHER" },
                       new string[] { "Maersk", "CH Robinson", "OTS", "Other" })]
        public string UsrDefaultCarrierCode { get; set; }
        #endregion
    }
}
