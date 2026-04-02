# Audit-Driven UI Regression Tests

**Date:** 2026-04-02
**Status:** Approved

## Problem

Post-deploy validation currently has two layers:
1. **REST API smoke tests** (`test_audit_derived.py`) — verify entities are queryable
2. **UI tests** (`tests/ui/test_auto_allocation.py`) — verify one specific bug fix

Neither layer catches "screen X broke after deploy" for the dozens of screens users actually use daily. The audit trail tells us exactly which screens and fields are in active use — we should use that to generate UI regression tests automatically.

## Design

### Architecture

```
OData (StudioBAuditTrail GI)
  │
  ▼
generate_ui_fixtures.py ─── pulls last 30 days of audit data
  │                         groups by screen_id
  │                         extracts: fields touched, custom fields, operation types
  ▼
tests/fixtures/ui_screens.json ─── one entry per screen
  │
  ▼
tests/ui/test_screen_smoke.py ─── parameterized Playwright tests
  │                                 navigate → assert load → check fields
  ▼
CI pipeline (post-deploy-validation job)
```

### Fixture Format (`ui_screens.json`)

```json
[
  {
    "screen_id": "SO301000",
    "screen_name": "Sales Orders",
    "record_count": 4500,
    "custom_fields": ["UsrHubSpotDealId", "UsrBoltID"],
    "tables_touched": ["SOOrder", "SOLine", "SOLineSplit"],
    "operations": ["Created", "Modified"],
    "last_seen": "2026-04-01T15:30:00"
  }
]
```

### What Each Smoke Test Does

Per screen entry:
1. Navigate to `{ACUMATICA_URL}/Main?ScreenId={screen_id}`
2. Wait for `networkidle` + form container visible (generic `#ctl00_phF_form` or grid `#ctl00_phG_grid`)
3. Assert no browser error dialogs fired
4. If screen has custom fields (`Usr*`): locate field elements in DOM by partial ID match
5. On failure: Playwright captures screenshot automatically

### File Changes

| File | Action | Purpose |
|------|--------|---------|
| `scripts/generate_ui_fixtures.py` | New | OData pull → fixture JSON |
| `tests/ui/test_screen_smoke.py` | New | Parameterized Playwright smoke tests |
| `tests/ui/conftest.py` | Edit | Add generic `acumatica_screen` fixture |
| `tests/ui/helpers.py` | Edit | Add `navigate_to_screen()`, `assert_screen_loaded()`, `find_custom_fields()` |
| `.github/workflows/deploy-customization.yml` | Edit | Add fixture generation step before UI test run |

### CI Integration

In `post-deploy-validation` job, before running pytest:
```yaml
- name: Generate UI test fixtures from audit data
  env:
    ACUMATICA_URL: ...
    ACUMATICA_USERNAME: ...
    ACUMATICA_PASSWORD: ...
    ACUMATICA_TENANT: ...
  run: python scripts/generate_ui_fixtures.py --days 30 --output tests/fixtures/ui_screens.json
```

### Extensibility for Workflow Replay (Phase 2)

The fixture format supports an optional `workflow_steps` array per screen. Phase 2 would populate this from `WorkflowPath` patterns and `test_screen_smoke.py` would replay them:

```json
{
  "screen_id": "SO301000",
  "workflow_steps": [
    {"action": "click_new", "selector": "div[icon='AddNew']"},
    {"action": "set_field", "field_id": "ctl00_phF_form_edOrderType", "value": "SO"},
    {"action": "save", "method": "ctrl_s"}
  ]
}
```

Not implementing in this PR — just designing the fixture format to accommodate it.

## Decisions

- **Fresh pull every deploy** — not stale weekly fixtures. OData call adds ~10s to CI.
- **All audit-observed screens** — not just top N. Broadest regression net.
- **Smoke-first, workflows later** — Phase 1 catches broken screens/fields. Phase 2 replays workflows.
- **Shared helpers** — `navigate_to_screen()` and `assert_screen_loaded()` are reusable by future workflow tests.
