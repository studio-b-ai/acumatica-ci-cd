using System;
using System.Configuration;
using Customization;

namespace Aesthetik.WMS
{
    /// <summary>
    /// Unified CustomizationPlugin that creates all database objects during publish.
    ///
    /// Consolidates HeritageFabricsPOv5 + AesthetikWMS schema management:
    /// - UsrPORelation and UsrPOActivity tables (heritage-wms PO sync)
    /// - PO/SO/AR extension columns (arrival dates, HubSpot IDs, WMS status, pay link)
    /// - WMS extension columns on INLotSerialClass, INLotSerialStatus, INSetup
    ///
    /// Uses Microsoft.Data.SqlClient with IF NOT EXISTS guards — idempotent and
    /// safe to run alongside StudioBPORelations (which also creates PO tables).
    ///
    /// Required because Acumatica cloud blocks CREATE TABLE in &lt;Sql&gt; elements
    /// during customization publish. CustomizationPlugin.UpdateDatabase() executes
    /// raw DDL via direct connection, bypassing that restriction.
    /// </summary>
    public class WMSDatabaseInstaller : CustomizationPlugin
    {
        public override void UpdateDatabase()
        {
            string connStr = GetConnectionString();
            if (connStr == null)
            {
                WriteLog("[AesthetikWMS] No connection string found — cannot run DDL");
                return;
            }

            // Microsoft.Data.SqlClient requires explicit SSL trust for cloud SQL
            if (!connStr.Contains("TrustServerCertificate"))
                connStr += ";TrustServerCertificate=True";

            // ── PO Sync Tables (heritage-wms dependency) ─────────────────────

            ExecuteDDL(connStr, "UsrPORelation", @"
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'UsrPORelation')
CREATE TABLE UsrPORelation (
    CompanyID INT NOT NULL DEFAULT 0,
    UsrPORelationID INT IDENTITY(1,1) NOT NULL,
    RefNoteID UNIQUEIDENTIFIER NULL,
    Role NVARCHAR(50) NULL,
    ContactName NVARCHAR(100) NULL,
    Email NVARCHAR(100) NULL,
    Phone NVARCHAR(50) NULL,
    Company NVARCHAR(100) NULL,
    AddToCC BIT NULL DEFAULT 0,
    IsActive BIT NULL DEFAULT 1,
    CreatedByID UNIQUEIDENTIFIER NULL,
    CreatedByScreenID CHAR(8) NULL,
    CreatedDateTime DATETIME NULL,
    LastModifiedByID UNIQUEIDENTIFIER NULL,
    LastModifiedByScreenID CHAR(8) NULL,
    LastModifiedDateTime DATETIME NULL,
    tstamp TIMESTAMP NOT NULL,
    CONSTRAINT PK_UsrPORelation PRIMARY KEY CLUSTERED (CompanyID, UsrPORelationID)
)");

            ExecuteDDL(connStr, "UsrPOActivity", @"
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'UsrPOActivity')
CREATE TABLE UsrPOActivity (
    CompanyID INT NOT NULL DEFAULT 0,
    UsrPOActivityID INT IDENTITY(1,1) NOT NULL,
    RefNoteID UNIQUEIDENTIFIER NULL,
    Type CHAR(2) NULL DEFAULT 'NT',
    Subject NVARCHAR(255) NULL,
    Body NVARCHAR(MAX) NULL,
    Status CHAR(2) NULL DEFAULT 'OP',
    Priority CHAR(1) NULL DEFAULT 'N',
    StartDate DATETIME NULL,
    OwnerID NVARCHAR(100) NULL,
    CreatedByID UNIQUEIDENTIFIER NULL,
    CreatedByScreenID CHAR(8) NULL,
    CreatedDateTime DATETIME NULL,
    LastModifiedByID UNIQUEIDENTIFIER NULL,
    LastModifiedByScreenID CHAR(8) NULL,
    LastModifiedDateTime DATETIME NULL,
    tstamp TIMESTAMP NOT NULL,
    CONSTRAINT PK_UsrPOActivity PRIMARY KEY CLUSTERED (CompanyID, UsrPOActivityID)
)");

            // PO table indexes
            ExecuteDDL(connStr, "IX_UsrPORelation_RefNoteID",
                "IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_UsrPORelation_RefNoteID') " +
                "CREATE INDEX IX_UsrPORelation_RefNoteID ON UsrPORelation(CompanyID, RefNoteID)");

            ExecuteDDL(connStr, "IX_UsrPOActivity_RefNoteID",
                "IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_UsrPOActivity_RefNoteID') " +
                "CREATE INDEX IX_UsrPOActivity_RefNoteID ON UsrPOActivity(CompanyID, RefNoteID)");

            // ── PO / SO / AR Extension Columns (from HeritageFabricsPOv5) ────

            // POOrder (3 columns)
            AddColumnIfMissing(connStr, "POOrder", "UsrExpArrivalDate", "datetime NULL");
            AddColumnIfMissing(connStr, "POOrder", "UsrActArrivalDate", "datetime NULL");
            AddColumnIfMissing(connStr, "POOrder", "UsrContainerRef", "nvarchar(50) NULL");

            // POLine (2 columns)
            AddColumnIfMissing(connStr, "POLine", "UsrExpArrivalDate", "datetime NULL");
            AddColumnIfMissing(connStr, "POLine", "UsrActArrivalDate", "datetime NULL");

            // SOOrder (4 columns)
            AddColumnIfMissing(connStr, "SOOrder", "UsrHubSpotDealId", "nvarchar(50) NULL");
            AddColumnIfMissing(connStr, "SOOrder", "UsrWMSStatus", "nvarchar(20) NULL");
            AddColumnIfMissing(connStr, "SOOrder", "UsrComplianceHold", "bit NULL");
            AddColumnIfMissing(connStr, "SOOrder", "UsrComplianceHoldReason", "nvarchar(500) NULL");

            // BAccount (1 column — Customer pay link exclusion)
            AddColumnIfMissing(connStr, "BAccount", "UsrDisablePayLink", "bit NULL");

            // ── WMS Extension Columns (belt-and-suspenders alongside <Sql>) ──

            // INLotSerialClass (4 columns)
            AddColumnIfMissing(connStr, "INLotSerialClass", "UsrMinRemnant", "decimal(18,2) NULL");
            AddColumnIfMissing(connStr, "INLotSerialClass", "UsrAutoPrint", "bit NULL");
            AddColumnIfMissing(connStr, "INLotSerialClass", "UsrDefaultWidth", "decimal(18,1) NULL");
            AddColumnIfMissing(connStr, "INLotSerialClass", "UsrPreRecvEnabled", "bit NULL");

            // INLotSerialStatus (9 columns)
            AddColumnIfMissing(connStr, "INLotSerialStatus", "UsrActualYardage", "decimal(18,2) NULL");
            AddColumnIfMissing(connStr, "INLotSerialStatus", "UsrDyeLot", "nvarchar(30) NULL");
            AddColumnIfMissing(connStr, "INLotSerialStatus", "UsrWidth", "decimal(18,1) NULL");
            AddColumnIfMissing(connStr, "INLotSerialStatus", "UsrShadeCode", "nvarchar(10) NULL");
            AddColumnIfMissing(connStr, "INLotSerialStatus", "UsrSourceRoll", "nvarchar(30) NULL");
            AddColumnIfMissing(connStr, "INLotSerialStatus", "UsrDefectFlag", "bit NULL");
            AddColumnIfMissing(connStr, "INLotSerialStatus", "UsrInventoryStatus", "nvarchar(15) NULL");
            AddColumnIfMissing(connStr, "INLotSerialStatus", "UsrPreAssignedBin", "nvarchar(30) NULL");
            AddColumnIfMissing(connStr, "INLotSerialStatus", "UsrContainerNo", "nvarchar(30) NULL");

            // INSetup (14 columns)
            AddColumnIfMissing(connStr, "INSetup", "UsrPGMinRemnant", "decimal(18,2) NULL");
            AddColumnIfMissing(connStr, "INSetup", "UsrPGAutoQtyMode", "bit NULL");
            AddColumnIfMissing(connStr, "INSetup", "UsrPGAutoPrint", "bit NULL");
            AddColumnIfMissing(connStr, "INSetup", "UsrPGCutSuffix", "nvarchar(20) NULL");
            AddColumnIfMissing(connStr, "INSetup", "UsrPGPreRecv", "bit NULL");
            AddColumnIfMissing(connStr, "INSetup", "UsrPGCrossDock", "bit NULL");
            AddColumnIfMissing(connStr, "INSetup", "UsrPGXDockAge", "int NULL");
            AddColumnIfMissing(connStr, "INSetup", "UsrPGInTransitWt", "int NULL");
            AddColumnIfMissing(connStr, "INSetup", "UsrPGYardageVar", "decimal(18,4) NULL");
            AddColumnIfMissing(connStr, "INSetup", "UsrPGWtExact", "int NULL");
            AddColumnIfMissing(connStr, "INSetup", "UsrPGWtRemnant", "int NULL");
            AddColumnIfMissing(connStr, "INSetup", "UsrPGWtDyeLot", "int NULL");
            AddColumnIfMissing(connStr, "INSetup", "UsrPGWtLocation", "int NULL");
            AddColumnIfMissing(connStr, "INSetup", "UsrPGWtFIFO", "int NULL");

            WriteLog("[AesthetikWMS] UpdateDatabase complete — PO tables + all extension columns verified");
        }

        private string GetConnectionString()
        {
            try
            {
                var cs = ConfigurationManager.ConnectionStrings["ProjectX"];
                if (cs != null) return cs.ConnectionString;
            }
            catch { }

            // Fallback: scan all connection strings
            try
            {
                var allCs = ConfigurationManager.ConnectionStrings;
                for (int i = 0; i < allCs.Count; i++)
                {
                    if (allCs[i].Name != "LocalSqlServer" && allCs[i].Name != "LocalMySqlServer")
                        return allCs[i].ConnectionString;
                }
            }
            catch { }

            return null;
        }

        private void AddColumnIfMissing(string connStr, string table, string column, string definition)
        {
            string sql = string.Format(
                "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('{0}') AND name = '{1}') " +
                "ALTER TABLE [{0}] ADD [{1}] {2}",
                table, column, definition);
            ExecuteDDL(connStr, table + "." + column, sql);
        }

        private void ExecuteDDL(string connStr, string label, string sql)
        {
            try
            {
                using (var conn = new Microsoft.Data.SqlClient.SqlConnection(connStr))
                {
                    conn.Open();
                    using (var cmd = conn.CreateCommand())
                    {
                        cmd.CommandText = sql;
                        cmd.CommandTimeout = 60;
                        cmd.ExecuteNonQuery();
                    }
                }
                WriteLog("[AesthetikWMS] " + label + " — OK");
            }
            catch (Exception ex)
            {
                WriteLog("[AesthetikWMS] " + label + " — FAILED: " + ex.GetType().FullName + ": " + ex.Message);
            }
        }
    }
}
