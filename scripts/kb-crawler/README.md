# Acumatica Help Wiki → studiob-knowledge

Crawls `help.acumatica.com`, extracts clean text for every page across every Acumatica guide, and ingests into the `studiob-knowledge` Qdrant collection under `topic=acumatica-help-wiki`.

**AcuDev and other agents use these chunks as their reference for Acumatica internals** — DAC fields, graph extensions, form IDs, REST semantics, workflow API, customization patterns, end-user workflow documentation, etc.

## Layout

```
scripts/kb-crawler/
  crawl.py                      # unified enumerate/fetch/ingest/monthly CLI
  guides.json                   # root pageid + tree_guid per guide (discovered once via Playwright)
  pages/{pageid}.json           # cached page content — one file per Acumatica wiki page
  state/
    tree_nodes.json             # full tree enumeration per guide (input for fetch)
    tree_nodes.json.bak-{ts}    # previous monthly snapshots
    enum.log / fetch.log / ingest.log
  README.md
```

## Guides covered (51)

- **Distribution** (3): invmgmt, ordermgmt, crm
- **Manufacturing** (1): manufacturing
- **End User** (22): general_ledger, accounts_payable, accounts_receivable, cash_management, taxes, credit_policy, currency_management, deferred_revenue, fixed_assets, automated_warehouse, organization_management, project_accounting, field_services, contract_management, prices_discounts, construction, payroll, retail_commerce, modern_customer_portal, self_service_portal, getting_started
- **Administrator** (4): sys_admin, integration, portal_admin, modern_portal_admin
- **Implementation Consultant** (6): installation, implementation, finance_migration, reporting, workflow_ui, dac_overview
- **Developer** (10): framework, customization, customization_update, workflow_api, integration_dev, mobile_framework, plugin_dev, unit_test, barcode_engine, platform_api
- **UI Developer** (3): ui_development, ui_components, frontend_api
- **Reference** (6): formref, release_notes, user_interface, form_quick_ref, report_reference, customization_tool_ref

## Usage

### One-time setup

```bash
# Install deps
pip3 install beautifulsoup4 lxml certifi requests playwright
python3 -m playwright install chromium

# Discover guide roots (uses Playwright; only needed if Acumatica changes their landing page)
python3 crawl.py discover
```

### Manual operations

```bash
# Load credentials (one-time per shell)
cd ~/dev/studiob && railway link --project studiob-platform --environment production
export QDRANT_URL=$(railway variables --service acudev --json | python3 -c "import sys,json; print(json.load(sys.stdin)['QDRANT_URL'])")
export VOYAGE_API_KEY=$(railway variables --service acudev --json | python3 -c "import sys,json; print(json.load(sys.stdin)['VOYAGE_API_KEY'])")

cd ~/dev/acumatica-ci-cd/scripts/kb-crawler

# List known guides and their current node counts
python3 crawl.py list

# Enumerate tree(s) — walks /ui/helptree/{pid} recursively per guide
python3 crawl.py enumerate                      # all guides not yet enumerated
python3 crawl.py enumerate formref framework    # specific guides

# Fetch page content (cache-aware, parallel)
python3 crawl.py fetch                          # all
python3 crawl.py fetch formref --parallelism 15
python3 crawl.py fetch --force                  # re-fetch cached

# Ingest to Qdrant (chunks @ 1800 chars / 200 overlap, voyage-3 embeddings)
python3 crawl.py ingest                         # all cached pages
python3 crawl.py ingest --delete-prior          # wipe topic=acumatica-help-wiki first

# Full one-shot per guide
python3 crawl.py all formref

# Monthly full refresh (backs up tree state, re-enumerates everything, fetches deltas, re-ingests)
python3 crawl.py monthly
```

### Monthly cron

A scheduled task runs the monthly refresh automatically:

- **Task:** `acumatica-kb-monthly-refresh`
- **Schedule:** `17 4 2 * *` (04:17 AM local, 2nd of every month)
- **Managed via:** `.claude/scheduled-tasks/acumatica-kb-monthly-refresh/SKILL.md`
- **What it does:** Backs up old tree state, re-enumerates all 51 guides, fetches any new/changed pages, deletes the old `topic=acumatica-help-wiki` chunks from Qdrant, and re-ingests fresh.

## Payload schema

Every chunk upserted to `studiob-knowledge` has:

```json
{
  "domain": "acumatica",
  "client": null,
  "source": "acumatica-help-wiki",
  "source_type": "help-wiki",
  "topic": "acumatica-help-wiki",
  "guide": "Inventory Management",
  "guide_slug": "invmgmt",
  "edition": "distribution",
  "title": "Inventory Planning with MRP: General Information",
  "pageid": "b47187f3-3102-4b7e-af80-b4ed6d394850",
  "tree_depth": 2,
  "source_url": "https://help.acumatica.com/Help?ScreenId=ShowWiki&pageid=...",
  "chunkIndex": 0,
  "chunkCount": 5,
  "hasCode": false,
  "text": "...",
  "ingested_at": 1728487200
}
```

Filter for retrieval:

```json
{"must":[
  {"key":"domain","match":{"value":"acumatica"}},
  {"key":"topic","match":{"value":"acumatica-help-wiki"}}
]}
```

Scope to one guide:

```json
{"must":[
  {"key":"guide_slug","match":{"value":"invmgmt"}}
]}
```

## How tree enumeration works

Acumatica's help site uses a lazy-loaded JS tree. Each page renders:

```html
<div id="helpTree"></div>
<script>window._helpTree = { dataSourceUrl: "ui/helptree", target: "help", ... };</script>
```

On load, the tree control calls `/ui/helptree/{tree_guid}?selected={pageid}` once to fetch its top-level siblings. When the user expands a parent node, the control calls `/ui/helptree/{node_pageid}` to fetch that node's children.

The crawler reproduces this pattern:

1. **`discover`** — Playwright opens each guide's landing card, captures the `{tree_guid}` from the network request, records root `{pageid}`.
2. **`enumerate`** — Calls `/ui/helptree/{tree_guid}?selected={root_pid}` for the top level, then recursively calls `/ui/helptree/{node_pid}` for every `hasChildren=true` node. Cookies are reused across calls for session auth.
3. **`fetch`** — For each discovered pageid, `GET /Wiki/Show.aspx?pageid={pid}&HideScript=On`, extract the `div.wiki` body, strip boilerplate (navigation chrome, edit links, etc.).
4. **`ingest`** — Paragraph-aware chunking (1800 chars / 200 overlap), voyage-3 embeddings, upsert to Qdrant.

## Known quirks

- **Wiki markup leakage** — The `div.wiki` container includes both rendered HTML and raw wiki markup footer (`[HelpRoot_FormReference\AM_10_00_00|...]` style). Embedding quality is fine; display-layer consumers may want a second-pass markup stripper.
- **Tree GUIDs aren't always unique per guide** — e.g., `20f237dd-409f-4338-b5ef-39cff26e191X` is a pattern. Verified in `discover_roots.py` — some guides legitimately share a tree with a sibling guide.
- **2 guides need pageid patching** — `getting_started` and `currency_management` don't expose their root pageid via the landing card click; we patch from the tree's top node instead. Handled automatically in `discover_roots.py`.
- **Some short pages** (< 200 chars) are skipped as empty. These are legitimate — mostly single-line Acumatica placeholder pages.
- **Respect business hours if forcing a full re-fetch.** At default parallelism=10 a full refresh pulls ~5000 pages in 20-40 minutes. No impact on production Acumatica, but be polite to help.acumatica.com.
