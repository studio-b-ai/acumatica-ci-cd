# `acuops-agent` GitHub App — provisioning + migration plan

**Goal:** Replace `GH_PAT_DISPATCH` (Kevin's personal PAT) with a **GitHub App identity** named `acuops-agent` for all cross-repo operations across the Studio B portfolio. Closes Safety Package gate #2 for the in-flight Phase 4 AI Failure Recovery agent re-enablement.

**Multi-tenant intent:** App is provisioned at the studio-b-ai org level so it can install on Studio B's own repos AND on customer/VAR client repos in the future. Per-installation scoping keeps Heritage / Aesthetik / future clients isolated.

---

## Why GitHub App, not service-account PAT

| | GitHub App | Service-account PAT |
|---|---|---|
| Audit attribution | `acuops-agent[bot]` ✅ | named user e.g. `studiob-bot` |
| Token expiry | none — auto-mint per run | 30-90d, manual rotation |
| Cost | free | ~$4/mo per seat |
| Anthropic claude-code-action support | native via `actions/create-github-app-token@v1` | works but requires custom step |
| Multi-tenant scoping | per-installation, granular | one PAT = same scope everywhere |
| Setup cost | ~1hr one-time | 5 min, recurring rotation pain |

**Source:** studiob-knowledge KB doc `Auto-dispatcher PAT attribution — agents look like Kevin` explicitly endorses both paths; tiebreaker is operational maintenance + audit clarity.

---

## Manual steps for Kevin (≈1 hour)

### Step 1 — Create the App at the org level

1. Visit `https://github.com/organizations/studio-b-ai/settings/apps/new`
2. Fields:
   - **GitHub App name:** `acuops-agent`
   - **Description:** `Studio B AcuOps automation — cross-repo dispatches, recovery agent operations, deploy orchestration. Used across Studio B's own repos and customer VAR client installations.`
   - **Homepage URL:** `https://github.com/studio-b-ai`
   - **Webhook:** **DISABLED** (uncheck "Active") — we don't need webhook events; this is a token-mint identity only
3. **Repository permissions** (set, leave others as "No access"):
   - Contents: **Read & write**
   - Pull requests: **Read & write**
   - Issues: **Read & write**
   - Actions: **Read & write** (for `gh workflow run` cross-repo dispatches)
   - Metadata: **Read** (auto-required)
4. **Organization permissions:** all `No access`
5. **Where can this GitHub App be installed?**
   - Select **Any account** (allows future customer installations on their own orgs/repos)
   - For tonight, only studio-b-ai org will install
6. Click **Create GitHub App**

### Step 2 — Generate the private key

After creation, on the App's settings page:

1. Scroll to **Private keys** section
2. Click **Generate a private key**
3. Browser downloads `acuops-agent.YYYY-MM-DD.private-key.pem`
4. **Capture the App ID** (shown at the top of the App settings page, e.g. `1234567`) — you'll need this in Step 4

### Step 3 — Store the private key in 1Password

1. Open 1Password → Studio B Infrastructure vault (or create one if missing)
2. Create new **Secure Note** item titled `acuops-agent GitHub App private key`
3. Add fields:
   - **App ID:** `<the App ID from Step 2>`
   - **Generated:** `2026-04-08`
   - **Permissions:** `Contents:rw, Pull Requests:rw, Issues:rw, Actions:rw, Metadata:r`
4. Attach the `.pem` file
5. **Delete the downloaded .pem from `~/Downloads/`** — the only canonical copy lives in 1Password

### Step 4 — Install the App on the studio-b-ai org

1. Visit the App's public install page (linked from App settings → "Install App")
2. Choose **studio-b-ai** org
3. Select **Only select repositories** and add:
   - `acumatica-ci-cd`
   - `acuops-pipeline`
   - `webhook-router`
   - `acudev`
   - `acuops`
   - `aesthetik-platform`
   - `studiob-acumatica-ci-cd-template`
4. Click **Install**
5. **Capture the Installation ID** from the resulting URL: `https://github.com/organizations/studio-b-ai/settings/installations/<INSTALLATION_ID>` — you'll need this to verify per-org access

### Step 5 — Add the App credentials as GitHub Actions secrets/variables

For **each** repo in the install list above, run (substituting App ID and Installation ID):

```bash
# As variables (not secrets — these aren't sensitive)
gh variable set ACUOPS_AGENT_APP_ID --org studio-b-ai --visibility selected --repos "acumatica-ci-cd,acuops-pipeline,webhook-router,acudev,acuops,aesthetik-platform,studiob-acumatica-ci-cd-template" --body "<APP_ID>"

# As an org-level secret with selected-repo visibility
gh secret set ACUOPS_AGENT_PRIVATE_KEY --org studio-b-ai --visibility selected --repos "acumatica-ci-cd,acuops-pipeline,webhook-router,acudev,acuops,aesthetik-platform,studiob-acumatica-ci-cd-template" < /path/to/acuops-agent-private-key.pem
```

**Then immediately shred the local pem** if it's still on disk:
```bash
shred -u /path/to/acuops-agent-private-key.pem  # macOS: rm -P
```

### Step 6 — Add Railway env vars for hosted services

`webhook-router` and `acudev` are Railway-hosted services that contain code-level dispatchers. They need the App credentials as env vars for runtime use:

```bash
cd ~/dev/webhook-router && railway variables --service webhook-router \
  --set ACUOPS_AGENT_APP_ID=<APP_ID> \
  --set ACUOPS_AGENT_INSTALLATION_ID=<INSTALLATION_ID> \
  --set ACUOPS_AGENT_PRIVATE_KEY="$(cat /path/to/pem)"

cd ~/dev/acudev && railway variables --service acudev \
  --set ACUOPS_AGENT_APP_ID=<APP_ID> \
  --set ACUOPS_AGENT_INSTALLATION_ID=<INSTALLATION_ID> \
  --set ACUOPS_AGENT_PRIVATE_KEY="$(cat /path/to/pem)"
```

(Use 1Password CLI `op read` to source the pem if you don't want it on disk.)

---

## Migration list (Task 2.3b — after Step 6)

Once the App is provisioned and credentials are in place, the following sites get migrated. **All of these can be claimed by Claude — Kevin doesn't need to touch them.**

### Workflow files (use `actions/create-github-app-token@v1`)

| Repo | File | Site | Operation |
|---|---|---|---|
| `acumatica-ci-cd` | `.github/workflows/vm-agent.yml` | L113 `GH_TOKEN` env | Dynamic prompt agent — needs cross-repo |
| `aesthetik-platform` | `.github/workflows/deploy-customization.yml` | L741 `GH_TOKEN` env | `gh workflow run` cross-repo dispatch |
| `aesthetik-platform` | same | L760 `GH_PAT_DISPATCH` env (passed downstream) | TBD — verify use site |
| `acuops` | `.github/workflows/deploy-asthetik.yml` | L518 `GH_TOKEN` env | `gh workflow run` cross-repo dispatch |
| `acuops` | same | L536 `GH_PAT_DISPATCH` env | TBD — verify use site |
| `studiob-acumatica-ci-cd-template` | `.github/workflows/deploy-customization.yml.tpl` | L293 `token:` for `peter-evans/repository-dispatch@v3` | Cross-repo `repository_dispatch` |

**Pattern:**
```yaml
- uses: actions/create-github-app-token@v1
  id: app-token
  with:
    app-id: ${{ vars.ACUOPS_AGENT_APP_ID }}
    private-key: ${{ secrets.ACUOPS_AGENT_PRIVATE_KEY }}
    owner: ${{ github.repository_owner }}
- env:
    GH_TOKEN: ${{ steps.app-token.outputs.token }}
  run: |
    gh workflow run ...
```

### Code-level dispatchers (use JWT helper to mint installation tokens)

| Repo | File | Operation |
|---|---|---|
| `webhook-router` | `src/workers/deploy-countdown.ts` | `repository_dispatch` POST |
| `acudev` | `src/index.ts` | `repository_dispatch` POST |
| `acudev` | `src/collateral/generate-collateral.ts` | `repository_dispatch` POST |
| `acuops` | `clients/asthetik/scripts/post-publish-hook.ts` | `repository_dispatch` POST |
| `acuops` | `clients/asthetik/scripts/dispatch-test-config.ts` | `repository_dispatch` POST |
| `acumatica-ci-cd` | `scripts/dispatch-test-config.ts` | `repository_dispatch` POST |

Each needs a small helper that signs a JWT with the App private key, exchanges it for an installation token via `POST /app/installations/{id}/access_tokens`, and uses that token in the `Authorization: Bearer ...` header. The token is good for 1 hour.

For Railway-hosted services (webhook-router, acudev), the helper can read App credentials from env vars set in Step 6. For one-shot scripts (acuops, acumatica-ci-cd), the script will need to read credentials from CI env vars when invoked from Actions, or from local `~/.acuops-agent` if invoked manually.

### Final cleanup (Task 2.3c)

After every site is migrated AND verified end-to-end:

```bash
gh secret delete GH_PAT_DISPATCH --repo studio-b-ai/acumatica-ci-cd
gh secret delete GH_PAT_DISPATCH --repo studio-b-ai/webhook-router
gh secret delete GH_PAT_DISPATCH --repo studio-b-ai/acudev
gh secret delete GH_PAT_DISPATCH --repo studio-b-ai/acuops
gh secret delete GH_PAT_DISPATCH --repo studio-b-ai/aesthetik-platform
# Remove from 1Password: github-pat-dispatch
```

This is the END of the GH_PAT_DISPATCH retirement arc. Closes Safety Package gate #2 fully. Combined with the dispatch counter (gate #3, separate work), invoke-agent can come back out of `if: false` for Phase 4.

---

## Verification per migration

After each Task 2.3b PR merges:
1. Trigger the relevant pipeline (deploy, dispatch, etc.)
2. Check audit log: `gh api orgs/studio-b-ai/audit-log --jq '.[] | select(.action=="workflow.dispatch") | .actor'`
3. Confirm the entry shows `acuops-agent[bot]`, NOT `kbibelhausen`

---

## Why this gates Phase 4

The 2026-04-07 dispatch loop incident burned 8 prod app pool restarts in 14 hours under Kevin's PAT identity. The post-mortem identified 3 hard gates before invoke-agent can re-enable. Two of three are addressed by other work; this is gate #2:

> **Safety Package gate #2:** GH_PAT_DISPATCH replaced with a service-account PAT (so audit log shows the agent, not Kevin)

Once `acuops-agent[bot]` is the dispatching identity, distinguishing "Kevin clicked Run Workflow" from "agent re-triggered after failure" becomes trivial. Combined with the external dispatch counter (gate #3) the agent cannot reset, the cascade pattern that caused the incident becomes impossible.

---

## Reference

- `studiob-knowledge` KB: `Auto-dispatcher PAT attribution — agents look like Kevin`
- `studiob-knowledge` KB: `Pipeline defenses layered after 2026-04-07 incident`
- Memory: `~/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/project_2026_04_07_prod_restart_followups.md`
- Memory: `~/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/project_acuops_pipeline.md`
- Workflow comment block: `acuops-deploy.yml:1885-1899` (Safety Package gates inline)
