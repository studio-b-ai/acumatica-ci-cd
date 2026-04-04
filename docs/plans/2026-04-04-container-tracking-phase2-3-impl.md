# Container Tracking Phase 2 & 3 — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable push-based container event tracking and build 4 master data screens (PO Container Lines GI, Container Types, Destinations/Ports, Container Preferences).

**Architecture:** Phase 2 adds a push webhook endpoint to webhook-router and enables the existing container-tracking worker. Phase 3 adds 3 new DACs + ASPX screens + 1 GI to AesthetikContainers, all deployed via the CustomizationPlugin.

**Tech Stack:** TypeScript/Fastify (webhook-router), C# (Acumatica DAC/Graph), ASPX, Python (gi_builder.py), Playwright (tests)

**Key Files:**
- Webhook-router: `/Users/kevin/dev/webhook-router/`
  - `src/workers/container-tracking.ts` — existing BullMQ worker
  - `src/lib/acumatica-containers.ts` — container CRUD helpers
  - `src/routes/carrier-webhooks.ts` — existing carrier webhook routes
  - `src/index.ts` — worker startup (line ~1743)
  - `src/lib/config.ts` — config vars
- Acumatica CI/CD: `/Users/kevin/dev/acumatica-ci-cd/`
  - `Customization/AesthetikContainers/project.xml` — DACs, graphs, ASPX, CustomizationPlugin
  - `scripts/heritage/gi_builder.py` — GI SQL generator
  - `scripts/heritage/gi_container_tracking.py` — existing GI specs (add PO Container Lines here)
  - `tests/ui/test_container_tracking.py` — Playwright tests

**Constraints:**
- After-hours deploys only (publishes restart Acumatica app pool)
- Never commit directly to main — always branch + PR
- `navigate_to_screen_safe()` + `wait_for_screen()` for Playwright (no `networkidle`)
- GI SQL must include `-- REVIEWED: gi-sql-safe` marker
- All DDL via `EnsureTable()` / `EnsureColumn()` / `EnsureIndex()` (idempotent)
- Container Tracking workspace ParentID: `9c89e3db-7c47-43c0-8554-5d2c9f2c0e87`

---

## Phase 2: Push-Based Container Events

### Task 1: Add container-update webhook endpoint to webhook-router

**Files:**
- Create: `/Users/kevin/dev/webhook-router/src/routes/container-update.ts`
- Modify: `/Users/kevin/dev/webhook-router/src/index.ts`

**Step 1: Create the webhook route**

Create `/Users/kevin/dev/webhook-router/src/routes/container-update.ts`:

```typescript
import { FastifyInstance } from "fastify";
import { Queue } from "bullmq";
import { Logger } from "pino";

interface ContainerUpdateRouteConfig {
  trackingQueue: Queue | null;
  log: Logger;
}

export function registerContainerUpdateRoute(
  app: FastifyInstance,
  cfg: ContainerUpdateRouteConfig,
) {
  app.post("/webhook/acumatica/container-update", async (request, reply) => {
    const body = request.body as Record<string, unknown>;
    const containerCD = body.ContainerCD as string;
    const carrierCode = body.CarrierCode as string;

    if (!containerCD) {
      return reply.status(400).send({ ok: false, error: "ContainerCD required" });
    }

    cfg.log.info({ containerCD, carrierCode }, "Container update webhook received");

    if (cfg.trackingQueue && carrierCode) {
      await cfg.trackingQueue.add("track-single", {
        eventType: "track-single",
        containerRef: `${carrierCode}:${containerCD}`,
        carrierCode,
        reference: containerCD,
        source: "acumatica-push",
      });
    }

    return { ok: true, containerCD, queued: !!cfg.trackingQueue };
  });
}
```

**Step 2: Register the route in index.ts**

Find the section where `registerCarrierWebhookRoutes` is called (~line 910) and add after it:

```typescript
import { registerContainerUpdateRoute } from "./routes/container-update";

// In the route registration section:
registerContainerUpdateRoute(app, { trackingQueue, log: logger });
```

**Step 3: Commit**

```bash
cd /Users/kevin/dev/webhook-router
git checkout -b feat/container-push-events
git add src/routes/container-update.ts src/index.ts
git commit -m "feat: add /webhook/acumatica/container-update push endpoint

Receives container save events from Acumatica ContainerMaint.Persist()
and enqueues track-single job to re-query carrier API for latest events."
```

---

### Task 2: Reduce poll frequency to daily fallback

**Files:**
- Modify: `/Users/kevin/dev/webhook-router/src/workers/container-tracking.ts`

**Step 1: Change the container-poll cron from 4h to daily**

In `createContainerTrackingWorker()`, find the job scheduler registration for `container-poll` (around line 239). Change the pattern from every 4 hours to daily:

```typescript
// Change from:
// pattern: "0 */4 * * *"  (every 4 hours)
// To:
pattern: cfg.pollCron,  // Already uses config — just change the env var default
```

The config already reads from `CONTAINER_TRACKING_POLL_CRON` with default `"0 11 * * *"` (daily at 6am EST). No code change needed — the cron is already daily. Just verify `CONTAINER_TRACKING_POLL_CRON` isn't overridden in Railway to a 4-hour schedule.

**Step 2: Verify config**

Check Railway env vars for webhook-router:
- `CONTAINER_TRACKING_POLL_CRON` — should be daily (default `0 11 * * *` is correct)
- If set to `0 */4 * * *`, change to `0 11 * * *`

**Step 3: Commit (if code changed)**

```bash
git add src/workers/container-tracking.ts
git commit -m "fix: reduce container poll to daily fallback (push is primary)"
```

---

### Task 3: Enable the container tracking worker

**Step 1: Set Railway env vars**

Using Railway CLI or MCP:
```
CONTAINER_TABLE_TRACKING_ENABLED=true
```

This enables the UsrContainer-based tracking mode (vs legacy PO-only mode).

**Step 2: Verify carrier registry has carriers**

Check that at least one carrier API key is configured:
- `CHR_API_KEY` — CH Robinson
- `OTS_API_KEY` — CargoWise/OTS

**Step 3: Deploy webhook-router**

Push the branch, create PR, merge. Railway auto-deploys.

```bash
cd /Users/kevin/dev/webhook-router
git push -u origin feat/container-push-events
gh pr create --title "feat: push-based container events" --body "..."
```

---

### Task 4: Wire ContainerMaint.Persist() to push events

**Files:**
- Modify: `/Users/kevin/dev/acumatica-ci-cd/Customization/AesthetikContainers/project.xml`

**Step 1: Add HTTP POST to webhook-router in Persist() override**

In the `ContainerMaint` graph CDATA, the existing `Persist()` override calls `ContainerDatePropagation.PropagateArrivalDate()`. After that call, add an HTTP POST:

```csharp
public override void Persist()
{
    base.Persist();

    var row = Container.Current;
    if (row != null)
    {
        ContainerDatePropagation.PropagateArrivalDate(
            this, row.ContainerID.Value, row.ETA, row.ATA);

        // Push container update to webhook-router for carrier event refresh
        try
        {
            var webhookUrl = System.Configuration.ConfigurationManager.AppSettings["ContainerWebhookUrl"];
            if (!string.IsNullOrEmpty(webhookUrl))
            {
                using (var client = new System.Net.Http.HttpClient())
                {
                    client.Timeout = System.TimeSpan.FromSeconds(5);
                    var json = Newtonsoft.Json.JsonConvert.SerializeObject(new
                    {
                        ContainerCD = row.ContainerCD,
                        CarrierCode = row.CarrierCode,
                        ContainerID = row.ContainerID,
                        Status = row.Status,
                    });
                    var content = new System.Net.Http.StringContent(
                        json, System.Text.Encoding.UTF8, "application/json");
                    client.PostAsync(webhookUrl, content).ConfigureAwait(false);
                }
            }
        }
        catch { /* Fire-and-forget — don't block save */ }
    }
}
```

**Step 2: Add AppSettings key for webhook URL**

This will be configured in Acumatica's web.config or as a customization parameter. For now, the try/catch ensures it fails silently if unconfigured.

**Step 3: Commit**

```bash
cd /Users/kevin/dev/acumatica-ci-cd
git add Customization/AesthetikContainers/project.xml
git commit -m "feat: wire ContainerMaint.Persist() to push container updates

Fire-and-forget POST to webhook-router on container save.
Triggers carrier event refresh instead of waiting for 24h poll."
```

---

## Phase 3: Master Data Screens

### Task 5: Add PO Container Lines GI spec to gi_builder

**Files:**
- Modify: `/Users/kevin/dev/acumatica-ci-cd/scripts/heritage/gi_container_tracking.py`

**Step 1: Add po_container_lines_spec() function**

Add after the existing `custom_classification_spec()`:

```python
def po_container_lines_spec() -> GIDefinition:
    """PO Container Lines GI (SB401040) — detail view of PO lines on containers."""
    return GIDefinition(
        name="POContainerLines",
        screen_id="SB401040",
        tables=[
            {"dac": "StudioB.Containers.UsrContainerPOLink", "alias": "Link"},
            {"dac": "StudioB.Containers.UsrContainer", "alias": "Container"},
            {"dac": "PX.Objects.PO.POOrder", "alias": "PO"},
            {"dac": "PX.Objects.PO.POLine", "alias": "Line"},
        ],
        results=[
            {"field": "ContainerCD", "caption": "Container", "width": 120},
            {"field": "Status", "caption": "Status", "width": 100},
            {"field": "ETA", "caption": "ETA", "width": 100},
            {"field": "OrderType", "caption": "Type", "width": 60},
            {"field": "OrderNbr", "caption": "PO Nbr", "width": 120},
            {"field": "LineNbr", "caption": "Line", "width": 60},
            {"field": "InventoryID", "caption": "Item", "width": 120},
            {"field": "OrderQty", "caption": "Qty", "width": 80},
            {"field": "CuryUnitCost", "caption": "Price", "width": 80},
        ],
        filters=[
            {"name": "ContainerFilter", "display_name": "Container", "data_type": 6},
            {"name": "POFilter", "display_name": "PO Nbr", "data_type": 6},
        ],
        where=[
            {"field": "Container.ContainerCD", "condition": "E ", "value": "@ContainerFilter", "operation": "A"},
            {"field": "Link.OrderNbr", "condition": "E ", "value": "@POFilter", "operation": "A"},
        ],
        sort=[
            {"field": "Container.ContainerCD", "order": "A"},
            {"field": "Link.OrderNbr", "order": "A"},
        ],
    )
```

**Step 2: Add to ALL_SPECS list**

```python
ALL_SPECS = [
    ("po_containers", po_containers_spec),
    ("so_containers", so_containers_spec),
    ("container_events", container_events_spec),
    ("custom_classification", custom_classification_spec),
    ("po_container_lines", po_container_lines_spec),  # NEW
]
```

**Step 3: Generate SQL**

```bash
cd /Users/kevin/dev/acumatica-ci-cd
python3 scripts/heritage/gi_container_tracking.py --gi po_container_lines --output-dir data/container-tracking
```

**Step 4: Commit**

```bash
git add scripts/heritage/gi_container_tracking.py data/container-tracking/po_container_lines.sql
git commit -m "feat: add PO Container Lines GI spec (SB401040)"
```

---

### Task 6: Add Container Types DAC + Graph + ASPX

**Files:**
- Modify: `/Users/kevin/dev/acumatica-ci-cd/Customization/AesthetikContainers/project.xml`

**Step 1: Add UsrContainerType DAC**

Add a new `<Graph>` element for the DAC:

```xml
<Graph ClassName="UsrContainerType" Source="#CDATA" IsNew="True" FileType="NewFile">
    <CDATA name="Source"><![CDATA[using System;
using PX.Data;
using PX.Data.BQL;

namespace StudioB.Containers
{
    [Serializable]
    [PXCacheName("Container Type")]
    public class UsrContainerType : IBqlTable
    {
        #region ContainerTypeID
        public abstract class containerTypeID : BqlInt.Field<containerTypeID> { }
        [PXDBIdentity]
        public int? ContainerTypeID { get; set; }
        #endregion

        #region TypeCD
        public abstract class typeCD : BqlString.Field<typeCD> { }
        [PXDBString(10, IsUnicode = true, IsKey = true, InputMask = ">aaaaaaaaaa")]
        [PXDefault]
        [PXUIField(DisplayName = "Type ID", Visibility = PXUIVisibility.SelectorVisible)]
        [PXSelector(typeof(Search<UsrContainerType.typeCD>),
            typeof(UsrContainerType.typeCD),
            typeof(UsrContainerType.description))]
        public string TypeCD { get; set; }
        #endregion

        #region Description
        public abstract class description : BqlString.Field<description> { }
        [PXDBString(60, IsUnicode = true)]
        [PXUIField(DisplayName = "Description")]
        public string Description { get; set; }
        #endregion

        #region LengthFt
        public abstract class lengthFt : BqlDecimal.Field<lengthFt> { }
        [PXDBDecimal(1)]
        [PXUIField(DisplayName = "Length (ft)")]
        public decimal? LengthFt { get; set; }
        #endregion

        #region WidthFt
        public abstract class widthFt : BqlDecimal.Field<widthFt> { }
        [PXDBDecimal(1)]
        [PXUIField(DisplayName = "Width (ft)")]
        public decimal? WidthFt { get; set; }
        #endregion

        #region HeightFt
        public abstract class heightFt : BqlDecimal.Field<heightFt> { }
        [PXDBDecimal(1)]
        [PXUIField(DisplayName = "Height (ft)")]
        public decimal? HeightFt { get; set; }
        #endregion

        #region MaxWeightKg
        public abstract class maxWeightKg : BqlDecimal.Field<maxWeightKg> { }
        [PXDBDecimal(0)]
        [PXUIField(DisplayName = "Max Weight (kg)")]
        public decimal? MaxWeightKg { get; set; }
        #endregion

        #region Active
        public abstract class active : BqlBool.Field<active> { }
        [PXDBBool]
        [PXDefault(true)]
        [PXUIField(DisplayName = "Active")]
        public bool? Active { get; set; }
        #endregion

        #region NoteID
        public abstract class noteID : BqlGuid.Field<noteID> { }
        [PXNote]
        public Guid? NoteID { get; set; }
        #endregion

        #region Audit + Timestamp
        public abstract class createdByID : BqlGuid.Field<createdByID> { }
        [PXDBCreatedByID] public Guid? CreatedByID { get; set; }
        public abstract class createdByScreenID : BqlString.Field<createdByScreenID> { }
        [PXDBCreatedByScreenID] public string CreatedByScreenID { get; set; }
        public abstract class createdDateTime : BqlDateTime.Field<createdDateTime> { }
        [PXDBCreatedDateTime] public DateTime? CreatedDateTime { get; set; }
        public abstract class lastModifiedByID : BqlGuid.Field<lastModifiedByID> { }
        [PXDBLastModifiedByID] public Guid? LastModifiedByID { get; set; }
        public abstract class lastModifiedByScreenID : BqlString.Field<lastModifiedByScreenID> { }
        [PXDBLastModifiedByScreenID] public string LastModifiedByScreenID { get; set; }
        public abstract class lastModifiedDateTime : BqlDateTime.Field<lastModifiedDateTime> { }
        [PXDBLastModifiedDateTime] public DateTime? LastModifiedDateTime { get; set; }
        public abstract class tstamp : BqlByteArray.Field<tstamp> { }
        [PXDBTimestamp] public byte[] Tstamp { get; set; }
        #endregion
    }
}
]]></CDATA>
</Graph>
```

**Step 2: Add ContainerTypeMaint graph**

```xml
<Graph ClassName="ContainerTypeMaint" Source="#CDATA" IsNew="True" FileType="NewFile">
    <CDATA name="Source"><![CDATA[using PX.Data;
using PX.Data.BQL.Fluent;

namespace StudioB.Containers
{
    public class ContainerTypeMaint : PXGraph<ContainerTypeMaint, UsrContainerType>
    {
        public SelectFrom<UsrContainerType>.View ContainerType;
    }
}
]]></CDATA>
</Graph>
```

**Step 3: Add SB302010.aspx + code-behind (same FormView pattern as SB302000)**

ASPX with fields: TypeCD selector, Description, LengthFt, WidthFt, HeightFt, MaxWeightKg, Active checkbox.

**Step 4: Add DDL to CustomizationPlugin**

In `UpdateDatabase()`, add EnsureTable for `UsrContainerType` + seed data:

```csharp
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

// Seed container types
SeedContainerTypes(conn);
```

Add seed method:

```csharp
private void SeedContainerTypes(SqlConnection conn)
{
    var types = new[] {
        ("20GP", "20ft Standard", "20.0", "8.0", "8.5", "28200"),
        ("40GP", "40ft Standard", "40.0", "8.0", "8.5", "28800"),
        ("40HC", "40ft High Cube", "40.0", "8.0", "9.5", "28560"),
        ("45HC", "45ft High Cube", "45.0", "8.0", "9.5", "27600"),
        ("20RF", "20ft Reefer", "20.0", "8.0", "8.5", "27400"),
        ("40RF", "40ft Reefer", "40.0", "8.0", "8.5", "27700"),
    };
    foreach (var (cd, desc, l, w, h, wt) in types)
    {
        string sql = string.Format(
            @"IF NOT EXISTS (SELECT 1 FROM UsrContainerType WHERE TypeCD = '{0}' AND CompanyID = 2)
            INSERT INTO UsrContainerType (CompanyID, TypeCD, Description, LengthFt, WidthFt, HeightFt, MaxWeightKg, Active)
            VALUES (2, '{0}', N'{1}', {2}, {3}, {4}, {5}, 1);",
            cd, desc, l, w, h, wt);
        using (var cmd = new SqlCommand(sql, conn)) { cmd.ExecuteNonQuery(); }
    }
    WriteLog("[AesthetikContainers] Container Types seed data — OK");
}
```

**Step 5: Add ScreenWithRights + SiteMap**

Add ScreenWithRights row for SB302010 and SiteMap entry in `EnsureContainerTrackingSiteMap()`.

**Step 6: Commit**

```bash
git add Customization/AesthetikContainers/project.xml
git commit -m "feat: add Container Types DAC + form (SB302010) with seed data"
```

---

### Task 7: Add Destinations/Ports DAC + Graph + ASPX (SB302020)

Same pattern as Task 6. DAC: `UsrPort` with PortCode (key), PortName, Country, Active.

Seed ~20 ports: CNSHA (Shanghai), CNYTN (Yantian), CNNGB (Ningbo), USLAX (Los Angeles), USLGB (Long Beach), USSAV (Savannah), USNYC (New York), USNWK (Newark), USCHI (Chicago), USHOU (Houston), CNQIN (Qingdao), CNXMN (Xiamen), CNSZX (Shenzhen), HKHKG (Hong Kong), VNSGN (Ho Chi Minh), VNHPH (Haiphong), IDSUB (Surabaya), INMAA (Chennai), INBOM (Mumbai), TWKHH (Kaohsiung).

Graph: `PortMaint`, ASPX: `SB302020.aspx`

**Commit:** `feat: add Destinations/Ports DAC + form (SB302020) with seed data`

---

### Task 8: Add Container Preferences DAC + Graph + ASPX (SB302030)

Single-record preferences DAC: `UsrContainerPrefs` with DefaultCarrierCode, DefaultContainerType (FK → UsrContainerType), DefaultInTransitWarehouse, AutoLinkPOsByRef (bool, default true), TrackingPollIntervalHours (int, default 24).

Graph: `ContainerPrefsMaint` (single-record pattern — `PXGraph<ContainerPrefsMaint>` with `Setup` view using `PXSetup`).

ASPX: `SB302030.aspx` — single-record FormView.

**Commit:** `feat: add Container Preferences DAC + form (SB302030)`

---

### Task 9: Embed GI SQL + SiteMap for Phase 3 screens

**Files:**
- Modify: `/Users/kevin/dev/acumatica-ci-cd/Customization/AesthetikContainers/project.xml`

**Step 1: Generate PO Container Lines GI SQL** (from Task 5)

**Step 2: Add GI SQL to `EnsureContainerTrackingGIs()`**

Paste the generated SQL as a 5th entry in the `giSqls` array.

**Step 3: Add SiteMap entries to `EnsureContainerTrackingSiteMap()`**

Add 4 new entries:
```
SB401040 — PO Container Lines — ~/GenericInquiry/GenericInquiry.aspx?id=SB401040 — Position 8.1
SB302010 — Container Types — ~/Pages/SB/SB302010.aspx — Position 8.2
SB302020 — Destinations/Ports — ~/Pages/SB/SB302020.aspx — Position 8.3
SB302030 — Container Preferences — ~/Pages/SB/SB302030.aspx — Position 8.4
```

**Step 4: Add ScreenWithRights for SB302010, SB302020, SB302030**

Same pattern as SB302000 (Admin=4, *=0).

**Step 5: Commit**

```bash
git add Customization/AesthetikContainers/project.xml
git commit -m "feat: GI SQL + SiteMap + ScreenWithRights for Phase 3 screens"
```

---

### Task 10: Update UsrContainer to reference master tables

**Files:**
- Modify: `/Users/kevin/dev/acumatica-ci-cd/Customization/AesthetikContainers/project.xml`

**Step 1: Change ContainerType from PXStringList to PXSelector**

In the UsrContainer DAC, replace:
```csharp
[PXStringList(
    new[] { "20GP", "40GP", "40HC", "45HC", "20RF", "40RF" },
    new[] { ... })]
```

With:
```csharp
[PXSelector(typeof(Search<UsrContainerType.typeCD,
    Where<UsrContainerType.active, Equal<True>>>),
    typeof(UsrContainerType.typeCD),
    typeof(UsrContainerType.description))]
```

**Step 2: Change PortOfLoading/PortOfDischarge from free-text to PXSelector**

Replace plain `[PXDBString]` with:
```csharp
[PXSelector(typeof(Search<UsrPort.portCode,
    Where<UsrPort.active, Equal<True>>>),
    typeof(UsrPort.portCode),
    typeof(UsrPort.portName),
    typeof(UsrPort.country))]
```

**Step 3: Commit**

```bash
git commit -m "feat: link ContainerType and Ports to master tables via PXSelector"
```

---

### Task 11: Add Playwright tests for Phase 3 screens

**Files:**
- Modify: `/Users/kevin/dev/acumatica-ci-cd/tests/ui/test_container_tracking.py`

**Step 1: Add test classes**

Same pattern as Phase 1 tests — load test + form content test for each ASPX screen, load test for GI.

```python
class TestPhase3Screens:
    """Verify Phase 3 container tracking screens."""

    @pytest.mark.parametrize("screen_id,name", [
        ("SB401040", "PO Container Lines"),
        ("SB302010", "Container Types"),
        ("SB302020", "Destinations/Ports"),
        ("SB302030", "Container Preferences"),
    ])
    def test_screen_loads(self, acumatica_page, screen_id, name):
        navigate_to_screen_safe(acumatica_page, screen_id)
        wait_for_screen(acumatica_page, screen_id)

        current_url = acumatica_page.url
        assert "ScreenId=ERROR" not in current_url, \
            f"{name} ({screen_id}) redirected to error page"

        if "ScreenId=00000000" in current_url:
            pytest.skip(f"{name} ({screen_id}) not yet deployed")
```

**Step 2: Verify syntax**

```bash
python3 -m py_compile tests/ui/test_container_tracking.py
```

**Step 3: Commit**

```bash
git add tests/ui/test_container_tracking.py
git commit -m "test: Playwright tests for Phase 3 container tracking screens"
```

---

### Task 12: Validate, PR, and deploy

**Step 1: Validate XML**

```bash
python3 -c "import xml.etree.ElementTree as ET; ET.parse('Customization/AesthetikContainers/project.xml'); print('OK')"
```

**Step 2: Create PR**

```bash
git push -u origin feat/container-tracking-phase2-3
gh pr create --title "feat: container tracking Phase 2 & 3" --body "..."
```

**Step 3: Update end-user migration guide**

Add Phase 3 screens to `docs/guides/container-tracking-migration-guide.md`.

---

## Execution Order

| Task | Description | Repo | Depends On | Parallel? |
|------|-------------|------|------------|-----------|
| 1 | Push webhook endpoint | webhook-router | — | Yes with 5 |
| 2 | Reduce poll frequency | webhook-router | — | Yes with 1 |
| 3 | Enable worker (Railway env) | webhook-router | 1, 2 | — |
| 4 | Wire Persist() push | acumatica-ci-cd | 1 | — |
| 5 | PO Container Lines GI spec | acumatica-ci-cd | — | Yes with 1 |
| 6 | Container Types DAC + form | acumatica-ci-cd | — | Yes with 7 |
| 7 | Ports DAC + form | acumatica-ci-cd | — | Yes with 6 |
| 8 | Preferences DAC + form | acumatica-ci-cd | — | Yes with 6,7 |
| 9 | Embed GI SQL + SiteMap | acumatica-ci-cd | 5, 6, 7, 8 | — |
| 10 | Link UsrContainer to masters | acumatica-ci-cd | 6, 7 | — |
| 11 | Playwright tests | acumatica-ci-cd | 9 | — |
| 12 | Validate + PR + deploy | both | all | — |

Tasks 1+2, 5+6+7+8 can run in parallel.
