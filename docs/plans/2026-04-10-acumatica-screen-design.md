# AcumaticaScreen — Iframe-Aware Test Context

**Date:** 2026-04-10
**Status:** Approved
**Scope:** `tests/ui/acumatica_screen.py` + `conftest.py` fixture

## Problem

Acumatica renders all screen content inside `iframe[name='main']`. Playwright's `page.locator()` does not pierce iframes. This causes three recurring classes of bugs:

1. **Vacuous passes** — `page.locator("text=X")` returns `count=0` silently because it searches the top document, not the iframe. Tests pass when they shouldn't.
2. **frame.evaluate() flake** — `frame.evaluate()` intermittently returns empty string despite the field being visually populated. Currently xfailed in `test_uom_migration.py` since 2026-04-08.
3. **Screen shadowing** — customizations can shadow a ScreenID, causing `/Main?ScreenId=X` to redirect to the home page. The iframe never loads the form.

Secondary issues:
- 67 hardcoded `wait_for_timeout()` calls (500ms–8s) instead of readiness signals
- `frame: Frame | None = None` parameter threaded through 12+ helper functions
- GI screens require manual routing via a hardcoded `GI_SCREEN_IDS` set
- No retry logic anywhere in the test infrastructure

## Solution

A single `AcumaticaScreen` class that wraps `Page` + frame resolution. All DOM operations go through it. Existing helpers remain untouched — tests migrate gradually.

## Class API

### Construction

```python
class AcumaticaScreen:
    page: Page           # raw Playwright page (keyboard, dialogs, top-level nav)
    ctx: Frame | Page    # resolved DOM context (iframe or direct page)
    screen_id: str
    mode: Literal["iframe", "direct"]
```

Two class methods:

| Method | Use case |
|--------|----------|
| `AcumaticaScreen.navigate(page, "IN202500", params="InventoryCD=00004")` | Standard — auto-detects shadowing + GI routing |
| `AcumaticaScreen.direct(page, "/Pages/PO/PO301000.aspx")` | Explicit bypass of Main wrapper |

### navigate() internals

1. If screen_id starts with `GI` → route to `/GenericInquiry/GenericInquiry.aspx?id=X`
2. Otherwise → navigate to `/Main?ScreenId=X&{params}`
3. Poll for `iframe[name='main']` to attach and have content (replaces 8s magic timeout)
4. Check for shadowing: if URL contains `ScreenId=00000000` → auto-fallback to direct-aspx, log warning, set `mode="direct"`
5. Poll for form readiness (`#ctl00_phF_form` OR `#ctl00_phF_frmFilter` OR `[id*=grid]`)
6. Return `AcumaticaScreen` instance

### DOM Methods

| Method | Signature | Replaces |
|--------|-----------|----------|
| `locator` | `(selector) -> Locator` | `_get_frame(page, frame).locator(...)` |
| `set_field` | `(field_id, value)` | `set_field_value(page, id, val, frame=frame)` |
| `get_field` | `(field_id) -> str` | `get_field_value(page, id, frame=frame)` — with retry |
| `evaluate` | `(js, retries=3, delay_ms=500)` | `frame.evaluate(js)` — with retry |
| `save` | `()` | `save_order(page, frame)` / `save_record(page)` |
| `wait_ready` | `(timeout=15_000)` | `wait_for_screen_ready(page, timeout, frame)` |
| `click_toolbar` | `(action: str)` | `click_add_new()`, `click_delete()`, etc. |
| `find_fields` | `(field_names: list[str]) -> dict[str, bool]` | `find_custom_fields(page, names, frame)` |

### Retry Mechanism

The `evaluate()` method retries on empty/null results:

```python
def evaluate(self, js: str, *, retries: int = 3, delay_ms: int = 500):
    for attempt in range(retries):
        result = self.ctx.evaluate(js)
        if result not in (None, ""):
            return result
        if attempt < retries - 1:
            self.page.wait_for_timeout(delay_ms)
    return result  # return last attempt even if empty
```

`get_field()` uses this internally. The xfail in `test_uom_migration.py` should be removable.

### Smart Waits

Replace magic timeouts with poll-based readiness checks:

```python
def _wait_for_frame(self, timeout: int = 15_000):
    """Poll for iframe[name='main'] to exist and have content."""
    self.page.wait_for_function(
        "() => { const f = document.querySelector('iframe[name=main]'); "
        "return f && f.contentDocument && f.contentDocument.body "
        "&& f.contentDocument.body.children.length > 0; }",
        timeout=timeout,
    )

def _wait_for_form(self, timeout: int = 15_000):
    """Poll for form container in the resolved context."""
    self.ctx.wait_for_function(
        "() => document.querySelector('#ctl00_phF_form') !== null "
        "|| document.querySelector('#ctl00_phF_frmFilter') !== null "
        "|| document.querySelector('[id*=grid]') !== null",
        timeout=timeout,
    )
```

### Error Detection

`navigate()` checks for common failure modes after loading:

- `ScreenId=00000000` in URL → screen shadowed (auto-fallback)
- `ScreenId=ERROR` in URL → raise with screen ID
- `"type is not found"` or `"igcm.dac"` in body → raise with details

## Fixture

```python
# conftest.py
@pytest.fixture
def acumatica_screen(acumatica_page):
    """Factory fixture — call with screen_id to get an AcumaticaScreen."""
    def _navigate(screen_id: str, **kwargs) -> AcumaticaScreen:
        return AcumaticaScreen.navigate(acumatica_page, screen_id, **kwargs)
    return _navigate
```

## Migration

### What changes

- New file: `tests/ui/acumatica_screen.py` (~200 LOC)
- New fixture in `conftest.py` (~5 LOC)

### What stays

- All existing functions in `helpers.py` — untouched, not removed
- All existing test files — unchanged until individually migrated
- Login flow, browser context, dialog capture — unchanged

### Migration order

1. Ship `AcumaticaScreen` + fixture (this PR)
2. Migrate `test_uom_migration.py` — remove xfail, use `screen.get_field()` (immediate win, proves the retry mechanism)
3. Other test files migrate opportunistically — no forced timeline

## Incident Context

From session history (`/recall`):
- **2026-04-08**: `test_container_tracking.py` vacuous-pass blocked SB501000 prod deploy. Root cause: `page.locator()` doesn't pierce iframes + screen shadowing. Took 2-3 iterations to untangle.
- **2026-04-08**: `frame.evaluate()` empty-string flake discovered on `test_uom_migration.py`. Marked xfail, never fixed.
- **2026-04-09**: UOM Class B corruption incident required UI click-Save test (`test_uom_migration.py:TestStockItemSaveSample`) — had to work around iframe issues with manual `page.frame("main") or page` fallback.
- **2026-03-15**: Multiple `locator.fill` errors on iframe-scoped elements in unrelated Playwright sessions.
