// =============================================================================
// ShipmentLabelAutoPrint.cs
// Heritage Fabrics / Studio B — Acumatica 24.208 Customization
//
// PURPOSE:
//   Graph extension for SOShipmentEntry (SO302000) that automatically queues
//   a 4×6 box-label print job via Device Hub whenever a shipment transitions
//   to the "Committed" WMS pick status while the shipment is also Confirmed.
//
// TRIGGER CONDITION (all three must be true simultaneously):
//   1. SOShipment.UsrFRPickStatus changes TO "C" (Committed)
//   2. SOShipment.Status == "N" (Confirmed)
//   3. UsrBoxLabelPrinted has not already been set (idempotency guard)
//
// DEVICE HUB APPROACH:
//   Acumatica's Device Hub print pipeline is accessed through SMPrintJobMaint.
//   Each print job targets report ID "BoxLabel4x6" and carries two report
//   parameters: ShipmentNbr and PackageLineNbr. One job is queued per
//   SOPackageDetailEx row. The printer name is resolved in priority order:
//     1. UserPreferences.PrinterName (per-user Device Hub printer)
//     2. Falls back gracefully with a logged warning if no printer is found.
//
// IDEMPOTENCY:
//   UsrBoxLabelPrinted (DAC extension bool, persisted) is set to true after
//   all jobs are queued. Subsequent RowUpdated calls that still see Status=N
//   and PickStatus=C will be no-ops. The field is reset to false when a
//   shipment is re-opened (RowUpdated: Status changes away from N).
//
// ERROR HANDLING:
//   All Device Hub calls are wrapped in try/catch. Failures log a PXTrace
//   warning and set a non-blocking PXSetPropertyException on the screen so
//   the warehouse user can see the issue without having the shipment workflow
//   interrupted.
// =============================================================================

using System;
using System.Collections.Generic;
using PX.Data;
using PX.Data.BQL;
using PX.Data.BQL.Fluent;
using PX.Objects.SO;
using PX.Objects.CS;
using PX.SM;

namespace HeritageFabrics.SO
{
    // =========================================================================
    // SECTION 1 — DAC Extension: adds UsrBoxLabelPrinted to SOShipment
    //
    // This persisted boolean is the idempotency guard. It prevents duplicate
    // label queuing if the RowUpdated event fires more than once while the
    // shipment remains in Confirmed+Committed state (e.g. user saves twice,
    // or a background process re-saves the record).
    //
    // SQL: the SchemaInstaller below creates the column on first publish.
    // =========================================================================
    public sealed class SOShipmentLabelExt : PXCacheExtension<SOShipment>
    {
        public static bool IsActive() => true;

        #region UsrBoxLabelPrinted
        /// <summary>
        /// True once box-label print jobs have been successfully queued for
        /// this shipment. Prevents duplicate label printing on re-save.
        /// Reset to false if the shipment is re-opened (status leaves 'N').
        /// </summary>
        public abstract class usrBoxLabelPrinted : BqlBool.Field<usrBoxLabelPrinted> { }

        [PXDBBool]
        [PXDefault(false, PersistingCheck = PXPersistingCheck.Nothing)]
        [PXUIField(DisplayName = "Box Labels Printed", Enabled = false, Visibility = PXUIVisibility.SelectorVisible)]
        public bool? UsrBoxLabelPrinted { get; set; }
        #endregion
    }

    // =========================================================================
    // SECTION 2 — Graph Extension: SOShipmentEntry_LabelAutoPrint
    //
    // Extends SOShipmentEntry (SO302000). All logic lives in RowUpdated so it
    // fires after the cache has accepted the new field values but before the
    // record is persisted — giving us a clean window to queue print jobs and
    // flip UsrBoxLabelPrinted in the same database transaction.
    // =========================================================================
    public class SOShipmentEntry_LabelAutoPrint : PXGraphExtension<SOShipmentEntry>
    {
        // The report ID registered in Acumatica's report designer.
        // Must match the Report ID field on the Report Designer (SM208000) exactly.
        private const string BOX_LABEL_REPORT_ID = "BoxLabel4x6";

        // SOShipmentStatus.Confirmed == "N"  (Acumatica constant)
        private const string STATUS_CONFIRMED = "N";

        // Kensium WMS "Committed" pick status value
        private const string PICK_STATUS_COMMITTED = "C";

        public static bool IsActive() => true;

        // -----------------------------------------------------------------
        // RowUpdated — fires each time the SOShipment row changes in cache.
        //
        // We use the generic event delegate syntax (Events.RowUpdated<T>)
        // which is the preferred pattern across this codebase (see existing
        // POOrderEntry_Extension, etc.) and guarantees the handler wires up
        // correctly for DAC extension fields.
        // -----------------------------------------------------------------
        protected void _(Events.RowUpdated<SOShipment> e)
        {
            // Guard: must have both old and new rows
            if (e.Row == null || e.OldRow == null) return;

            SOShipment newRow = e.Row;
            SOShipment oldRow = e.OldRow;

            // ------------------------------------------------------------------
            // Gate 1 — Shipment must be in Confirmed status ('N').
            //          If it's not confirmed we have nothing to print yet.
            // ------------------------------------------------------------------
            if (newRow.Status != STATUS_CONFIRMED) 
            {
                // Reset the label-printed flag if the shipment leaves Confirmed
                // so that if it's re-confirmed later labels will re-queue.
                SOShipmentLabelExt ext = newRow.GetExtension<SOShipmentLabelExt>();
                if (ext?.UsrBoxLabelPrinted == true)
                {
                    e.Cache.SetValueExt<SOShipmentLabelExt.usrBoxLabelPrinted>(newRow, false);
                }
                return;
            }

            // ------------------------------------------------------------------
            // Gate 2 — Pick status must have just transitioned TO 'C'.
            //          We check that the NEW value is 'C' and the OLD value
            //          was NOT 'C', preventing re-triggering on unrelated saves.
            // ------------------------------------------------------------------
            // UsrFRPickStatus lives in the Kensium-supplied DAC extension.
            // We access it via the generic GetExtension pattern to keep this
            // code decoupled from the Kensium assembly's concrete type name.
            string newPickStatus = GetPickStatus(e.Cache, newRow);
            string oldPickStatus = GetPickStatus(e.Cache, oldRow);

            bool pickStatusJustCommitted =
                string.Equals(newPickStatus, PICK_STATUS_COMMITTED, StringComparison.Ordinal) &&
                !string.Equals(oldPickStatus, PICK_STATUS_COMMITTED, StringComparison.Ordinal);

            if (!pickStatusJustCommitted) return;

            // ------------------------------------------------------------------
            // Gate 3 — Idempotency check: labels not already printed.
            // ------------------------------------------------------------------
            SOShipmentLabelExt labelExt = newRow.GetExtension<SOShipmentLabelExt>();
            if (labelExt?.UsrBoxLabelPrinted == true)
            {
                // Labels were already queued for this shipment; skip silently.
                PXTrace.WriteInformation(
                    $"[BoxLabel] Shipment {newRow.ShipmentNbr}: labels already printed — skipping.");
                return;
            }

            // ------------------------------------------------------------------
            // All gates passed — queue print jobs for every package.
            // ------------------------------------------------------------------
            QueueBoxLabelPrintJobs(e.Cache, newRow);
        }

        // -----------------------------------------------------------------
        // QueueBoxLabelPrintJobs
        //
        // Queries all SOPackageDetailEx rows for the shipment, resolves the
        // configured printer, and submits one SMPrintJob per package through
        // the SMPrintJobMaint graph. On success it marks UsrBoxLabelPrinted.
        // -----------------------------------------------------------------
        private void QueueBoxLabelPrintJobs(PXCache shipmentCache, SOShipment shipment)
        {
            string shipmentNbr = shipment.ShipmentNbr;

            try
            {
                // ── Step 1: Collect all packages for this shipment ────────────
                // SOPackageDetailEx is the extended package table used in SO302000.
                // We use PXSelect rather than a view because we are inside a graph
                // extension and want a fresh, unbuffered result set.
                List<SOPackageDetailEx> packages = new List<SOPackageDetailEx>();

                foreach (SOPackageDetailEx pkg in PXSelect<
                    SOPackageDetailEx,
                    Where<SOPackageDetailEx.shipmentNbr,
                          Equal<Required<SOPackageDetailEx.shipmentNbr>>>>
                    .Select(Base, shipmentNbr))
                {
                    packages.Add(pkg);
                }

                if (packages.Count == 0)
                {
                    PXTrace.WriteWarning(
                        $"[BoxLabel] Shipment {shipmentNbr}: no packages found — no labels queued.");
                    return;
                }

                // ── Step 2: Resolve Device Hub printer ────────────────────────
                // Priority order:
                //   a) Current user's printer from UserPreferences (SM.UserPreferences)
                //   b) Nothing found → warn and bail; don't block the workflow.
                string printerName = ResolvePrinterName();

                if (string.IsNullOrWhiteSpace(printerName))
                {
                    // Warn on-screen (non-blocking) and trace, then exit.
                    PXTrace.WriteWarning(
                        $"[BoxLabel] Shipment {shipmentNbr}: no Device Hub printer configured " +
                        "for current user. Set a default printer in User Preferences (SM202010). " +
                        "Labels were NOT queued.");

                    shipmentCache.RaiseExceptionHandling<SOShipmentLabelExt.usrBoxLabelPrinted>(
                        shipment, false,
                        new PXSetPropertyException(
                            "Box labels could not be queued: no Device Hub printer is configured " +
                            "for your user account. Please set a default printer in User Preferences.",
                            PXErrorLevel.Warning));
                    return;
                }

                // ── Step 3: Create one print job per package ──────────────────
                int jobsQueued = 0;

                foreach (SOPackageDetailEx pkg in packages)
                {
                    try
                    {
                        QueueSingleLabelJob(shipmentNbr, pkg.LineNbr, printerName);
                        jobsQueued++;
                    }
                    catch (Exception pkgEx)
                    {
                        // Log individual package failure but continue with remaining packages.
                        PXTrace.WriteWarning(
                            $"[BoxLabel] Shipment {shipmentNbr}, LineNbr {pkg.LineNbr}: " +
                            $"failed to queue print job — {pkgEx.GetType().Name}: {pkgEx.Message}");
                    }
                }

                // ── Step 4: Mark labels as printed (in-cache; persisted on Save) ──
                if (jobsQueued > 0)
                {
                    shipmentCache.SetValueExt<SOShipmentLabelExt.usrBoxLabelPrinted>(shipment, true);

                    PXTrace.WriteInformation(
                        $"[BoxLabel] Shipment {shipmentNbr}: queued {jobsQueued}/{packages.Count} " +
                        $"label job(s) on printer '{printerName}'.");
                }
                else
                {
                    // All individual package jobs failed — surface a warning.
                    PXTrace.WriteWarning(
                        $"[BoxLabel] Shipment {shipmentNbr}: all {packages.Count} label job(s) " +
                        "failed to queue. Check Device Hub logs.");

                    shipmentCache.RaiseExceptionHandling<SOShipmentLabelExt.usrBoxLabelPrinted>(
                        shipment, false,
                        new PXSetPropertyException(
                            "Box labels could not be printed. Device Hub may be offline or the " +
                            "report 'BoxLabel4x6' is unavailable. Check the trace log for details.",
                            PXErrorLevel.Warning));
                }
            }
            catch (Exception ex)
            {
                // Top-level catch: Device Hub completely unavailable or unexpected error.
                // Log as warning — NEVER throw from RowUpdated to avoid blocking the workflow.
                PXTrace.WriteWarning(
                    $"[BoxLabel] Shipment {shipmentNbr}: unexpected error queuing labels — " +
                    $"{ex.GetType().FullName}: {ex.Message}");

                shipmentCache.RaiseExceptionHandling<SOShipmentLabelExt.usrBoxLabelPrinted>(
                    shipment, false,
                    new PXSetPropertyException(
                        $"Box label auto-print encountered an error: {ex.Message} " +
                        "The shipment has been saved normally. Check Device Hub and retry manually.",
                        PXErrorLevel.Warning));
            }
        }

        // -----------------------------------------------------------------
        // QueueSingleLabelJob
        //
        // Creates a single SMPrintJob via SMPrintJobMaint for one package.
        //
        // SMPrintJobMaint is the standard Acumatica Device Hub print graph
        // (namespace PX.SM). It accepts:
        //   • PrinterName  — the Device Hub printer ID string
        //   • ReportID     — the report to print
        //   • Parameters   — key/value pairs passed as report parameters
        //
        // The graph's Save action persists the job record, which Device Hub
        // then picks up asynchronously and sends to the physical printer.
        // -----------------------------------------------------------------
        private void QueueSingleLabelJob(string shipmentNbr, int? packageLineNbr, string printerName)
        {
            // Create a fresh, isolated graph instance for each job so that
            // cache state does not bleed between iterations.
            SMPrintJobMaint printGraph = PXGraph.CreateInstance<SMPrintJobMaint>();

            // Build the new print job record.
            SMPrintJob job = new SMPrintJob
            {
                // Device Hub printer identifier (matches Printer ID on SM206036).
                PrinterName = printerName,

                // Report ID as registered in the Report Designer (SM208000).
                // Must match the Report ID field exactly (case-sensitive).
                ReportID = BOX_LABEL_REPORT_ID,

                // Number of copies — always 1 per package; re-print manually if needed.
                NumberOfCopies = 1
            };

            // Insert the job into the graph's primary view.
            job = printGraph.PrintJob.Insert(job);

            // ── Attach report parameters ──────────────────────────────────
            // SMPrintJobMaint uses a child view (PrintParameters) to hold
            // the name/value pairs that get forwarded to the report engine.
            AttachReportParameter(printGraph, job, "ShipmentNbr",     shipmentNbr);
            AttachReportParameter(printGraph, job, "PackageLineNbr",  packageLineNbr?.ToString() ?? "0");

            // Persist — this commits the job to the SMPrintJob table and
            // makes it visible to the Device Hub polling service.
            printGraph.Actions.PressSave();
        }

        // -----------------------------------------------------------------
        // AttachReportParameter
        //
        // Inserts a single name/value pair into the SMPrintJobMaint's
        // PrintParameters detail view. Acumatica's Device Hub reads these
        // from the SMPrintJobParameter table when it dispatches the job to
        // the report engine.
        // -----------------------------------------------------------------
        private static void AttachReportParameter(
            SMPrintJobMaint printGraph,
            SMPrintJob      job,
            string          paramName,
            string          paramValue)
        {
            SMPrintJobParameter param = new SMPrintJobParameter
            {
                // ParentJobID links back to the header via the FK.
                // PXParent on the DAC handles this automatically when we
                // insert with the header as Current — but we set it
                // explicitly as a belt-and-suspenders safety measure.
                JobID     = job.JobID,
                ParameterName  = paramName,
                ParameterValue = paramValue
            };

            printGraph.PrintParameters.Insert(param);
        }

        // -----------------------------------------------------------------
        // ResolvePrinterName
        //
        // Retrieves the Device Hub printer name for the currently logged-in
        // user from their User Preferences record (SM.UserPreferences).
        //
        // UserPreferences.PrinterName holds the printer ID that the user
        // selected in User Preferences (SM202010 → Printer Name field).
        // This is the most natural per-user configuration point in Acumatica
        // and requires no additional custom fields.
        //
        // Returns null / empty string if no printer is configured so callers
        // can decide how to handle the missing-printer case.
        // -----------------------------------------------------------------
        private string ResolvePrinterName()
        {
            // PXAccess.GetUserID() returns the current user's GUID, which is
            // the primary key for UserPreferences.
            Guid? userID = PXAccess.GetUserID();
            if (userID == null) return null;

            UserPreferences prefs = PXSelect<
                UserPreferences,
                Where<UserPreferences.userID, Equal<Required<UserPreferences.userID>>>>
                .Select(Base, userID);

            return prefs?.PrinterName;
        }

        // -----------------------------------------------------------------
        // GetPickStatus
        //
        // Reads UsrFRPickStatus from the Kensium WMS DAC extension on
        // SOShipment. Because we cannot take a hard compile-time dependency
        // on the Kensium assembly type name (it may change between WMS
        // versions), we use PXCache.GetValue with the field name string.
        //
        // If the field is missing (e.g. running in a non-WMS environment),
        // GetValue returns null, the method returns null, and the gate check
        // cleanly returns false — no exception thrown.
        // -----------------------------------------------------------------
        private static string GetPickStatus(PXCache cache, SOShipment row)
        {
            if (row == null) return null;
            try
            {
                // Attempt late-bound field access — safe even if the extension
                // DAC is not present in the current Acumatica instance build.
                object rawValue = cache.GetValue(row, "UsrFRPickStatus");
                return rawValue as string;
            }
            catch
            {
                // Field does not exist on this instance — return null so gates fail safely.
                return null;
            }
        }
    }

    // =========================================================================
    // SECTION 3 — Schema Installer: adds UsrBoxLabelPrinted column to SOShipment
    //
    // Follows the same CustomizationPlugin pattern used by HeritageFabricsSchemaInstaller
    // and PORelationsInstaller already in this project. The IF NOT EXISTS guard
    // makes every publish idempotent — safe to run repeatedly with no side effects.
    // =========================================================================
    public class ShipmentLabelSchemaInstaller : Customization.CustomizationPlugin
    {
        public override void UpdateDatabase()
        {
            string connStr = null;
            try
            {
                var cs = System.Configuration.ConfigurationManager
                              .ConnectionStrings["ProjectX"];
                if (cs != null) connStr = cs.ConnectionString;
            }
            catch { /* connection string lookup failure handled below */ }

            // Fallback: scan all registered connection strings
            if (connStr == null)
            {
                try
                {
                    var all = System.Configuration.ConfigurationManager.ConnectionStrings;
                    for (int i = 0; i < all.Count; i++)
                    {
                        string name = all[i].Name;
                        if (name != "LocalSqlServer" && name != "LocalMySqlServer")
                            connStr = all[i].ConnectionString;
                    }
                }
                catch { /* ignore — handled below */ }
            }

            if (connStr == null)
            {
                WriteLog("[ShipmentLabelSchema] ERROR: No connection string found — cannot alter SOShipment table.");
                return;
            }

            // Microsoft.Data.SqlClient requires explicit TLS trust for cloud SQL endpoints.
            if (!connStr.Contains("TrustServerCertificate"))
                connStr += ";TrustServerCertificate=True";

            string[] statements = new[]
            {
                // UsrBoxLabelPrinted — idempotency flag for box-label auto-print
                "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('SOShipment') AND name = 'UsrBoxLabelPrinted') " +
                "ALTER TABLE SOShipment ADD UsrBoxLabelPrinted bit NULL"
            };

            try
            {
                using (var conn = new Microsoft.Data.SqlClient.SqlConnection(connStr))
                {
                    conn.Open();
                    foreach (string sql in statements)
                    {
                        using (var cmd = conn.CreateCommand())
                        {
                            cmd.CommandText = sql;
                            cmd.CommandTimeout = 60;
                            cmd.ExecuteNonQuery();
                        }
                        WriteLog("[ShipmentLabelSchema] OK: UsrBoxLabelPrinted column ensured on SOShipment.");
                    }
                }
            }
            catch (Exception ex)
            {
                WriteLog($"[ShipmentLabelSchema] ERROR: {ex.GetType().FullName}: {ex.Message}");
                if (ex.InnerException != null)
                    WriteLog($"[ShipmentLabelSchema] Inner: {ex.InnerException.Message}");
            }
        }
    }
}
