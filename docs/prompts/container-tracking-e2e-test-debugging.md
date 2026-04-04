# Container Tracking — E2E Test Debugging & Completion

## Context

On 2026-04-04, we shipped Container Tracking Phase 1 cleanup + Phase 2-3 (PRs #169, #171, #172, #173, #175, #176). All 10 screens deploy and load without errors. But the Playwright E2E tests that verify screen **functionality** (not just loading) are marked `xfail` because Acumatica renders all screen content inside `iframe[name='main']` and uses div-based form controls instead of native HTML inputs.

The workspace integrity tests (10 screens, error detection) pass and are enforced. The CRUD, GI column, seed data, PXSelector, and cross-screen E2E tests are skeleton code that fails on DOM selectors.

## Goal

1. Fix all xfail tests so they pass — remove the `_xfail_dom` marker
2. Every link in the Container Tracking workspace must be reachable and functional
3. Full E2E test results proving screens and workflows work end-to-end

## What's Broken and Why

### The iframe problem

Acumatica's frameset structure:
```
page (top)
  ├── sidebar (navigation)
  ├── frame[name='main'] ← ALL screen content lives here
  │     ├── form (#ctl00_phF_form)
  │     ├── grid (#ctl00_phG_grid)
  │     ├── toolbar (#ctl00_phDS_ds_ToolBar_Insert, _Save, _Delete)
  │     └── tabs (#ctl00_phG_tab)
  ├── frame[name='quickHelp']
  └── frame[name='help']
```

`page.locator()` auto-searches frames for element matching, BUT `page.wait_for_function()` executes JS only in the top frame. All helpers that use `wait_for_function` (like `assert_grid_visible`) must use `frame.wait_for_function()` instead.

**Helper already added:** `get_main_frame(page)` in `helpers.py` returns the `main` frame. All helpers have been updated to use it, but the selectors inside them are wrong.

### Specific selector issues discovered

| Helper | Issue | Fix needed |
|--------|-------|------------|
| `assert_grid_visible()` | GI grids don't match `[id*=grid]` in the main frame — GI content may load in yet another nested frame, or use different class names | Run headed, inspect GI DOM |
| `set_field_value()` | ContainerCD is a `<div class="selector">`, not `<input>`. The actual input is `#ctl00_phF_form_edContainerCD_text` | Use `_text` suffix for selector fields |
| `click_add_new()` | Button ID is `ctl00_phDS_ds_ToolBar_Insert` (confirmed working via DOM inspection) | Already fixed, needs retest |
| `assert_field_has_selector_data()` | Dropdown button ID pattern `_ddBtn` may not match | Inspect PXSelector DOM in headed mode |
| `find_custom_fields()` | Searches main frame for `[id*='AutoLinkPOsByRef']` but field may use different ID pattern | Inspect SB302030 DOM |
| Seed data tests | `[id*='TypeCD']` and `[id*='PortCode']` not found — may need `_text` suffix or different ID | Inspect SB302010/SB302020 DOM |

## Debugging Approach

### Step 1: Headed browser inspection

Run each failing screen in headed mode and dump the DOM:

```bash
cd /Users/kevin/dev/acumatica-ci-cd
HEADED=1 ACUMATICA_USERNAME=api-bot ACUMATICA_PASSWORD='<from 1password>' \
  python3 -c "
from playwright.sync_api import sync_playwright
# Login, navigate to screen, then:
# frame = page.frame('main')
# print(frame.content()[:5000])  # dump DOM
# Or use frame.locator('*').all() to enumerate elements
"
```

For each screen, record:
- The toolbar button IDs (Insert, Save, Delete)
- The form field IDs (especially `_text` variants for selector/div fields)
- The grid element IDs and class names for GIs
- The PXSelector dropdown button ID and dropdown row class names

### Step 2: Fix selectors in helpers.py

Update each helper with the correct selectors found in Step 1.

### Step 3: Fix test assertions

Update field IDs in test methods (e.g., `ctl00_phF_form_edContainerCD` → `ctl00_phF_form_edContainerCD_text`).

### Step 4: Run full suite, iterate

```bash
ACUMATICA_USERNAME=api-bot ACUMATICA_PASSWORD='<from 1password>' \
  python3 -m pytest tests/ui/test_container_tracking.py -v --tb=short --timeout=120
```

### Step 5: Remove xfail markers

Once all tests pass, remove the `_xfail_dom` marker and the variable definition at the top of the E2E section.

### Step 6: Final validation

Run the complete suite and capture full output. Every test must pass:
- WorkspaceIntegrity (10 screens)
- IGCM removal (17 screens)
- GI columns (5 GIs)
- Form CRUD (5 screens)
- Seed data verification (types + ports)
- PXSelector dropdowns (ContainerType, PortOfLoading, PortOfDischarge)
- Cross-screen E2E flow (create → verify in GI → delete)

## Key Files

| File | Purpose |
|------|---------|
| `tests/ui/test_container_tracking.py` | All container tracking tests — xfail tests start after `_xfail_dom` marker |
| `tests/ui/helpers.py` | Shared helpers — `get_main_frame()`, `assert_grid_visible()`, etc. |
| `tests/ui/conftest.py` | Session fixtures — `acumatica_page` login, `dialog_messages` capture |

## DOM Discovery Notes (from 2026-04-04 session)

**SB501000 (Container Maintenance) — confirmed via DOM inspection:**
- Add New button: `frame.locator("[id*='ToolBar_Insert']")` → `ctl00_phDS_ds_ToolBar_Insert`
- Form visible: `frame.locator("#ctl00_phF_form")` → True
- ContainerCD field IDs: `ctl00_phF_form_edContainerCD_state`, `ctl00_phF_form_edContainerCD`, `ctl00_phF_form_edContainerCD_text`
- The `_text` variant is the actual editable input
- Events tab: `frame.locator("text=Events")` → 1 match
- Grid events: `ctl00_phG_tab_t0_gridEvents`
- Grid PO Links: `ctl00_phG_tab_t1_gridPOLinks`

**SB401000 (PO Containers GI):**
- main frame URL: `GenericInquiry/GenericInquiry.aspx?id=SB401000`
- Grid elements: needs inspection — `[id*=grid]` returned 0 in main frame
- GI may use different DOM structure than form screens

## Credentials

- api-bot: `op://Studio B Infrastructure/acumatica-api-bot`
- api-bot has full browser/SiteMap access (confirmed 2026-04-04)

## Constraints

- `navigate_to_screen_safe()` + `wait_for_screen()` — never `networkidle`
- All DOM interaction through `get_main_frame(page)` — top page only has sidebar
- Acumatica frameset URL always shows `ScreenId=00000000` — this is normal
- Per-test timeout: 120 seconds
- CI action timeout: 10 minutes total (may need increase if 87+ tests)

## Success Criteria

- [ ] All `_xfail_dom` markers removed
- [ ] Full pytest run: 87+ tests, 0 failures, 0 errors
- [ ] Container Tracking workspace: every link verified by TestWorkspaceIntegrity
- [ ] GI screens: grid renders with expected columns
- [ ] Form screens: create, save, delete lifecycle works
- [ ] Seed data: 6 container types, 20+ ports confirmed
- [ ] PXSelectors: ContainerType, PortOfLoading, PortOfDischarge dropdowns populated
- [ ] E2E flow: container created on SB501000 → visible on SB401000 GI → deleted
- [ ] Screenshot evidence of test results (full pytest output)
