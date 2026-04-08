# SB501000 KPI Tile Layout — Approved Spec

**Date:** 2026-04-07
**Status:** Approved (greenlit 2026-04-07)
**Parent:** 2026-04-07-sb501000-command-center-design.md

## Structure

Three tiles, equal width, horizontal row across the top of SB501000. Each tile is clickable and filters the container grid to a corresponding view.

## Color tokens

```css
:root {
  --risk-critical: #d64045;
  --risk-critical-bg: #fdecea;
  --risk-critical-bg-hover: #fadcd9;
  --risk-warning: #e8a33d;
  --risk-warning-dark: #b37517;
  --risk-warning-bg: #fef5e7;
  --risk-warning-bg-hover: #fcebd3;
  --accent: #1d3557;
  --accent-bg: #ebf0f7;
  --accent-bg-hover: #dde6f1;
  --risk-ok: #2d8a5f;
  --risk-neutral: #4a5568;
}
```

## Tile 1 — ACTION REQUIRED

- **Purpose:** Count of containers with `RiskLevel = CRITICAL`
- **Left border:** 4px solid `--risk-critical`
- **Background:** `--risk-critical-bg`
- **Marker:** `●` in `--risk-critical`
- **Top-right label:** `ACTION` — 11px uppercase, letter-spacing 0.08em, color `--risk-critical`
- **Main number:** 48px, font-weight 300, tabular-nums, color `--risk-critical`
- **Main label:** `CONTAINERS NEED ACTION` — 10px uppercase
- **Subtext** (up to 3 bullets, 11px tabular-nums, color `--risk-neutral`):
  - `• N PAST LFD · $X/DAY`
  - `• N CUSTOMS HOLD > 2D`
  - `• N ISF CUTOFF < 6H`
- **Click:** sets `ContainerFilter.ViewMode = 'EXCEPTIONS'`, grid reloads
- **Hover:** background → `--risk-critical-bg-hover`
- **Empty state:** number `0`, label `NO CRITICAL ITEMS`, desaturate to green accent

## Tile 2 — WATCH

- **Purpose:** Count of containers with `RiskLevel = WARNING`
- **Left border:** 4px solid `--risk-warning`
- **Background:** `--risk-warning-bg`
- **Marker:** `◆` in `--risk-warning`
- **Top-right label:** `WATCH` — color `--risk-warning-dark`
- **Main number:** 48px, tabular-nums, color `--risk-warning-dark`
- **Main label:** `CONTAINERS ON WATCHLIST`
- **Subtext:**
  - `• N ETA SLIPPED 7D`
  - `• N DOCS INCOMPLETE`
  - `• N ARRIVE IN 7D`
- **Click:** sets `ContainerFilter.ViewMode = 'WATCH'`
- **Hover:** background → `--risk-warning-bg-hover`
- **Empty state:** number `0`, label `NOTHING ON WATCH`

## Tile 3 — $ EXPOSURE

- **Purpose:** Total projected financial exposure in next 7 days
- **Left border:** 4px solid `--accent`
- **Background:** `--accent-bg`
- **Marker:** `$` in `--accent`, bold
- **Top-right label:** `EXPOSURE` — color `--accent`
- **Main number:** 40px (smaller to fit dollar amounts), tabular-nums, color `--accent`
- **Number format:** `$12,400` — USD, comma-separated, no decimals when ≥$1000, round to nearest dollar
- **Main label:** `AT RISK THIS WEEK`
- **Subtext** (right-aligned amounts within bullet):
  - `• $X,XXX DEMURRAGE`
  - `• $X,XXX DUTY VAR`
  - `• $X,XXX OTHER`
- **Click:** opens `PXSmartPanel` with full exposure breakdown table by container
- **Hover:** background → `--accent-bg-hover`
- **Empty state:** number `$0`, label `NO EXPOSURE`

## Tile dimensions

- Width: `calc(33.333% - 14px)`, 20px gap between tiles
- Height: 140px fixed
- Padding: 18px 20px
- Box-sizing: border-box
- Display: inline-block for ASPX compatibility

## Rendering approach

**Server-side HTML string generation.** `ContainerFilter` exposes a `KPITilesHtml` field populated in `RowSelected<ContainerFilter>`. ASPX renders via `PXHtmlView` bound to that field. Click handlers inline via `onclick` attributes that call Acumatica's action dispatcher.

**Why not three `PXButton`s:** buttons inject chrome that breaks the layout and can't contain multi-line subtext cleanly.

**Why not a custom `.ascx` control:** `PXHtmlView` + string builder is sufficient and has fewer moving parts for v1.

## Behaviors

1. **Initial load:** tiles render current-period data; grid shows CRITICAL+WARNING rows by default (Exceptions view).
2. **Tile click:** grid filters, view selector tab highlights to match, filter persists in `Filter.ViewMode`.
3. **Tile click again (same tile):** clears filter, returns to default Exceptions view.
4. **Calculation-in-progress:** show `—` and `CALCULATING…` label, never ambiguous `0`.
5. **Double-click:** no effect.
6. **Keyboard:** tabbable, Enter activates, 2px accent outline on focus.

## What the tiles are NOT

- Not animated (no fade, no counter roll-up, no pulse)
- Not a chart (no sparklines)
- Not user-configurable (fixed 3 tiles; thresholds configurable, layout not)
- Not the only KPI surface (Unbilled LC MTD lives in detail pane, not top row)

## Approval

Greenlit by Kevin on 2026-04-07. Any deviation from this spec during implementation requires a new approval.
