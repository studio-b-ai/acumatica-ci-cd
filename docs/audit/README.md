# Audit Documentation

This directory contains configuration audit records for the Heritage Fabrics / Studio B
Acumatica instance. Audits are created before any configuration change is applied so
that a precise rollback path exists.

## Index

| File | Subject | Status |
|---|---|---|
| [duties-landed-cost-code-audit.md](./duties-landed-cost-code-audit.md) | DUTIES landed cost code — why it is absent from PO Container IGCM3098 | 🔲 Pending field inspection |

## How to Use These Docs

1. **Before changing anything** — open the relevant audit file and fill in the
   "Observed Value" column from the live Acumatica UI.
2. **Take screenshots** and place them in `docs/audit/screenshots/`.
3. **Commit** the filled-in audit file and screenshots so the pre-change state is
   permanently recorded in git history.
4. Apply the fix, then update the "Findings" and "Sign-Off" sections.
