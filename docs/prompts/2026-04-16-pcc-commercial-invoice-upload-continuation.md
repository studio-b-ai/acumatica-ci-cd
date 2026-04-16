# Continuation — PCC commercial invoice upload (SB501000)

## Your task
Build invoice-upload capability for SB501000 ("Container Maintenance" /
PCC). Staff drops a commercial invoice (.xlsx today; maybe .pdf later),
the screen populates `UsrContainerPOLink` rows with **yards actually on
the container**. Core distinction: "yards on container" ≠ "yards on PO"
— supplier often ships more/less than ordered, so a new
`UsrContainerPOLink.ContainerQty` field is needed (distinct from the PO
line's `OrderQty`).

Architecture should mirror the Bolt WMS packing-slip parser Kevin
already built — LLM-based extraction (Claude reads the workbook,
returns structured rows), not column-mapped parsing. Supplier formats
vary; a growing training fixture set drives prompt quality.

## P0 — before any design or code
1. **Confirm Kevin has dropped ≥10 sample invoices** into a known
   location (`~/Downloads` or a shared folder). A training set <10 will
   over-fit the Krishna format. If fewer are present, stop and ask him
   to collect the rest. Do not proceed on a smaller corpus.
2. Read the seed example:
   `~/Downloads/Krishna 026-25-26.xlsx` (Krishna Fabrics, 2026-03-18,
   invoice #026-25-26; has 4 sheets — primary with friendly names,
   `(2)` variant with Acumatica-style codes, plus `Sheet1` / `DRAFT`
   bale-level packing lists).

## P1 — gather context BEFORE asking Kevin design questions
- **Prior art:** `/recall "packing slip parser Bolt WMS"` — Kevin built
  the LLM parser for Bolt WMS (heritage-wms app in the `studiob`
  monorepo). Read its prompt, fixture layout, output schema, and
  calling pattern before proposing a design. This feature should
  plug into the same pipeline where sensible.
- **Acumatica data model:**
  `src/StudioB.Containers/DACs/UsrContainerPOLink.cs` — has no quantity
  field today; needs `ContainerQty` (DBDecimal, nullable).
- **Screen & existing upload UX:**
  `Customization/AesthetikContainers/Pages/SB/SB501000.aspx` — the
  `ImportForwarderCSV` callback + `ForwarderImportParser.cs` graph are
  prior-art for file-upload UX on the same screen. Copy that pattern
  for the ASPX SmartPanel / graph wiring.
- **Repos in play:**
  - `acumatica-ci-cd` — DAC, graph, ASPX, Install plugin
  - `studiob` (heritage-wms app) — likely host for the shared LLM
    parser logic if we fold into the Bolt WMS path
  - `webhook-router` — candidate intermediary if Acumatica can't call
    the LLM directly
- **Reference (do NOT touch):** PR #439 (merged 2026-04-16 18:00 ET)
  fixed three residual SB501000 PR#366 bugs. Use its SmartPanel /
  LoadOnDemand patterns as a cheat-sheet, but this feature is a new
  PR on a new branch.

## P2 — THEN ask Kevin these questions (not before)
1. Invoice corpus location + count — are ≥10 gathered?
2. **Pattern/color → Acumatica InventoryCD mapping.** Krishna codes
   (`COPLEYST`, `IVORY`) are truncated; real CD likely longer. Is
   there an existing cross-reference table, or do we need to build
   one? Maintained where — Acumatica DAC, GI, or external?
3. **PO-line disambiguation.** PO263 has two invoice rows (Ivory +
   Oatmeal) — LLM must pick the right `LineNbr` by inventory match.
   If the inventoried PO line doesn't exist: (a) error and block
   upload, (b) auto-add a PO line, (c) flag the row for manual
   review in a preview UI?
4. **Upload UX.** Preview-then-commit (show matched + unmatched rows,
   user resolves unmatched before the DB write) or one-shot with
   post-hoc reconciliation screen?
5. **Bale-level packing-list detail** (`Sheet1` / `DRAFT` — roll-by-
   roll yards + weights). Do we add a `UsrContainerBale` DAC now to
   capture per-bale yardage for WMS receiving, or later phase?
6. **Auto-attach the uploaded .xlsx** to the container as a Document
   (Documents tab / CR Notes files) on successful import?
7. **Parser host + LLM call path.** Parser in heritage-wms shared
   with Bolt WMS, or new C# plugin in `StudioB.Containers`? How does
   Acumatica reach the LLM — direct Anthropic API from the graph, or
   via webhook-router as intermediary?
8. **Duplicate-upload detection key.** `(InvoiceNbr, InvoiceDate,
   Supplier)` — idempotent on re-upload?
9. **PO type filter.** RO (regular order), Normal, or mixed? Affects
   BQL lookup.
10. **Error reporting.** Inline in the preview panel, or routed to a
    Slack channel?

## CLAUDE.md discipline reminders
- Rule 20 — verify against live sandbox via Playwright before
  proposing C#/ASPX fixes
- Rule 11 — every publish restarts the app pool; deploy only after
  6 PM ET weekdays or weekends
- Rule 14 — edit `.aspx` under `Customization/*/Pages/`, never
  project.xml CDATA directly; run `python3
  scripts/sync-aspx-cdata.py` after
- Rule 13 — `ls /Users/kevin/dev/acumatica-ci-cd/Customization/`
  before designing around any package
- Rule 24 — `<Sql>` scripts in project.xml don't re-run on
  subsequent `merge=true` publishes; use
  `AesthetikContainersInstall.cs` (CustomizationPlugin) for anything
  that must run every deploy (new DAC fields auto-handled by the
  schema publisher, but install data is not)
