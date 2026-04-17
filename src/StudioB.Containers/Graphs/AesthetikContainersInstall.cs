using System;
using System.Collections.Generic;
using System.Configuration;
using System.Data.SqlClient;
using Customization;
using PX.Data;
using PX.Objects.IN;

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

                    // 2026-04-12: IIG parity date fields (PR #366)
                    EnsureColumn(conn, "UsrContainer", "DrayageAppointmentDate", "datetime NULL");
                    EnsureColumn(conn, "UsrContainer", "ShipmentWindowStart",    "datetime NULL");
                    EnsureColumn(conn, "UsrContainer", "ShipmentWindowEnd",      "datetime NULL");
                    EnsureColumn(conn, "UsrContainer", "DeliveryOrderNbr",       "nvarchar(30) NULL");
                    EnsureColumn(conn, "UsrContainer", "DeliveryOrderDate",      "datetime NULL");
                    EnsureColumn(conn, "UsrContainer", "OnBoardDate",            "datetime NULL");
                    EnsureColumn(conn, "UsrContainer", "FactoryPickupDate",      "datetime NULL");
                    EnsureColumn(conn, "UsrContainer", "CargoReadyDate",         "datetime NULL");
                    EnsureColumn(conn, "UsrContainer", "PaymentDueDate",         "datetime NULL");
                    EnsureColumn(conn, "UsrContainer", "BrokerInvoiceNbr",       "nvarchar(30) NULL");
                    EnsureColumn(conn, "UsrContainer", "SCACNumber",             "nvarchar(10) NULL");
                    EnsureColumn(conn, "UsrContainer", "EstimatedFreight",       "decimal(19,4) NULL");

                    // 2026-04-11: PCC redesign — mill date fields
                    EnsureColumn(conn, "UsrContainer", "MillAckDate",          "datetime NULL");
                    EnsureColumn(conn, "UsrContainer", "FactoryPromisedDate",  "datetime NULL");
                    EnsureColumn(conn, "UsrContainer", "FactoryActualDate",    "datetime NULL");

                    // 2026-04-12: PCC usability — receipt tracking
                    EnsureColumn(conn, "UsrContainer", "ReceiptNbr", "nvarchar(30) NULL");

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
                    EnsureColumn(conn, "InventoryItem", "UsrCbmPerUnit", "decimal(25,6) NULL");

                    // ── POReceiptLine landed cost fields ───────────────────────
                    EnsureColumn(conn, "POReceiptLine", "UsrActualDutyAmt", "decimal(25,4) NULL");
                    EnsureColumn(conn, "POReceiptLine", "UsrActualFreightAmt", "decimal(25,4) NULL");
                    EnsureColumn(conn, "POReceiptLine", "UsrBrokerageAmt", "decimal(25,4) NULL");

                    // ── POOrder DRP Phase 0 lead-time tracking fields ──────────
                    // UsrAcknowledgedDate / UsrFactoryReadyDate populated by
                    // vendor acknowledgment email watcher (webhook-router)
                    // and by Vendor Planning Hub manual entry. Consumed by
                    // drp_lead_time_samples → vendor lead-time learning.
                    // See docs/plans/2026-04-09-drp-implementation-design.md §4.2.
                    // POLine / POOrder arrival date + container ref fields — pre-existing
                    // columns from IIG migration. EnsureColumn is idempotent (IF NOT EXISTS).
                    EnsureColumn(conn, "POLine",  "UsrExpArrivalDate", "datetime NULL");
                    EnsureColumn(conn, "POLine",  "UsrActArrivalDate", "datetime NULL");
                    EnsureColumn(conn, "POOrder", "UsrExpArrivalDate", "datetime NULL");
                    EnsureColumn(conn, "POOrder", "UsrActArrivalDate", "datetime NULL");
                    EnsureColumn(conn, "POOrder", "UsrContainerRef",   "nvarchar(50) NULL");
                    EnsureColumn(conn, "POOrder", "UsrAcknowledgedDate", "datetime NULL");
                    EnsureColumn(conn, "POOrder", "UsrFactoryReadyDate", "datetime NULL");

                    // ── BAccount vendor defaults ─────────────────────────────
                    EnsureColumn(conn, "BAccount", "UsrDefaultInTransitSiteID", "int NULL");
                    EnsureColumn(conn, "BAccount", "UsrDefaultCarrierCode",     "nvarchar(20) NULL");

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

                    // ── Per-company DML (SiteMap, seed data) ──────
                    // DRP GIs are installed via <GenericInquiryScreen> XML blocks
                    // in project.xml (Acumatica-native path with RolesInGraph inside
                    // each GI's SiteMap row per CLAUDE.md rule 17).
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

                        try { EnsureItemUomConsistency(conn, companyId); }
                        catch (Exception ex) { WriteLog(string.Format("[AesthetikContainers] EnsureItemUomConsistency failed CID={0}: {1}", companyId, ex.Message)); }

                        try { SeedContainerTypes(conn, companyId); }
                        catch (Exception ex) { WriteLog(string.Format("[AesthetikContainers] Seed types failed CID={0}: {1}", companyId, ex.Message)); }

                        try { SeedPorts(conn, companyId); }
                        catch (Exception ex) { WriteLog(string.Format("[AesthetikContainers] Seed ports failed CID={0}: {1}", companyId, ex.Message)); }

                        try { SeedContainerPreferences(conn, companyId); }
                        catch (Exception ex) { WriteLog(string.Format("[AesthetikContainers] Seed prefs failed CID={0}: {1}", companyId, ex.Message)); }

                        // ── DRP GI orphan cleanup (2026-04-17 hotfix) ──
                        // Removes partial/stale GIDesign + child rows left by
                        // PR #427/#430/#431's failed DRP GI install attempts on
                        // 2026-04-16. Canonical DesignIDs are owned by PR #445's
                        // <GenericInquiryScreen> XML blocks; anything matching a
                        // DRP name but a different DesignID is stale residue.
                        // See docs/AAR-2026-04-17-custproject-nre-transient.md.
                        try { CleanupOrphanDRPGIRows(conn, companyId); }
                        catch (Exception ex) { WriteLog(string.Format("[AesthetikContainers] DRP orphan cleanup failed CID={0}: {1}", companyId, ex.Message)); }
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
                  AND ScreenID NOT IN ('SB501000','SB501200','SB302000','SB302010','SB302020','SB302030')";
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
                  AND ScreenID NOT IN ('SB501000','SB501200','SB302000','SB302010','SB302020','SB302030')";
            using (var cmd = new SqlCommand(deleteIgcmEntries, conn))
            {
                cmd.Parameters.AddWithValue("@cid", companyId);
                int rows = cmd.ExecuteNonQuery();
                if (rows > 0) WriteLog(string.Format("[AesthetikContainers] Cleaned {0} IGCM SiteMap entries outside workspace (CID={1})", rows, companyId));
            }

            // Step 3: Upsert our 5 form screen entries
            // 2026-04-15: Added SB501200 (Supplier Intake) — was missing from
            // the whitelist DELETE + upsert, so the project.xml SiteMap row was
            // wiped on every publish. Symptom: SB501200 returned the
            // "screen not registered" stub <script>window.open("/Main","_top")
            // </script> instead of the page, breaking
            // tests/ui/test_container_tracking.py::TestSB501200.
            string[][] entries = new[]
            {
                new[] { "SB302000", "Freight Forwarders", "~/Pages/SB/SB302000.aspx", "7.9" },
                new[] { "SB302010", "Container Types", "~/Pages/SB/SB302010.aspx", "8.2" },
                new[] { "SB302020", "Destinations/Ports", "~/Pages/SB/SB302020.aspx", "8.3" },
                new[] { "SB302030", "Container Preferences", "~/Pages/SB/SB302030.aspx", "8.4" },
                new[] { "SB501200", "Supplier Intake", "~/Pages/SB/SB501200.aspx", "8.6" },
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
            WriteLog(string.Format("[AesthetikContainers] Container Tracking SiteMap (5 form screens) for CompanyID={0} — OK", companyId));
        }

        // DRP GIs are installed via <GenericInquiryScreen> XML blocks in
        // project.xml. Each block carries RolesInGraph Rolename="*"
        // Accessrights="4" inside its own <SiteMap>/<row> per rule 17 and
        // a matching <row> in <ScreenWithRights> to grant OData access.

        // ── EnsureItemUomConsistency ────────────────────────────────────────
        // 2026-04-09 rewrite (supersedes PR #292/#299/#301/#302, closes PR #304).
        //
        // Targets Class B corruption: stale INUnit rows on YDS-base items
        // where FromUnit or ToUnit is still 'PIECE' from pre-migration days.
        // These rows are INVISIBLE to both REST StockItem.UOMConversions and
        // the IN202500 UI grid (filtered out before reaching the client), but
        // INUnitAttribute.UnitVerifying sees them on Save and throws:
        //
        //     "The PIECE value specified in the To Unit box differs from
        //      the YDS base unit specified for the <item> item."
        //
        // Reproduced 2026-04-09 on prod item 00006 via Playwright UI click-
        // Save with a dialog listener (REST PUT does NOT trigger the
        // validator — which is why every previous gate was false-green).
        // Heritage Test tenant (CompanyID=3) reproduces identically.
        //
        // Why prior PRs all missed this:
        //   PR #292/#299 — INSERT INTO INUnit with hardcoded CompanyMask=1
        //     (invisible rows). Added rows alongside the stale ones. The
        //     validator errors on the first bad row it finds, so adding a
        //     good row doesn't suppress the error.
        //   PR #301 — Source CompanyMask from (PIECE,PIECE) seed row.
        //     Failed on items without that seed row.
        //   PR #302 — Source CompanyMask from InventoryItem.CompanyMask.
        //     InventoryItem has no CompanyMask column in 24.208 → Step 1
        //     throws "Invalid column name", Step 2 never runs.
        //   PR #304 — PXDatabase.Insert only. Still just adding new rows
        //     alongside the stale ones. Does not touch the validator's
        //     actual target.
        //
        // The fix — three phases:
        //
        //   Phase A (always runs) — Pre-scan and log row counts per company.
        //                            Pure read. Four counters split by shape.
        //   Phase B (always runs) — Enumerate each affected (InventoryID,
        //                            FromUnit, ToUnit) triple and log it.
        //                            Capped at 500 rows per company to keep
        //                            the publish log bounded.
        //   Phase C (LIVE mode only) —
        //     C1: UPDATE ToUnit='PIECE' → 'YDS' where no unique-key collision
        //         (NOT EXISTS guard on the target key). Renames YDS→PIECE
        //         to YDS→YDS (the canonical self-conversion).
        //     C2: UPDATE FromUnit='PIECE' → 'YDS' similarly.
        //     C3: DELETE any remaining (FromUnit='PIECE' OR ToUnit='PIECE')
        //         rows on YDS-base items. These are rows that could not be
        //         renamed because of a collision, plus (PIECE,PIECE) self-
        //         convs that don't fit either update. Provably junk: the
        //         owning item is YDS-base, the row references PIECE, no
        //         valid save path needs such a row.
        //
        // Scope guard:
        //   Only CompanyID ∈ {2, 3} — Heritage Fabrics prod + Heritage Test.
        //   Any other company is skipped with a log line.
        //
        // DRY_RUN compile-time const:
        //   true  → Phase A+B only. No writes. Use this for the first deploy
        //           to get the exact row counts without touching data.
        //   false → Phase A+B+C. Use this for the second deploy after the
        //           dry-run counts have been manually verified.
        //
        // Phase C3 DELETE requires the "-- REVIEWED: inunit-sql-safe" marker
        // to bypass validate-project.py's INUnit guard (banned by default
        // because of the 2026-03-29 P0 outage). This specific delete is
        // authorized for this incident (Kevin, 2026-04-09).
        //
        // Exceptions per company are caught by the outer try/catch in the
        // DiscoverCompanies loop, so one bad CompanyID doesn't abort others.
        private void EnsureItemUomConsistency(SqlConnection conn, int companyId)
        {
            // ⚠ Flip to false for the LIVE deploy on the second CI run.
            const bool DRY_RUN = false;

            // Scope guard — only target Heritage Fabrics (2) and Heritage Test (3).
            if (companyId != 2 && companyId != 3)
            {
                WriteLog(string.Format(
                    "[AesthetikContainers] EnsureItemUomConsistency CID={0} SKIP — out of scope (only 2/3)",
                    companyId));
                return;
            }

            WriteLog(string.Format(
                "[AesthetikContainers] EnsureItemUomConsistency CID={0} START mode={1}",
                companyId, DRY_RUN ? "DRY_RUN" : "LIVE"));

            // ── Phase A — Pre-scan counts ──
            string scanSql = @"
                SELECT
                    SUM(CASE WHEN u.ToUnit = 'PIECE' AND u.FromUnit <> 'PIECE' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN u.FromUnit = 'PIECE' AND u.ToUnit <> 'PIECE' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN u.FromUnit = 'PIECE' AND u.ToUnit = 'PIECE' THEN 1 ELSE 0 END),
                    COUNT(*)
                FROM INUnit u
                INNER JOIN InventoryItem i
                    ON i.CompanyID = u.CompanyID
                   AND i.InventoryID = u.InventoryID
                WHERE u.CompanyID = @cid
                  AND u.UnitType = 1
                  AND u.ItemClassID = 0
                  AND i.BaseUnit = 'YDS'
                  AND (u.FromUnit = 'PIECE' OR u.ToUnit = 'PIECE');";

            int cntToPiece = 0, cntFromPiece = 0, cntBothPiece = 0, cntTotal = 0;
            using (var cmd = new SqlCommand(scanSql, conn))
            {
                cmd.Parameters.AddWithValue("@cid", companyId);
                using (var rdr = cmd.ExecuteReader())
                {
                    if (rdr.Read())
                    {
                        cntToPiece   = rdr.IsDBNull(0) ? 0 : rdr.GetInt32(0);
                        cntFromPiece = rdr.IsDBNull(1) ? 0 : rdr.GetInt32(1);
                        cntBothPiece = rdr.IsDBNull(2) ? 0 : rdr.GetInt32(2);
                        cntTotal     = rdr.IsDBNull(3) ? 0 : rdr.GetInt32(3);
                    }
                }
            }

            WriteLog(string.Format(
                "[AesthetikContainers] EnsureItemUomConsistency CID={0} SCAN: " +
                "total_piece_rows_on_yds_items={1}, " +
                "ToUnit='PIECE' only={2}, FromUnit='PIECE' only={3}, both='PIECE'={4}",
                companyId, cntTotal, cntToPiece, cntFromPiece, cntBothPiece));

            if (cntTotal == 0)
            {
                WriteLog(string.Format(
                    "[AesthetikContainers] EnsureItemUomConsistency CID={0} CLEAN — nothing to fix",
                    companyId));
                return;
            }

            // ── Phase B — List each affected row (bounded at 500) ──
            string listSql = @"
                SELECT TOP 500
                    u.InventoryID, u.FromUnit, u.ToUnit, u.UnitRate
                FROM INUnit u
                INNER JOIN InventoryItem i
                    ON i.CompanyID = u.CompanyID
                   AND i.InventoryID = u.InventoryID
                WHERE u.CompanyID = @cid
                  AND u.UnitType = 1
                  AND u.ItemClassID = 0
                  AND i.BaseUnit = 'YDS'
                  AND (u.FromUnit = 'PIECE' OR u.ToUnit = 'PIECE')
                ORDER BY u.InventoryID;";

            using (var cmd = new SqlCommand(listSql, conn))
            {
                cmd.Parameters.AddWithValue("@cid", companyId);
                using (var rdr = cmd.ExecuteReader())
                {
                    while (rdr.Read())
                    {
                        WriteLog(string.Format(
                            "[AesthetikContainers] CID={0} stale row: InventoryID={1} FromUnit={2} ToUnit={3} UnitRate={4}",
                            companyId,
                            rdr.GetInt32(0),
                            rdr.GetString(1),
                            rdr.GetString(2),
                            rdr.GetDecimal(3)));
                    }
                }
            }

            if (DRY_RUN)
            {
                WriteLog(string.Format(
                    "[AesthetikContainers] EnsureItemUomConsistency CID={0} DRY_RUN=true — Phase C skipped. " +
                    "Flip DRY_RUN to false and re-deploy to apply the fix.",
                    companyId));
                return;
            }

            // ── Phase C — Fix rows (LIVE mode only) ──

            const string systemUserId = "B5344897-037E-4D58-B5C3-1BDFD0F47BF4";
            const string customizationScreenId = "SM208000";

            // C1) Rename YDS→PIECE to YDS→YDS where no collision exists.
            string updateToSql = @"
                UPDATE u
                SET u.ToUnit = 'YDS',
                    u.LastModifiedByID = @user,
                    u.LastModifiedByScreenID = @screen,
                    u.LastModifiedDateTime = GETUTCDATE()
                FROM INUnit u
                INNER JOIN InventoryItem i
                    ON i.CompanyID = u.CompanyID
                   AND i.InventoryID = u.InventoryID
                WHERE u.CompanyID = @cid
                  AND u.UnitType = 1
                  AND u.ItemClassID = 0
                  AND u.ToUnit = 'PIECE'
                  AND u.FromUnit <> 'PIECE'
                  AND i.BaseUnit = 'YDS'
                  AND NOT EXISTS (
                      SELECT 1 FROM INUnit dst
                      WHERE dst.CompanyID  = u.CompanyID
                        AND dst.UnitType   = 1
                        AND dst.ItemClassID= 0
                        AND dst.InventoryID= u.InventoryID
                        AND dst.FromUnit   = u.FromUnit
                        AND dst.ToUnit     = 'YDS'
                  );";
            int updatedTo = ExecInUnitWrite(conn, updateToSql, companyId, systemUserId, customizationScreenId);

            // C2) Rename PIECE→YDS to YDS→YDS where no collision exists.
            string updateFromSql = @"
                UPDATE u
                SET u.FromUnit = 'YDS',
                    u.LastModifiedByID = @user,
                    u.LastModifiedByScreenID = @screen,
                    u.LastModifiedDateTime = GETUTCDATE()
                FROM INUnit u
                INNER JOIN InventoryItem i
                    ON i.CompanyID = u.CompanyID
                   AND i.InventoryID = u.InventoryID
                WHERE u.CompanyID = @cid
                  AND u.UnitType = 1
                  AND u.ItemClassID = 0
                  AND u.FromUnit = 'PIECE'
                  AND u.ToUnit <> 'PIECE'
                  AND i.BaseUnit = 'YDS'
                  AND NOT EXISTS (
                      SELECT 1 FROM INUnit dst
                      WHERE dst.CompanyID  = u.CompanyID
                        AND dst.UnitType   = 1
                        AND dst.ItemClassID= 0
                        AND dst.InventoryID= u.InventoryID
                        AND dst.FromUnit   = 'YDS'
                        AND dst.ToUnit     = u.ToUnit
                  );";
            int updatedFrom = ExecInUnitWrite(conn, updateFromSql, companyId, systemUserId, customizationScreenId);

            // C3) DELETE residuals — provably junk. Marker required by guard.
            string deleteResidualSql = @"
                -- REVIEWED: inunit-sql-safe
                DELETE u
                FROM INUnit u
                INNER JOIN InventoryItem i
                    ON i.CompanyID = u.CompanyID
                   AND i.InventoryID = u.InventoryID
                WHERE u.CompanyID = @cid
                  AND u.UnitType = 1
                  AND u.ItemClassID = 0
                  AND (u.FromUnit = 'PIECE' OR u.ToUnit = 'PIECE')
                  AND i.BaseUnit = 'YDS';";
            int deleted = ExecInUnitWrite(conn, deleteResidualSql, companyId, systemUserId, customizationScreenId);

            WriteLog(string.Format(
                "[AesthetikContainers] EnsureItemUomConsistency CID={0} LIVE done: " +
                "updated ToUnit→YDS={1} (scan saw {2}), " +
                "updated FromUnit→YDS={3} (scan saw {4}), " +
                "deleted residuals={5}",
                companyId, updatedTo, cntToPiece, updatedFrom, cntFromPiece, deleted));
        }

        private int ExecInUnitWrite(SqlConnection conn, string sql, int cid, string userGuid, string screen)
        {
            using (var cmd = new SqlCommand(sql, conn))
            {
                cmd.Parameters.AddWithValue("@cid",    cid);
                cmd.Parameters.AddWithValue("@user",   new Guid(userGuid));
                cmd.Parameters.AddWithValue("@screen", screen);
                return cmd.ExecuteNonQuery();
            }
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

        // ── DRP GI orphan cleanup (2026-04-17 hotfix) ─────────────────────────
        //
        // Removes stale GIDesign + 8 child-table rows for the five DRP Phase 0
        // GIs whose DesignIDs don't match the canonical values owned by PR #445's
        // <GenericInquiryScreen> XML blocks in this project.xml. Pattern copied
        // from the proven 2026-03-29 UserAuditTrail cleanup (commit ab35a0d)
        // which resolved a 45-min GI-brick outage.
        //
        // Hard-codes eight DELETE statements (one per child table) instead of
        // a loop over a string[] so the validator's "DELETE FROM <literal>"
        // table-name extractor captures each table correctly. All nine targets
        // are in validate-project.py's SAFE_DELETE_TABLES allowlist.
        //
        // Idempotent: after the first run deletes the residue, subsequent
        // calls find zero stale rows and exit in a few ms. Safe to run on
        // every publish.
        //
        // -- REVIEWED: gi-sql-safe
        private static readonly System.Collections.Generic.Dictionary<string, Guid> DRPCanonDesigns =
            new System.Collections.Generic.Dictionary<string, Guid>(StringComparer.Ordinal)
        {
            { "DRP_VelocityHistory",       new Guid("52ebcf52-7256-47d9-9256-974a33660702") },
            { "DRP_OpenSOCommitments",     new Guid("8771befb-f3d9-4c14-8898-e9b1f249addc") },
            { "DRP_InventoryBySite",       new Guid("b6cadfdd-f802-4456-8a7a-9f52dc271145") },
            { "DRP_OpenPOLines",           new Guid("263148fc-5b6a-4312-8c45-6e590415ea3a") },
            { "DRP_ItemWarehouseSettings", new Guid("969bfd48-5eaa-470a-b806-4bb46cf494d6") },
        };

        private void CleanupOrphanDRPGIRows(SqlConnection conn, int companyId)
        {
            var stale = new System.Collections.Generic.List<System.Collections.Generic.KeyValuePair<string, Guid>>();
            using (var cmd = new SqlCommand(
                "SELECT Name, DesignID FROM GIDesign " +
                "WHERE CompanyID = @CID " +
                "  AND Name IN ('DRP_VelocityHistory', 'DRP_OpenSOCommitments', " +
                "               'DRP_InventoryBySite', 'DRP_OpenPOLines', " +
                "               'DRP_ItemWarehouseSettings')", conn))
            {
                cmd.Parameters.AddWithValue("@CID", companyId);
                using (var rdr = cmd.ExecuteReader())
                {
                    while (rdr.Read())
                    {
                        var name = rdr.GetString(0);
                        var id = rdr.GetGuid(1);
                        Guid canon;
                        if (DRPCanonDesigns.TryGetValue(name, out canon) && id == canon) continue;
                        stale.Add(new System.Collections.Generic.KeyValuePair<string, Guid>(name, id));
                    }
                }
            }

            if (stale.Count == 0)
            {
                WriteLog(string.Format("[AesthetikContainers] DRP GI orphan scan CID={0} — clean (0 stale)", companyId));
                return;
            }

            WriteLog(string.Format("[AesthetikContainers] DRP GI orphan scan CID={0} — {1} stale row(s)", companyId, stale.Count));
            foreach (var s in stale)
                WriteLog(string.Format("    stale: {0} @ {1}", s.Key, s.Value));

            int total = 0;
            using (var tx = conn.BeginTransaction())
            {
                try
                {
                    foreach (var s in stale)
                    {
                        total += DeleteOrphanGIRow(conn, tx, "DELETE FROM GITable    WHERE DesignID = @ID AND CompanyID = @CID", "GITable",    s, companyId);
                        total += DeleteOrphanGIRow(conn, tx, "DELETE FROM GIResult   WHERE DesignID = @ID AND CompanyID = @CID", "GIResult",   s, companyId);
                        total += DeleteOrphanGIRow(conn, tx, "DELETE FROM GIWhere    WHERE DesignID = @ID AND CompanyID = @CID", "GIWhere",    s, companyId);
                        total += DeleteOrphanGIRow(conn, tx, "DELETE FROM GISort     WHERE DesignID = @ID AND CompanyID = @CID", "GISort",     s, companyId);
                        total += DeleteOrphanGIRow(conn, tx, "DELETE FROM GIFilter   WHERE DesignID = @ID AND CompanyID = @CID", "GIFilter",   s, companyId);
                        total += DeleteOrphanGIRow(conn, tx, "DELETE FROM GIRelation WHERE DesignID = @ID AND CompanyID = @CID", "GIRelation", s, companyId);
                        total += DeleteOrphanGIRow(conn, tx, "DELETE FROM GIOn       WHERE DesignID = @ID AND CompanyID = @CID", "GIOn",       s, companyId);
                        total += DeleteOrphanGIRow(conn, tx, "DELETE FROM GIGroupBy  WHERE DesignID = @ID AND CompanyID = @CID", "GIGroupBy",  s, companyId);
                        total += DeleteOrphanGIRow(conn, tx, "DELETE FROM GIDesign   WHERE DesignID = @ID AND CompanyID = @CID", "GIDesign",   s, companyId);
                    }
                    tx.Commit();
                }
                catch
                {
                    tx.Rollback();
                    throw;
                }
            }
            WriteLog(string.Format("[AesthetikContainers] DRP GI orphan cleanup CID={0} — committed {1} row deletions", companyId, total));
        }

        private int DeleteOrphanGIRow(SqlConnection conn, SqlTransaction tx, string sql, string label,
                                      System.Collections.Generic.KeyValuePair<string, Guid> s, int companyId)
        {
            using (var cmd = new SqlCommand(sql, conn, tx))
            {
                cmd.Parameters.AddWithValue("@ID", s.Value);
                cmd.Parameters.AddWithValue("@CID", companyId);
                var n = cmd.ExecuteNonQuery();
                if (n > 0)
                    WriteLog(string.Format("        deleted {0} from {1} for {2}", n, label, s.Key));
                return n;
            }
        }

    }
}
