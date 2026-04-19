# acumatica-ci-cd — ARCHIVED 2026-04-19

This repository has been **split** into two:

- **Generic CI/CD engine** → https://github.com/studio-b-ai/acuops-pipeline
- **Ästhetik / Heritage Fabrics instance** → https://github.com/studio-b-ai/client-asthetik

Heritage Fabrics deploys now flow: `push to client-asthetik/main` → the reusable
workflow `studio-b-ai/acuops-pipeline/.github/workflows/acuops-build.yml@v1`.

Full migration plan: https://github.com/studio-b-ai/acuops-pipeline/blob/main/docs/plans/2026-04-18-acumatica-ci-cd-split.md

This repo is preserved read-only for history. Do not open PRs here.
