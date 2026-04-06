# Phase 3 E2E Dry Run Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Wire secrets delivery to the deploy agent so the remote trigger can execute the full deploy lifecycle.

**Architecture:** Expand the GHA deploy-context artifact to include secrets, add a bootstrap step to the agent prompt that exports them as env vars at runtime.

**Tech Stack:** GitHub Actions, jq, bash

**Design doc:** `docs/plans/2026-04-06-phase3-dry-run-design.md`

---

### Task 1: Add secrets to deploy-context.json in workflow

**Files:**
- Modify: `.github/workflows/acuops-deploy.yml` (invoke-agent job, "Save deploy context" step)

**Step 1: Edit the heredoc**

The current heredoc at the "Save deploy context" step looks like:

```yaml
      - name: Save deploy context
        run: |
          cat > deploy-context.json <<'CONTEXT_EOF'
          {
            "package_name": "${{ needs.build.outputs.package_name }}",
            ...
          }
          CONTEXT_EOF
```

The problem is `<<'CONTEXT_EOF'` (quoted) prevents variable expansion. Change to unquoted `<<CONTEXT_EOF` and add the secrets block. Replace the entire step with:

```yaml
      - name: Save deploy context
        run: |
          cat > deploy-context.json <<CONTEXT_EOF
          {
            "package_name": "${{ needs.build.outputs.package_name }}",
            "package_path": "${{ needs.build.outputs.package_path }}",
            "project_name": "${{ needs.build.outputs.project_name }}",
            "also_publish": "${{ needs.build.outputs.also_publish }}",
            "isv_prefix": "${{ needs.build.outputs.isv_prefix }}",
            "known_projects": "${{ needs.build.outputs.known_projects }}",
            "commit_sha": "${{ github.sha }}",
            "commit_message": "${{ github.event.head_commit.message }}",
            "run_id": "${{ github.run_id }}",
            "ref": "${{ github.ref }}",
            "environment": "${{ github.ref == 'refs/heads/main' && 'production' || 'staging' }}",
            "secrets": {
              "ACUMATICA_SANDBOX_URL": "${{ secrets.ACUMATICA_SANDBOX_URL }}",
              "ACUMATICA_SANDBOX_USERNAME": "${{ secrets.ACUMATICA_SANDBOX_USERNAME }}",
              "ACUMATICA_SANDBOX_PASSWORD": "${{ secrets.ACUMATICA_SANDBOX_PASSWORD }}",
              "ACUMATICA_SANDBOX_TENANT": "${{ secrets.ACUMATICA_SANDBOX_TENANT }}",
              "ACUMATICA_PROD_URL": "${{ secrets.ACUMATICA_PROD_URL }}",
              "ACUMATICA_PROD_USERNAME": "${{ secrets.ACUMATICA_PROD_USERNAME }}",
              "ACUMATICA_PROD_PASSWORD": "${{ secrets.ACUMATICA_PROD_PASSWORD }}",
              "ACUMATICA_PROD_TENANT": "${{ secrets.ACUMATICA_PROD_TENANT }}",
              "SLACK_BOT_TOKEN": "${{ secrets.SLACK_BOT_TOKEN }}",
              "GH_TOKEN": "${{ secrets.GH_PAT_DISPATCH }}",
              "QDRANT_URL": "${{ secrets.QDRANT_URL }}",
              "VOYAGE_API_KEY": "${{ secrets.VOYAGE_API_KEY }}",
              "ACUDEV_URL": "${{ secrets.ACUDEV_URL }}",
              "ACUDEV_API_KEY": "${{ secrets.ACUDEV_API_KEY }}"
            }
          }
          CONTEXT_EOF
```

Note: `GH_TOKEN` maps to `GH_PAT_DISPATCH` (the PAT with repo+actions scope).

**Step 2: Verify YAML syntax**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/acuops-deploy.yml')); print('OK')"`
Expected: `OK`

**Step 3: Commit**

```
git add .github/workflows/acuops-deploy.yml
git commit -m "ci: add secrets to deploy-context artifact for agent bootstrap

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Add Step 0 Bootstrap to agent prompt

**Files:**
- Modify: `agents/deploy-agent.md`

**Step 1: Update the Environment Variables section**

Replace the current text:

```
## Environment Variables

These are available in your environment:
```

With:

```
## Environment Variables

These are loaded from `deploy-context.json` in Step 0 (Bootstrap). The GH Actions workflow injects all secrets into the artifact before uploading.
```

**Step 2: Add Step 0 before Step 1**

Insert the following section before "## Step 1: Get Deploy Context":

```markdown
## Step 0: Bootstrap

Download the deploy context artifact and export secrets as environment variables. This must run before any other step.

### Get the latest run ID

```bash
RUN_ID=$(gh run list --repo studio-b-ai/acumatica-ci-cd \
  --workflow=acuops-deploy.yml --branch=main \
  --status=completed --limit=1 \
  --json databaseId -q '.[0].databaseId')

echo "Run ID: $RUN_ID"
```

### Download deploy context

```bash
gh run download "$RUN_ID" --name deploy-context --dir ./context
```

### Export secrets as environment variables

```bash
eval $(jq -r '.secrets | to_entries[] | "export \(.key)=\(.value)"' ./context/deploy-context.json)
```

### Verify bootstrap

```bash
# Sanity check — these must all be non-empty
for var in ACUMATICA_PROD_URL ACUMATICA_SANDBOX_URL SLACK_BOT_TOKEN GH_TOKEN QDRANT_URL; do
  if [ -z "${!var}" ]; then
    echo "FATAL: $var is empty after bootstrap. Deploy context may be missing secrets."
    exit 1
  fi
done
echo "Bootstrap complete — all secrets loaded."
```
```

**Step 3: Update Step 1 to remove duplicate artifact download**

The current Step 1 downloads both `deploy-context` and `package-artifacts`. Since Step 0 already downloads `deploy-context`, change Step 1 to only download `package-artifacts` and read the already-downloaded context:

Replace the Step 1 download block:

```bash
# Download deploy context and package artifacts
gh run download "$RUN_ID" --name deploy-context --dir ./context
gh run download "$RUN_ID" --name package-artifacts --dir ./artifacts
```

With:

```bash
# Deploy context already downloaded in Step 0
# Download package artifacts
gh run download "$RUN_ID" --name package-artifacts --dir ./artifacts
```

And remove the duplicate `RUN_ID` assignment from Step 1 (it's already set in Step 0).

**Step 4: Commit**

```
git add agents/deploy-agent.md
git commit -m "feat: add bootstrap step to deploy agent — loads secrets from artifact

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Verify and push

**Step 1: Verify YAML syntax**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/acuops-deploy.yml')); print('OK')"`
Expected: `OK`

**Step 2: Verify agent prompt has Step 0 before Step 1**

Run: `grep -n "^## Step" agents/deploy-agent.md`
Expected:
```
Step 0: Bootstrap
Step 1: Get Deploy Context
Step 2: Pre-deploy KB Check
...
```

**Step 3: Push and create PR**

```
git push origin claude/quirky-perlman
gh pr create --title "ci: Phase 3 dry run — secrets via deploy-context" --body "..."
```
