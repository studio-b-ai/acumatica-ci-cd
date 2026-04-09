# Container Tracking UI Test Failures — investigation + fix plan

> ## ⚠ CORRECTION (2026-04-08, after PR #289 merged)
>
> **The original investigation in this doc reached a wrong conclusion about Failure #2 (PO301000 button).** Preserved below as a learning artifact. Read this section first.
>
> ### What actually happened
>
> A second Claude session (`claude/zealous-noether` → PR #289 squash `630cca4`) ran the test against the live sandbox via Playwright and found the real root cause:
>
> 1. **`/Main?ScreenId=PO301000` redirects to home in this tenant.** AesthetikWMS shadows PO301000 with PO3010PL via the customization layer. The standard framed-nav route (`/Main?ScreenId=PO301000`) sends users to home because the screen registration was overridden. So the original test wasn't even loading the form it claimed to be testing — it was looking for "CONTAINER TRACKING" on the home page, which obviously doesn't have it.
> 2. **`page.locator("text=CONTAINER TRACKING")` couldn't pierce iframes anyway.** Acumatica renders forms inside `iframe[name='main']`. The default Playwright `text=` locator searches the top document, not nested frames. Even if the form HAD loaded, the locator would have returned `count() == 0`. The original assertion `assert btn.count() > 0` was vacuous: it has been silently false for 2 reasons since the test was added.
> 3. **The CONTAINER TRACKING button was deployed correctly the entire time.** PR #70's Sprint 2 work was never broken. `POOrderEntry_Extension.cs:13` defines the `ViewContainer` PXAction with `[PXButton]` + `[PXUIField(DisplayName = "Container Tracking")]`, and Acumatica's graph extension auto-promotes it to the top toolbar. Verified live in sandbox: 2 visible matches with class `qp-tool-bar-text`.
>
> ### The fix that shipped (PR #289)
>
> Test-only change, no DLL/schema/SQL/project.xml. New test pattern: `acumatica_page.goto(.../Pages/PO/PO301000.aspx)` then look for the button via top-level locator. Bypasses the framed wrapper entirely, which is the right approach for **screen-shadowed forms** where `/Main?ScreenId=...` redirects.
>
> ### Two valid Playwright patterns for Acumatica forms (KB-worthy)
>
> | Pattern | When to use | Example |
> |---|---|---|
> | `get_main_frame(page).locator(...)` | Tests using `/Main?ScreenId=XXXXXX` framed nav, where the form renders into `iframe[name='main']`. Most existing `test_container_tracking.py` tests use this. | Workspace test (now skipped), other PO301000 field tests |
> | `page.goto(.../Pages/.../XXXXXX.aspx)` then top-level locator | Screen-shadowed forms (e.g. AesthetikWMS shadowing PO301000 → PO3010PL) OR when you want to skip the framed wrapper entirely | `test_container_tracking_button_exists` (PR #289) |
>
> A KB doc on this is being written by `claude/zealous-noether` titled `"Acumatica iframe + screen-shadowing test patterns — when to use direct-aspx vs iframe-scoped locators"`. The screen-shadowing trap (a customization can shadow a stock screen so framed-nav goes to home) is the more interesting half — easy to miss without live verification.
>
> ### What this doc gets right vs wrong
>
> - **Failure #1 (workspace) — diagnosis still correct.** The MUIWorkspace row really is missing, the `85e6542` history really is the cause, and the `EnsureContainerTrackingMUI` CustomizationPlugin path really is the right fix. **Status: deferred follow-up.** Will be implemented in a separate PR (`claude/ensure-workspace-mui-rows`) **after** the 6 PM ET deploy of PR #289 + Phase A-G is verified clean. Schema introspection is in flight via REST API on the current branch.
> - **Failure #2 (button) — diagnosis was wrong.** Original section below claimed it needed graph-extension wiring + project.xml ASPX edit + DLL recompile. None of that was true. The graph extension was already correct; the test was just looking in the wrong place.
>
> ### Lesson
>
> **Verify against the running system before classifying a fix as "moderate" or "needs DLL recompile".** My investigation read source code + git history + project.xml, then made a conclusion without ever loading the actual screen in a browser. The other session's first action was to run the test live and inspect the DOM, which gave the right answer in minutes.
>
> Per CLAUDE.md rule #4 ("Verify before claiming success" — and inversely, before claiming failure): a 30-second sandbox load is worth more than 30 minutes of code reading.
>
> ---

**Context:** 2026-04-08 sandbox-gate failures on dispatch run 24121131536 (sha `f2449d8`). Two `tests/ui/test_container_tracking.py` failures remain after PR #285 fixed the SB501000 install plugin schema bug.

**Status (original — superseded above):** Investigation complete. Both fixes need Kevin sign-off + sandbox dry-run before merge. **Customization changes deferred** — risk of repeating the 2026-04-05 PO301000 breakage.

---

## Failure 1 — `TestContainerTrackingWorkspace::test_workspace_link_exists`

**What the test expects:** A `Container Tracking` entry in the Acumatica left sidebar workspace list when visiting SB501000.

**Current state:** No such entry. Sidebar omits the Container Tracking workspace entirely.

### Root cause

The MUI workspace registration was added in commit `9c557d1` (PR #203, 2026-03-31) and **deliberately removed** in commit `85e6542` (2026-04-05) after a production incident. The 85e6542 commit message:

> The MUIScreen/MUIWorkspace/MUISubcategory/MUIArea references in the ScreenWithRights block were deleting the PO301000 SiteMap entry on publish, breaking Purchase Orders and all PO-linked navigation (View Document, Inventory Allocation Details, etc.) across production.

What was removed:

1. Five `<MUIScreen WorkspaceID="95191203-...">` rows nested inside SiteMap row blocks (these uplink screens to the workspace) — **the actual bug source**
2. `<MUIWorkspace>` row defining the workspace (UUID `95191203-a0b8-4fc0-8b20-4efe831708e9`, Title `Container Tracking`, Icon `directions_car`, AreaID `62cfd5dc-...`)
3. `<MUISubcategory>` rows (Transactions / Configuration / Inquiries)
4. `<MUIArea>` row (Operations)
5. The table declarations (`<table name="MUIWorkspace">`, `<table name="MUISubcategory">`, `<table name="MUIArea">`, `<table name="MUIScreen">`)
6. The link declarations between MUI tables

### Why a naive re-add is unsafe

**Hypothesis (untested but consistent with the symptoms):** When the customization manifest declares the MUI table schema, the publish process treats those tables as **owned by this customization**. On unpublish/republish, it wipes existing rows that are not explicitly declared by this customization — including PO301000's pre-existing SiteMap entry that other (Acumatica-shipped) customizations registered.

If this hypothesis is correct, re-adding ANY of the MUI **table/link declarations** in `project.xml` will replicate the production breakage. Re-adding only the row data without the schema declarations may not insert the rows at all.

### Recommended fix path — needs Kevin call

**Option A — CustomizationPlugin approach (recommended).** Add MUI row insertions to `AesthetikContainersInstall` (the same C# CustomizationPlugin that PR #285 used to backfill schema columns). At publish time, the plugin would:

1. Check if the workspace UUID exists in `MUIWorkspace`
2. If not, INSERT it
3. Same for the subcategory + area rows
4. Idempotent (safe to publish repeatedly)
5. Does NOT declare table schema in `project.xml`, so does NOT trigger the row-wipe behavior

**Cost:** ~30-50 lines of C# in `src/StudioB.Containers/Graphs/AesthetikContainersInstall.cs`, DLL recompile, deploy.

**Option B — Add table declarations + careful row data, test in sandbox FIRST.** Re-add the project.xml block with all rows BUT verify in sandbox that PO301000 SiteMap survives republish. Risk: if sandbox passes but production has different state, prod breaks again.

**Option C — Defer.** Sidebar workspace is a navigation convenience, not a hard requirement. Users can navigate to SB501000 via direct screen ID. Mark the test `xfail` until Option A is implemented.

---

## Failure 2 — `TestPO301000ContainerFields::test_container_tracking_button_exists`

**What the test expects:** A `CONTAINER TRACKING` button visible on PO301000 (Purchase Orders) screen.

**Current state:** No button visible. Test docstring says "toolbar button should be present."

### Root cause — partial

The graph extension is correctly defined and compiled. From `src/StudioB.Containers/Graphs/POOrderEntry_Extension.cs:13`:

```csharp
public PXAction<POOrder> ViewContainer;
[PXButton(CommitChanges = true)]
[PXUIField(DisplayName = "Container Tracking", MapEnableRights = PXCacheRights.Select)]
protected void viewContainer() { ... }
```

The graph extension has `IsActive() => true`. The DLL is registered in `project.xml:168`. Source has not changed since PR #213; DLL was last rebuilt in PR #234.

**So what's missing?** Acumatica's behavior with graph extension PXAction:

- The action **IS** auto-registered into the graph's available action set
- It **DOES** appear in the screen's "Actions" dropdown menu (the `...` button)
- It does **NOT** auto-promote to the top-level toolbar — that requires explicit ASPX-level promotion via `<callbackcommand>` + `PXToolBarButton` registration

The test docstring explicitly says "toolbar button" — design intent was top-level toolbar, not buried in Actions menu.

### Recommended fix path — needs Kevin call

**Option A — Promote to toolbar via project.xml ASPX edit.** Add a `<Page path="~/pages/po/po301000.aspx">` block with toolbar customization:

```xml
<Page path="~/pages/po/po301000.aspx">
  <PXFormView ID="form" ...>
    <Children Key="ActionBar">
      <AddItem><PXToolBarButton ...DataItem="ViewContainer".../></AddItem>
    </Children>
  </PXFormView>
</Page>
```

Cost: ~10 lines of project.xml. **Risk:** like the workspace fix, modifying ASPX/toolbar via project.xml may interact with other customizations. PO301000 is also extended by other Heritage customizations (AesthetikWMS, etc.) — collision possible.

**Option B — Fix the test instead.** Update the test to look in the Actions dropdown menu (click "..." then look for "Container Tracking"). Reframe the design intent: action is available but not prominently surfaced. Lower-effort, lower-risk.

**Option C — ASPX file direct edit.** If the page already has a SB501000.aspx in the customization (`Customization/AesthetikContainers/Pages/SB/SB501000.aspx`), there's no PO301000.aspx in this customization — it'd be a new file. More invasive.

---

## Decision matrix for Kevin

| Failure | Recommended | Risk | Effort |
|---|---|---|---|
| Workspace sidebar | Option A — CustomizationPlugin row insertion | Low (idempotent, no schema declaration) | ~1 hour C# + DLL rebuild + deploy |
| PO301000 button | Option B — fix the test | Lowest | ~15 min Python |

**Why this combination:** Workspace fix matters because it's user-visible navigation. Button fix is testing internal API surface — the action exists, users can reach it via Actions menu. Lowering test expectations matches the easier user-side workaround.

## Production impact (right now)

Sandbox-gate failure on PR #285 means **production deploys are blocked**. Any future customization PR will fail at sandbox-gate the same way until these 2 tests pass or are overridden.

**Workaround until fixed:** Use `OVERRIDE_TEST_GATE=true` workflow_dispatch input to force a deploy past the gate. This was added in PR #221 specifically for known-broken-but-acceptable test states.

## Files referenced

- `tests/ui/test_container_tracking.py:166-175` — button test
- `tests/ui/test_container_tracking.py:235-243` — workspace test
- `Customization/AesthetikContainers/project.xml` — 1781 lines, current state lacks MUI registration + button promotion
- `src/StudioB.Containers/Graphs/POOrderEntry_Extension.cs:13` — `ViewContainer` action source
- `src/StudioB.Containers/Graphs/AesthetikContainersInstall.cs` — CustomizationPlugin (where Option A workspace fix would go)
- Commit `9c557d1` — original workspace add (PR #203)
- Commit `85e6542` — emergency workspace removal
- Commit `e3f76b8` — original button add (PR #70, "Sprint 2: PO toolbar button")
