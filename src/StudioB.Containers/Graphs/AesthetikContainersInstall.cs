using System;
using System.Configuration;
using System.Data.SqlClient;
using Customization;

namespace StudioB.Containers
{
    public class AesthetikContainersInstall : CustomizationPlugin
    {
        public override void UpdateDatabase()
        {
            try
            {
                var cs = ConfigurationManager.ConnectionStrings["ProjectX"];
                if (cs == null) { WriteLog("[AesthetikContainers] No ProjectX connection string — skipping DDL"); return; }
                string connStr = cs.ConnectionString + ";TrustServerCertificate=True";

                using (var conn = new SqlConnection(connStr))
                {
                    conn.Open();

                    // ── Container Tracking Tables ──────────────────────────────
                    EnsureTable(conn, "UsrContainer", @"
                        CompanyID int NOT NULL DEFAULT 0,
                        ContainerID int IDENTITY(1,1) NOT NULL,
                        ContainerCD nvarchar(20) NOT NULL,
                        CarrierCode nvarchar(20) NOT NULL DEFAULT 'OTHER',
                        BookingRef nvarchar(50) NULL,
                        BillOfLading nvarchar(50) NULL,
                        VesselName nvarchar(50) NULL,
                        VesselIMO nvarchar(10) NULL,
                        VoyageNbr nvarchar(30) NULL,
                        PortOfLoading nvarchar(10) NULL,
                        PortOfDischarge nvarchar(10) NULL,
                        ETD datetime NULL,
                        ATD datetime NULL,
                        ETA datetime NULL,
                        ATA datetime NULL,
                        Status nvarchar(20) NOT NULL DEFAULT 'BOOKED',
                        TransportMode nvarchar(10) NULL,
                        ContainerType nvarchar(10) NULL,
                        SealNbr nvarchar(20) NULL,
                        LandedCostRefNbr nvarchar(15) NULL,
                        LandedCostStatus nvarchar(20) NULL,
                        LastEventCode nvarchar(20) NULL,
                        LastEventDate datetime NULL,
                        LastSyncDate datetime NULL,
                        NoteID uniqueidentifier NULL,
                        CreatedByID uniqueidentifier NULL,
                        CreatedByScreenID char(8) NULL,
                        CreatedDateTime datetime NULL,
                        LastModifiedByID uniqueidentifier NULL,
                        LastModifiedByScreenID char(8) NULL,
                        LastModifiedDateTime datetime NULL,
                        tstamp timestamp NOT NULL,
                        CONSTRAINT PK_UsrContainer PRIMARY KEY (CompanyID, ContainerID)
                    ");

                    // UsrContainer incremental columns — EnsureTable above only runs on
                    // first CREATE. These EnsureColumn calls ALTER the existing table to
                    // add columns added to UsrContainer DAC after the table was created.
                    // Order matches DAC field definitions.
                    EnsureColumn(conn, "UsrContainer", "TransportMode", "nvarchar(10) NULL");
                    EnsureColumn(conn, "UsrContainer", "LandedCostRefNbr", "nvarchar(15) NULL");
                    EnsureColumn(conn, "UsrContainer", "LandedCostStatus", "nvarchar(20) NULL");
                    // 2026-04-07: Phase A Command Center redesign — new milestone,
                    // demurrage, forwarder/broker, CBP entry, and ISF fields.
                    EnsureColumn(conn, "UsrContainer", "BookedDate",          "datetime NULL");
                    EnsureColumn(conn, "UsrContainer", "DepartedDate",        "datetime NULL");
                    EnsureColumn(conn, "UsrContainer", "ArrivedPortDate",     "datetime NULL");
                    EnsureColumn(conn, "UsrContainer", "CustomsReleasedDate", "datetime NULL");
                    EnsureColumn(conn, "UsrContainer", "DeliveredDate",       "datetime NULL");
                    EnsureColumn(conn, "UsrContainer", "LastFreeDay",         "datetime NULL");
                    EnsureColumn(conn, "UsrContainer", "DemurrageDailyRate",  "decimal(19,4) NULL");
                    EnsureColumn(conn, "UsrContainer", "FreightForwarderID",  "int NULL");
                    EnsureColumn(conn, "UsrContainer", "BrokerID",            "int NULL");
                    EnsureColumn(conn, "UsrContainer", "EntryNumber",         "nvarchar(20) NULL");
                    EnsureColumn(conn, "UsrContainer", "EntryType",           "nvarchar(2) NULL");
                    EnsureColumn(conn, "UsrContainer", "EntryReleaseDate",    "datetime NULL");
                    EnsureColumn(conn, "UsrContainer", "DutyPaid",            "decimal(19,4) NULL");
                    EnsureColumn(conn, "UsrContainer", "MPFAmount",           "decimal(19,4) NULL");
                    EnsureColumn(conn, "UsrContainer", "HMFAmount",           "decimal(19,4) NULL");
                    EnsureColumn(conn, "UsrContainer", "ISFFiledDate",        "datetime NULL");
                    EnsureColumn(conn, "UsrContainer", "ISFFilingNbr",        "nvarchar(20) NULL");

                    EnsureTable(conn, "UsrContainerEvent", @"
                        CompanyID int NOT NULL DEFAULT 0,
                        EventID int IDENTITY(1,1) NOT NULL,
                        ContainerID int NOT NULL,
                        CarrierEventCode nvarchar(20) NOT NULL DEFAULT '',
                        NormalizedEventCode nvarchar(20) NOT NULL DEFAULT '',
                        EventDateTime datetime NOT NULL DEFAULT GETUTCDATE(),
                        EventClassifier nvarchar(10) NULL,
                        LocationName nvarchar(100) NULL,
                        LocationCode nvarchar(10) NULL,
                        VesselName nvarchar(50) NULL,
                        Description nvarchar(255) NULL,
                        RawPayload nvarchar(MAX) NULL,
                        CreatedDateTime datetime NOT NULL DEFAULT GETUTCDATE(),
                        CONSTRAINT PK_UsrContainerEvent PRIMARY KEY (CompanyID, EventID)
                    ");

                    EnsureTable(conn, "UsrContainerPOLink", @"
                        CompanyID int NOT NULL DEFAULT 0,
                        LinkID int IDENTITY(1,1) NOT NULL,
                        ContainerID int NOT NULL,
                        OrderType nvarchar(2) NOT NULL DEFAULT 'RO',
                        OrderNbr nvarchar(15) NOT NULL DEFAULT '',
                        LineNbr int NULL,
                        CONSTRAINT PK_UsrContainerPOLink PRIMARY KEY (CompanyID, LinkID)
                    ");

                    // Container Costs child table — shipped DAC in PR #232 (Bucket B
                    // Phase 1) but the EnsureTable was missed, so SB501000 opened the
                    // BQL select against UsrContainerCost and SQL Server returned
                    // "Invalid object name 'UsrContainerCost'" on any prod tenant
                    // that didn't have the table manually created. CRUD child table,
                    // shown as a tab on the Procurement Command Center screen.
                    EnsureTable(conn, "UsrContainerCost", @"
                        CompanyID int NOT NULL DEFAULT 0,
                        CostID int IDENTITY(1,1) NOT NULL,
                        ContainerID int NOT NULL,
                        CostType nvarchar(20) NOT NULL DEFAULT '',
                        Description nvarchar(100) NULL,
                        Amount decimal(19,4) NOT NULL DEFAULT 0,
                        VendorID int NULL,
                        ReferenceNbr nvarchar(30) NULL,
                        APDocType nchar(3) NULL,
                        APRefNbr nvarchar(15) NULL,
                        NoteID uniqueidentifier NULL,
                        CreatedByID uniqueidentifier NULL,
                        CreatedByScreenID char(8) NULL,
                        CreatedDateTime datetime NULL,
                        LastModifiedByID uniqueidentifier NULL,
                        LastModifiedByScreenID char(8) NULL,
                        LastModifiedDateTime datetime NULL,
                        tstamp timestamp NOT NULL,
                        CONSTRAINT PK_UsrContainerCost PRIMARY KEY (CompanyID, CostID)
                    ");

                    // 2026-04-07: Phase A Command Center — new child tables for ETA
                    // history audit trail and per-container document checklist, plus a
                    // new root table for customs broker master data.
                    EnsureTable(conn, "UsrContainerETAHistory", @"
                        CompanyID int NOT NULL DEFAULT 0,
                        ETAHistoryID int IDENTITY(1,1) NOT NULL,
                        ContainerID int NOT NULL,
                        RecordedDate datetime NOT NULL DEFAULT GETUTCDATE(),
                        PreviousETA datetime NULL,
                        NewETA datetime NOT NULL,
                        Source nvarchar(10) NOT NULL DEFAULT 'MANUAL',
                        Note nvarchar(255) NULL,
                        CreatedByID uniqueidentifier NULL,
                        CreatedDateTime datetime NULL,
                        tstamp timestamp NOT NULL,
                        CONSTRAINT PK_UsrContainerETAHistory PRIMARY KEY (CompanyID, ETAHistoryID)
                    ");

                    EnsureTable(conn, "UsrContainerDocument", @"
                        CompanyID int NOT NULL DEFAULT 0,
                        DocumentID int IDENTITY(1,1) NOT NULL,
                        ContainerID int NOT NULL,
                        DocumentType nvarchar(10) NOT NULL DEFAULT 'OTHER',
                        Required bit NOT NULL DEFAULT 1,
                        Status nvarchar(10) NOT NULL DEFAULT 'MISSING',
                        ReceivedDate datetime NULL,
                        VerifiedBy uniqueidentifier NULL,
                        Note nvarchar(255) NULL,
                        NoteID uniqueidentifier NULL,
                        CreatedByID uniqueidentifier NULL,
                        CreatedDateTime datetime NULL,
                        LastModifiedByID uniqueidentifier NULL,
                        LastModifiedDateTime datetime NULL,
                        tstamp timestamp NOT NULL,
                        CONSTRAINT PK_UsrContainerDocument PRIMARY KEY (CompanyID, DocumentID)
                    ");

                    EnsureTable(conn, "UsrCustomsBroker", @"
                        CompanyID int NOT NULL DEFAULT 0,
                        BrokerID int IDENTITY(1,1) NOT NULL,
                        BrokerCD nvarchar(15) NOT NULL DEFAULT '',
                        Description nvarchar(100) NOT NULL DEFAULT '',
                        ContactName nvarchar(100) NULL,
                        Email nvarchar(100) NULL,
                        Phone nvarchar(30) NULL,
                        FilerCode nvarchar(3) NULL,
                        Active bit NOT NULL DEFAULT 1,
                        Notes nvarchar(255) NULL,
                        NoteID uniqueidentifier NULL,
                        CreatedByID uniqueidentifier NULL,
                        CreatedByScreenID char(8) NULL,
                        CreatedDateTime datetime NULL,
                        LastModifiedByID uniqueidentifier NULL,
                        LastModifiedByScreenID char(8) NULL,
                        LastModifiedDateTime datetime NULL,
                        tstamp timestamp NOT NULL,
                        CONSTRAINT PK_UsrCustomsBroker PRIMARY KEY (CompanyID, BrokerID)
                    ");

                    // Indexes
                    EnsureIndex(conn, "UsrContainer", "IX_UsrContainer_ContainerCD", "CompanyID, ContainerCD");
                    EnsureIndex(conn, "UsrContainer", "IX_UsrContainer_Status", "CompanyID, Status");
                    EnsureIndex(conn, "UsrContainerEvent", "IX_UsrContainerEvent_ContainerID", "CompanyID, ContainerID, EventDateTime DESC");
                    EnsureIndex(conn, "UsrContainerPOLink", "IX_UsrContainerPOLink_ContainerID", "CompanyID, ContainerID");
                    EnsureIndex(conn, "UsrContainerPOLink", "IX_UsrContainerPOLink_PO", "CompanyID, OrderType, OrderNbr");
                    EnsureIndex(conn, "UsrContainerCost", "IX_UsrContainerCost_ContainerID", "CompanyID, ContainerID");
                    EnsureIndex(conn, "UsrContainerETAHistory", "IX_UsrContainerETAHistory_ContainerID", "CompanyID, ContainerID, RecordedDate DESC");
                    EnsureIndex(conn, "UsrContainerDocument", "IX_UsrContainerDocument_ContainerID", "CompanyID, ContainerID");
                    EnsureIndex(conn, "UsrCustomsBroker", "IX_UsrCustomsBroker_BrokerCD", "CompanyID, BrokerCD");

                    // SOShipment container fields
                    EnsureColumn(conn, "SOShipment", "UsrIncludeInContainer", "bit NULL DEFAULT 0");
                    EnsureColumn(conn, "SOShipment", "UsrContainerID", "int NULL");

                    // ── InventoryItem tariff/customs fields ────────────────────
                    EnsureColumn(conn, "InventoryItem", "UsrDutyRate", "decimal(25,4) NULL");
                    EnsureColumn(conn, "InventoryItem", "UsrFiberContent", "nvarchar(100) NULL");
                    EnsureColumn(conn, "InventoryItem", "UsrPreferentialTariff", "bit NULL");
                    EnsureColumn(conn, "InventoryItem", "UsrFreightClass", "nvarchar(15) NULL");

                    // ── POReceiptLine landed cost fields ───────────────────────
                    EnsureColumn(conn, "POReceiptLine", "UsrActualDutyAmt", "decimal(25,4) NULL");
                    EnsureColumn(conn, "POReceiptLine", "UsrActualFreightAmt", "decimal(25,4) NULL");
                    EnsureColumn(conn, "POReceiptLine", "UsrBrokerageAmt", "decimal(25,4) NULL");

                    // ── Freight Forwarders Table ──────────────────────────────
                    EnsureTable(conn, "UsrFreightForwarder", @"
                        CompanyID int NOT NULL DEFAULT 0,
                        ForwarderID int IDENTITY(1,1) NOT NULL,
                        ForwarderCD nvarchar(15) NOT NULL,
                        Name nvarchar(100) NOT NULL,
                        ContactName nvarchar(100) NULL,
                        Phone nvarchar(30) NULL,
                        Email nvarchar(100) NULL,
                        Website nvarchar(200) NULL,
                        CarrierAPIType nvarchar(20) NULL,
                        CarrierAPIKey nvarchar(200) NULL,
                        Active bit NOT NULL DEFAULT 1,
                        NoteID uniqueidentifier NULL,
                        CreatedByID uniqueidentifier NULL,
                        CreatedByScreenID char(8) NULL,
                        CreatedDateTime datetime NULL,
                        LastModifiedByID uniqueidentifier NULL,
                        LastModifiedByScreenID char(8) NULL,
                        LastModifiedDateTime datetime NULL,
                        tstamp timestamp NOT NULL,
                        CONSTRAINT PK_UsrFreightForwarder PRIMARY KEY (CompanyID, ForwarderID)
                    ");
                    EnsureIndex(conn, "UsrFreightForwarder", "IX_UsrFreightForwarder_CD", "CompanyID, ForwarderCD");

                    // ── Container Types Table ────────────────────────────────
                    EnsureTable(conn, "UsrContainerType", @"
                        CompanyID int NOT NULL DEFAULT 0,
                        ContainerTypeID int IDENTITY(1,1) NOT NULL,
                        TypeCD nvarchar(10) NOT NULL,
                        Description nvarchar(60) NULL,
                        LengthFt decimal(6,1) NULL,
                        WidthFt decimal(6,1) NULL,
                        HeightFt decimal(6,1) NULL,
                        MaxWeightKg decimal(10,0) NULL,
                        Active bit NOT NULL DEFAULT 1,
                        NoteID uniqueidentifier NULL,
                        CreatedByID uniqueidentifier NULL,
                        CreatedByScreenID char(8) NULL,
                        CreatedDateTime datetime NULL,
                        LastModifiedByID uniqueidentifier NULL,
                        LastModifiedByScreenID char(8) NULL,
                        LastModifiedDateTime datetime NULL,
                        tstamp timestamp NOT NULL,
                        CONSTRAINT PK_UsrContainerType PRIMARY KEY (CompanyID, ContainerTypeID)
                    ");
                    EnsureIndex(conn, "UsrContainerType", "IX_UsrContainerType_CD", "CompanyID, TypeCD");

                    // ── Ports Table ──────────────────────────────────────────
                    EnsureTable(conn, "UsrPort", @"
                        CompanyID int NOT NULL DEFAULT 0,
                        PortID int IDENTITY(1,1) NOT NULL,
                        PortCode nvarchar(10) NOT NULL,
                        PortName nvarchar(100) NOT NULL,
                        Country nvarchar(2) NULL,
                        Active bit NOT NULL DEFAULT 1,
                        NoteID uniqueidentifier NULL,
                        CreatedByID uniqueidentifier NULL,
                        CreatedByScreenID char(8) NULL,
                        CreatedDateTime datetime NULL,
                        LastModifiedByID uniqueidentifier NULL,
                        LastModifiedByScreenID char(8) NULL,
                        LastModifiedDateTime datetime NULL,
                        tstamp timestamp NOT NULL,
                        CONSTRAINT PK_UsrPort PRIMARY KEY (CompanyID, PortID)
                    ");
                    EnsureIndex(conn, "UsrPort", "IX_UsrPort_Code", "CompanyID, PortCode");

                    // ── Container Preferences Table ──────────────────────────
                    EnsureTable(conn, "UsrContainerPrefs", @"
                        CompanyID int NOT NULL DEFAULT 0,
                        PrefsID int NOT NULL DEFAULT 1,
                        DefaultCarrierCode nvarchar(20) NULL,
                        DefaultContainerType nvarchar(10) NULL,
                        DefaultInTransitWarehouse nvarchar(30) NULL,
                        AutoLinkPOsByRef bit NOT NULL DEFAULT 1,
                        TrackingPollIntervalHours int NOT NULL DEFAULT 24,
                        NoteID uniqueidentifier NULL,
                        CreatedByID uniqueidentifier NULL,
                        CreatedByScreenID char(8) NULL,
                        CreatedDateTime datetime NULL,
                        LastModifiedByID uniqueidentifier NULL,
                        LastModifiedByScreenID char(8) NULL,
                        LastModifiedDateTime datetime NULL,
                        tstamp timestamp NOT NULL,
                        CONSTRAINT PK_UsrContainerPrefs PRIMARY KEY (CompanyID, PrefsID)
                    ");
                    // Backfill LC code mapping columns added in commit 00eba6d (2026-04-06).
                    // The DAC has these fields but EnsureTable skipped creating them because
                    // IF NOT EXISTS only creates the table, not new columns on existing tables.
                    // Surfaced by sandbox UI test failure on 2026-04-08 when SB302030 and
                    // SB501000 both redirected to ERROR with "Invalid column name 'LCCode*'".
                    EnsureColumn(conn, "UsrContainerPrefs", "LCCodeShipping",  "nvarchar(15) NULL");
                    EnsureColumn(conn, "UsrContainerPrefs", "LCCodeDuty",      "nvarchar(15) NULL");
                    EnsureColumn(conn, "UsrContainerPrefs", "LCCodeTariff",    "nvarchar(15) NULL");
                    EnsureColumn(conn, "UsrContainerPrefs", "LCCodeBrokerage", "nvarchar(15) NULL");
                    EnsureColumn(conn, "UsrContainerPrefs", "LCCodeOther",     "nvarchar(15) NULL");
                    // ── IGCM → UsrContainer Data Migration ──────────────────
                    // Idempotent (NOT EXISTS guards). Safe to run on every publish.
                    // Migrates IIG container data to AesthetikContainers tables.
                    MigrateIGCMContainers(conn);

                    // ── Per-company DML (SiteMap, seed data) ─────────────────
                    // GIs are now created via XML files (GenericInquiryScreen_*.xml).
                    // These tables are CompanyID-scoped. Discover all companies
                    // dynamically so the plugin works on any tenant (test or prod).
                    var companies = DiscoverCompanies(conn);
                    foreach (var kvp in companies)
                    {
                        int companyId = kvp.Key;
                        string companyName = kvp.Value;
                        WriteLog(string.Format("[AesthetikContainers] Processing company '{0}' (CompanyID={1})", companyName, companyId));

                        try { EnsureContainerTrackingSiteMap(conn, companyId); }
                        catch (Exception ex) { WriteLog(string.Format("[AesthetikContainers] SiteMap update failed CID={0}: {1}", companyId, ex.Message)); }

                        try { SeedContainerTypes(conn, companyId); }
                        catch (Exception ex) { WriteLog(string.Format("[AesthetikContainers] Seed types failed CID={0}: {1}", companyId, ex.Message)); }

                        try { SeedPorts(conn, companyId); }
                        catch (Exception ex) { WriteLog(string.Format("[AesthetikContainers] Seed ports failed CID={0}: {1}", companyId, ex.Message)); }

                        try { SeedContainerPreferences(conn, companyId); }
                        catch (Exception ex) { WriteLog(string.Format("[AesthetikContainers] Seed prefs failed CID={0}: {1}", companyId, ex.Message)); }
                    }
                }

                WriteLog("[AesthetikContainers] All tables, columns, indexes, and migration verified/created.");
            }
            catch (Exception ex)
            {
                WriteLog("[AesthetikContainers] ERROR: " + ex.GetType().FullName + ": " + ex.Message);
                if (ex.InnerException != null)
                    WriteLog("[AesthetikContainers] Inner: " + ex.InnerException.Message);
            }
        }

        private System.Collections.Generic.Dictionary<int, string> DiscoverCompanies(SqlConnection conn)
        {
            // Key by CompanyID (guaranteed unique) → company name for logging
            var companies = new System.Collections.Generic.Dictionary<int, string>();
            using (var cmd = conn.CreateCommand())
            {
                cmd.CommandText = "SELECT CompanyID, COALESCE(CompanyCD, CAST(CompanyID AS nvarchar)) FROM Company WHERE CompanyID > 0";
                cmd.CommandTimeout = 30;
                try
                {
                    using (var rdr = cmd.ExecuteReader())
                    {
                        while (rdr.Read())
                        {
                            int id = rdr.GetInt32(0);
                            string name = rdr.IsDBNull(1) ? ("Company_" + id) : rdr.GetString(1);
                            companies[id] = name;
                            WriteLog(string.Format("[AesthetikContainers] Found company: '{0}' -> CompanyID={1}", name, id));
                        }
                    }
                }
                catch (Exception ex)
                {
                    WriteLog(string.Format("[AesthetikContainers] Company discovery failed: {0}", ex.Message));
                }
            }

            if (companies.Count == 0)
                WriteLog("[AesthetikContainers] WARNING: No companies found — SiteMap/seed data will not be created");

            return companies;
        }

        private void EnsureColumn(SqlConnection conn, string table, string column, string definition)
        {
            string sql = string.Format(
                "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('{0}') AND name = '{1}') " +
                "ALTER TABLE [{0}] ADD [{1}] {2};",
                table, column, definition);
            using (var cmd = new SqlCommand(sql, conn)) { cmd.ExecuteNonQuery(); }
            WriteLog(string.Format("  Column {0}.{1} — OK", table, column));
        }

        private void EnsureTable(SqlConnection conn, string table, string columnDefs)
        {
            string sql = string.Format(
                "IF OBJECT_ID('{0}', 'U') IS NULL CREATE TABLE [{0}] ({1});",
                table, columnDefs);
            using (var cmd = new SqlCommand(sql, conn)) { cmd.CommandTimeout = 60; cmd.ExecuteNonQuery(); }
            WriteLog(string.Format("  Table {0} — OK", table));
        }

        private void EnsureIndex(SqlConnection conn, string table, string indexName, string columns)
        {
            string sql = string.Format(
                "IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('{0}') AND name = '{1}') " +
                "CREATE NONCLUSTERED INDEX [{1}] ON [{0}] ({2});",
                table, indexName, columns);
            using (var cmd = new SqlCommand(sql, conn)) { cmd.ExecuteNonQuery(); }
            WriteLog(string.Format("  Index {0}.{1} — OK", table, indexName));
        }

        private void MigrateIGCMContainers(SqlConnection conn)
        {
            // Skip if IIG source table doesn't exist (already fully removed)
            string checkSql = "SELECT OBJECT_ID('IGCMPOLandedCost', 'U')";
            using (var cmd = new SqlCommand(checkSql, conn))
            {
                var result = cmd.ExecuteScalar();
                if (result == null || result == System.DBNull.Value)
                {
                    WriteLog("  IGCM migration: IGCMPOLandedCost table not found — skipping");
                    return;
                }
            }

            // Step 1: Migrate container headers
            string migrateHeaders = @"
                INSERT INTO UsrContainer (
                    CompanyID, ContainerCD, CarrierCode, BookingRef, Status,
                    CreatedByID, CreatedByScreenID, CreatedDateTime,
                    LastModifiedByID, LastModifiedByScreenID, LastModifiedDateTime
                )
                SELECT
                    c.CompanyID,
                    ISNULL(c.ContainerNbr, c.LandedCostNbr),
                    'OTHER',
                    c.LandedCostNbr,
                    CASE
                        WHEN c.Released = 1 THEN 'DELIVERED'
                        WHEN c.Hold = 1 THEN 'CUSTOMS_HOLD'
                        ELSE 'IN_TRANSIT'
                    END,
                    c.CreatedByID, c.CreatedByScreenID, c.CreatedDateTime,
                    c.LastModifiedByID, c.LastModifiedByScreenID, c.LastModifiedDateTime
                FROM IGCMPOLandedCost c
                WHERE NOT EXISTS (
                    SELECT 1 FROM UsrContainer u
                    WHERE u.CompanyID = c.CompanyID
                    AND u.ContainerCD = ISNULL(c.ContainerNbr, c.LandedCostNbr)
                )";
            using (var cmd = new SqlCommand(migrateHeaders, conn))
            {
                cmd.CommandTimeout = 120;
                int rows = cmd.ExecuteNonQuery();
                WriteLog(string.Format("  IGCM migration: {0} container headers migrated", rows));
            }

            // Step 2: Migrate PO links
            string migrateLinks = @"
                INSERT INTO UsrContainerPOLink (
                    CompanyID, ContainerID, OrderType, OrderNbr, LineNbr
                )
                SELECT DISTINCT
                    cl.CompanyID, u.ContainerID, cl.POOrderType, cl.PONbr, cl.POLineNbr
                FROM IGCMPOLandedCostLine cl
                INNER JOIN IGCMPOLandedCost c
                    ON cl.CompanyID = c.CompanyID AND cl.LandedCostNbr = c.LandedCostNbr
                INNER JOIN UsrContainer u
                    ON u.CompanyID = c.CompanyID AND u.ContainerCD = ISNULL(c.ContainerNbr, c.LandedCostNbr)
                WHERE cl.PONbr IS NOT NULL
                AND NOT EXISTS (
                    SELECT 1 FROM UsrContainerPOLink lk
                    WHERE lk.CompanyID = cl.CompanyID
                    AND lk.ContainerID = u.ContainerID
                    AND lk.OrderType = cl.POOrderType
                    AND lk.OrderNbr = cl.PONbr
                    AND ISNULL(lk.LineNbr, -1) = ISNULL(cl.POLineNbr, -1)
                )";
            using (var cmd = new SqlCommand(migrateLinks, conn))
            {
                cmd.CommandTimeout = 120;
                int rows = cmd.ExecuteNonQuery();
                WriteLog(string.Format("  IGCM migration: {0} PO links migrated", rows));
            }

            // Step 3: PO header UsrContainerRef backfill deferred —
            // UPDATE on POOrder is blocked by validate-project.py guard.
            // ContainerMaint graph sets UsrContainerRef on save.
            // Historical POs can be backfilled via SM302050 if needed.
        }

        // CleanupIGCMArtifacts and EnsureContainerTrackingGIs removed —
        // GIs are now created via XML files (GenericInquiryScreen_*.xml).
        // IGCM cleanup is no longer needed; the ISV artifacts are gone.
        private void EnsureContainerTrackingSiteMap(SqlConnection conn, int companyId)
        {
            // Step 1: Delete ALL non-whitelisted entries from the Container Tracking
            // workspace. IIG left behind SiteMap entries for IGCM screens that no longer
            // exist. Whitelist only our working form screens + Container Maintenance.
            string deleteOldEntries = @"
                DELETE FROM SiteMap
                WHERE CompanyID = @cid
                  AND ParentID = '9c89e3db-7c47-43c0-8554-5d2c9f2c0e87'
                  AND ScreenID NOT IN ('SB501000','SB302000','SB302010','SB302020','SB302030')";
            using (var cmd = new SqlCommand(deleteOldEntries, conn))
            {
                cmd.Parameters.AddWithValue("@cid", companyId);
                int rows = cmd.ExecuteNonQuery();
                if (rows > 0) WriteLog(string.Format("[AesthetikContainers] Cleaned {0} old IIG entries from Container Tracking workspace (CID={1})", rows, companyId));
            }

            // Step 2: Also clean IGCM-pattern SiteMap entries outside the workspace
            string deleteIgcmEntries = @"
                DELETE FROM SiteMap
                WHERE CompanyID = @cid
                  AND (ScreenID LIKE 'IGCM%' OR ScreenID LIKE 'IG.CM%')
                  AND ScreenID NOT IN ('SB501000','SB302000','SB302010','SB302020','SB302030')";
            using (var cmd = new SqlCommand(deleteIgcmEntries, conn))
            {
                cmd.Parameters.AddWithValue("@cid", companyId);
                int rows = cmd.ExecuteNonQuery();
                if (rows > 0) WriteLog(string.Format("[AesthetikContainers] Cleaned {0} IGCM SiteMap entries outside workspace (CID={1})", rows, companyId));
            }

            // Step 3: Upsert our 4 form screen entries
            string[][] entries = new[]
            {
                new[] { "SB302000", "Freight Forwarders", "~/Pages/SB/SB302000.aspx", "7.9" },
                new[] { "SB302010", "Container Types", "~/Pages/SB/SB302010.aspx", "8.2" },
                new[] { "SB302020", "Destinations/Ports", "~/Pages/SB/SB302020.aspx", "8.3" },
                new[] { "SB302030", "Container Preferences", "~/Pages/SB/SB302030.aspx", "8.4" },
            };

            foreach (var e in entries)
            {
                string sql = @"
                    IF EXISTS (SELECT 1 FROM SiteMap WHERE ScreenID = @sid AND CompanyID = @cid)
                        UPDATE SiteMap SET Url = @url, Title = @title, Position = @pos
                        WHERE ScreenID = @sid AND CompanyID = @cid;
                    ELSE
                        INSERT INTO SiteMap (CompanyID, NodeID, ScreenID, Title, Url, Position, ParentID, SelectedUI, CreatedByID, CreatedByScreenID, CreatedDateTime, LastModifiedByID, LastModifiedByScreenID, LastModifiedDateTime)
                        VALUES (@cid, NEWID(), @sid, @title, @url, @pos, '9c89e3db-7c47-43c0-8554-5d2c9f2c0e87', N'E', N'B5344897-037E-4D58-B5C3-1BDFD0F47BF4', N'SM208000', GETUTCDATE(), N'B5344897-037E-4D58-B5C3-1BDFD0F47BF4', N'SM208000', GETUTCDATE());";
                using (var cmd = new SqlCommand(sql, conn))
                {
                    cmd.Parameters.AddWithValue("@cid", companyId);
                    cmd.Parameters.AddWithValue("@sid", e[0]);
                    cmd.Parameters.AddWithValue("@title", e[1]);
                    cmd.Parameters.AddWithValue("@url", e[2]);
                    cmd.Parameters.AddWithValue("@pos", e[3]);
                    cmd.ExecuteNonQuery();
                }
            }
            WriteLog(string.Format("[AesthetikContainers] Container Tracking SiteMap (4 form screens) for CompanyID={0} — OK", companyId));
        }

        private void SeedContainerTypes(SqlConnection conn, int companyId)
        {
            var types = new (string cd, string desc, string l, string w, string h, string wt)[] {
                ("20GP", "20ft Standard", "20.0", "8.0", "8.5", "28200"),
                ("40GP", "40ft Standard", "40.0", "8.0", "8.5", "28800"),
                ("40HC", "40ft High Cube", "40.0", "8.0", "9.5", "28560"),
                ("45HC", "45ft High Cube", "45.0", "8.0", "9.5", "27600"),
                ("20RF", "20ft Reefer", "20.0", "8.0", "8.5", "27400"),
                ("40RF", "40ft Reefer", "40.0", "8.0", "8.5", "27700"),
            };
            foreach (var t in types)
            {
                string sql = @"
                    IF NOT EXISTS (SELECT 1 FROM UsrContainerType WHERE TypeCD = @cd AND CompanyID = @cid)
                    INSERT INTO UsrContainerType (CompanyID, TypeCD, Description, LengthFt, WidthFt, HeightFt, MaxWeightKg, Active)
                    VALUES (@cid, @cd, @desc, @l, @w, @h, @wt, 1);";
                using (var cmd = new SqlCommand(sql, conn))
                {
                    cmd.Parameters.AddWithValue("@cid", companyId);
                    cmd.Parameters.AddWithValue("@cd", t.cd);
                    cmd.Parameters.AddWithValue("@desc", t.desc);
                    cmd.Parameters.AddWithValue("@l", decimal.Parse(t.l));
                    cmd.Parameters.AddWithValue("@w", decimal.Parse(t.w));
                    cmd.Parameters.AddWithValue("@h", decimal.Parse(t.h));
                    cmd.Parameters.AddWithValue("@wt", decimal.Parse(t.wt));
                    cmd.ExecuteNonQuery();
                }
            }
            WriteLog(string.Format("[AesthetikContainers] Container Types seed for CompanyID={0} — OK", companyId));
        }

        private void SeedPorts(SqlConnection conn, int companyId)
        {
            var ports = new (string code, string name, string country)[] {
                ("CNSHA", "Shanghai", "CN"), ("CNYTN", "Yantian", "CN"), ("CNNGB", "Ningbo", "CN"),
                ("CNQIN", "Qingdao", "CN"), ("CNXMN", "Xiamen", "CN"), ("CNSZX", "Shenzhen", "CN"),
                ("HKHKG", "Hong Kong", "HK"), ("VNSGN", "Ho Chi Minh City", "VN"), ("VNHPH", "Haiphong", "VN"),
                ("IDSUB", "Surabaya", "ID"), ("INMAA", "Chennai", "IN"), ("INBOM", "Mumbai", "IN"),
                ("TWKHH", "Kaohsiung", "TW"), ("USLAX", "Los Angeles", "US"), ("USLGB", "Long Beach", "US"),
                ("USSAV", "Savannah", "US"), ("USNYC", "New York", "US"), ("USNWK", "Newark", "US"),
                ("USCHI", "Chicago", "US"), ("USHOU", "Houston", "US"),
            };
            foreach (var p in ports)
            {
                string sql = @"
                    IF NOT EXISTS (SELECT 1 FROM UsrPort WHERE PortCode = @code AND CompanyID = @cid)
                    INSERT INTO UsrPort (CompanyID, PortCode, PortName, Country, Active)
                    VALUES (@cid, @code, @name, @country, 1);";
                using (var cmd = new SqlCommand(sql, conn))
                {
                    cmd.Parameters.AddWithValue("@cid", companyId);
                    cmd.Parameters.AddWithValue("@code", p.code);
                    cmd.Parameters.AddWithValue("@name", p.name);
                    cmd.Parameters.AddWithValue("@country", p.country);
                    cmd.ExecuteNonQuery();
                }
            }
            WriteLog(string.Format("[AesthetikContainers] Ports seed for CompanyID={0} — OK", companyId));
        }

        private void SeedContainerPreferences(SqlConnection conn, int companyId)
        {
            string sql = @"
                IF NOT EXISTS (SELECT 1 FROM UsrContainerPrefs WHERE CompanyID = @cid)
                INSERT INTO UsrContainerPrefs (CompanyID, PrefsID, AutoLinkPOsByRef, TrackingPollIntervalHours)
                VALUES (@cid, 1, 1, 24);";
            using (var cmd = new SqlCommand(sql, conn))
            {
                cmd.Parameters.AddWithValue("@cid", companyId);
                cmd.ExecuteNonQuery();
            }
            WriteLog(string.Format("[AesthetikContainers] Container Preferences default for CompanyID={0} — OK", companyId));
        }
    }
}
