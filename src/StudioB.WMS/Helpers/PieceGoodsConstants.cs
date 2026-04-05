using System;

namespace Aesthetik.WMS
{
    /// <summary>
    /// Constants used throughout the Piece Goods WMS customization.
    /// All magic strings, attribute IDs, and default values are centralized here.
    /// </summary>
    public static class PieceGoodsConstants
    {
        #region Lot/Serial Class

        /// <summary>Lot/serial class ID for all piece goods items.</summary>
        public const string LotSerialClassID = "PIECEGOODS";

        /// <summary>Serial number format: [SKU]-[YYMMDD]-[SEQ]</summary>
        public const string SerialFormat = "{0}-{1:yyMMdd}-{2:D3}";

        /// <summary>Cut piece serial suffix format: -C[SEQ]</summary>
        public const string DefaultCutSerialSuffix = "-C{0}";

        #endregion

        #region Lot/Serial Attributes

        public const string Attr_ActualYardage   = "ACTYARDAGE";
        public const string Attr_DyeLot          = "DYELOT";
        public const string Attr_Width            = "WIDTHIN";
        public const string Attr_ShadeCode        = "SHADECODE";
        public const string Attr_SourceRoll       = "SOURCEROLL";
        public const string Attr_DefectFlag       = "DEFECTFLAG";
        public const string Attr_InventoryStatus  = "INVSTATUS";
        public const string Attr_PreAssignedBin   = "PREASSIGNBIN";
        public const string Attr_ContainerNumber  = "CONTAINERNO";

        #endregion

        #region Inventory Status Values

        public const string InvStatus_InTransit    = "IN-TRANSIT";
        public const string InvStatus_Receiving    = "RECEIVING";
        public const string InvStatus_PutAway      = "PUT-AWAY";
        public const string InvStatus_Available    = "AVAILABLE";
        public const string InvStatus_CrossDockHold = "XDOCK-HOLD";

        #endregion

        #region Warehouse Locations

        /// <summary>Virtual receiving dock location for cross-dock workflow.</summary>
        public const string Location_RecvDock = "RECV-DOCK";

        /// <summary>Staging sub-location prefix for large warehouses.</summary>
        public const string Location_StagingPrefix = "RECV-STAGING-";

        /// <summary>Number of default staging sub-locations.</summary>
        public const int DefaultStagingLocations = 4;

        #endregion

        #region GS1-128 Application Identifiers

        /// <summary>AI 01: GTIN / SKU</summary>
        public const string AI_GTIN = "01";

        /// <summary>AI 21: Serial Number</summary>
        public const string AI_Serial = "21";

        /// <summary>AI 10: Batch/Lot Number (Dye Lot)</summary>
        public const string AI_Lot = "10";

        /// <summary>GS1 FNC1 separator character.</summary>
        public const char GS1_FNC1 = '\u001D';

        /// <summary>GS1 AI start parenthesis (human-readable format).</summary>
        public const char GS1_AI_Start = '(';
        public const char GS1_AI_End = ')';

        #endregion

        #region Configuration Defaults

        public const decimal DefaultMinRemnantYardage       = 1.0m;
        public const bool    DefaultAutoQuantityMode        = true;
        public const int     DefaultDyeLotMatchWeight       = 15;
        public const bool    DefaultAutoPrintLabel          = true;
        public const bool    DefaultPreReceivingEnabled     = true;
        public const bool    DefaultCrossDockEnabled        = true;
        public const int     DefaultCrossDockAgeDays        = 5;
        public const int     DefaultInTransitAllocWeight    = -20;
        public const decimal DefaultYardageVarianceThreshold = 0.02m;

        // Pick optimizer scoring weights
        public const int DefaultWeight_ExactMatch       = 50;
        public const int DefaultWeight_MinimizeRemnant  = 30;
        public const int DefaultWeight_DyeLotMatch      = 15;
        public const int DefaultWeight_LocationPref     = 10;
        public const int DefaultWeight_FIFOAge          = 5;

        #endregion

        #region Scan Commands

        /// <summary>Scan command to enter pick mode.</summary>
        public const string ScanCmd_Pick    = "@pick";

        /// <summary>Scan command to confirm an action (e.g., cut confirmation).</summary>
        public const string ScanCmd_Confirm = "@confirm";

        /// <summary>Scan command to override a suggestion.</summary>
        public const string ScanCmd_Override = "@override";

        /// <summary>Scan command to skip a pick line.</summary>
        public const string ScanCmd_Skip = "@skip";

        /// <summary>Scan command to print label.</summary>
        public const string ScanCmd_Print = "@print";

        #endregion

        #region Custom Field Names (DAC extensions)

        // INLotSerialStatus extension fields
        public const string Fld_ActualYardage        = "UsrActualYardage";
        public const string Fld_DyeLot               = "UsrDyeLot";
        public const string Fld_Width                = "UsrWidth";
        public const string Fld_ShadeCode            = "UsrShadeCode";
        public const string Fld_SourceRoll           = "UsrSourceRoll";
        public const string Fld_DefectFlag           = "UsrDefectFlag";
        public const string Fld_InventoryStatus      = "UsrInventoryStatus";
        public const string Fld_PreAssignedBin       = "UsrPreAssignedBin";
        public const string Fld_ContainerNumber      = "UsrContainerNo";

        // INSetup extension fields
        public const string Fld_PGMinRemnant         = "UsrPGMinRemnant";
        public const string Fld_PGAutoQtyMode        = "UsrPGAutoQtyMode";
        public const string Fld_PGDyeLotWeight       = "UsrPGDyeLotWeight";
        public const string Fld_PGAutoPrint          = "UsrPGAutoPrint";
        public const string Fld_PGCutSerialSuffix    = "UsrPGCutSuffix";
        public const string Fld_PGPreReceiving       = "UsrPGPreRecv";
        public const string Fld_PGCrossDock          = "UsrPGCrossDock";
        public const string Fld_PGCrossDockAgeDays   = "UsrPGXDockAge";
        public const string Fld_PGInTransitWeight    = "UsrPGInTransitWt";
        public const string Fld_PGYardageVariance    = "UsrPGYardageVar";

        // Pick optimizer weight fields on INSetup
        public const string Fld_PGWtExactMatch       = "UsrPGWtExact";
        public const string Fld_PGWtMinRemnant       = "UsrPGWtRemnant";
        public const string Fld_PGWtDyeLot           = "UsrPGWtDyeLot";
        public const string Fld_PGWtLocation         = "UsrPGWtLocation";
        public const string Fld_PGWtFIFO             = "UsrPGWtFIFO";

        #endregion
    }
}
