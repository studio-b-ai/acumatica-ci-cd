# DUTIES Landed Cost Code – Configuration Audit

**Acumatica Instance:** https://heritagefabrics.acumatica.com  
**Screen:** Landed Cost Codes (`PO202000`)  
**Record:** `DUTIES`  
**Audit Date:** _[ to be filled in by engineer ]_  
**Audited By:** _[ to be filled in by engineer ]_  
**Related PO / Container:** IGCM3098

---

## Purpose

Document the current configuration of the `DUTIES` landed cost code to determine
why it does **not** appear on the Landed Cost tab of PO Container **IGCM3098**.

The primary hypothesis is that the **Applicable To** (Apply To) field or another
restriction field is scoped in a way that excludes Purchase Order / Container
document types.

---

## Field-by-Field Audit Checklist

Fill in each value exactly as it appears in the Acumatica UI.

| Field | Observed Value | Notes |
|---|---|---|
| Landed Cost Code ID | | |
| Description | | |
| Allocation Method | | One of: By Quantity · By Cost · By Weight · By Volume · None |
| **Applicable To / Apply To** | | **Primary suspect** — must include "Purchase Receipt" for container use |
| Vendor | | Blank = any vendor; a specific vendor restricts availability |
| Tax Category | | |
| Posting Class | | If present |
| Account / Sub | | Debit account the cost posts to |
| Active checkbox | | Must be checked |
| Any other restriction fields | | Document all |

---

## Screenshot Checklist (Rollback Documentation)

Capture and attach the following screenshots before making any changes:

- [ ] Full `DUTIES` record — General tab
- [ ] Full `DUTIES` record — GL Accounts tab (if separate tab exists)
- [ ] Landed Cost tab on PO Container IGCM3098 **before** any fix (show that DUTIES is absent)
- [ ] Landed Cost Codes list view filtered to show all active codes and their "Apply To" values

> **Storage:** Save screenshots to `docs/audit/screenshots/` and commit them alongside this file.

---

## Findings

_Complete this section after the UI inspection._

### Root Cause Hypothesis Status

| Hypothesis | Confirmed / Refuted / Unknown |
|---|---|
| "Applicable To" is set to AP Bill only (not Purchase Receipt) | |
| Record is inactive | |
| Vendor restriction excludes the vendor on IGCM3098 | |
| Allocation Method incompatible with container document type | |
| Other | |

### Observed Root Cause

> _Describe exactly what setting is preventing DUTIES from appearing on IGCM3098._

---

## Recommended Fix

> _Record the exact field change needed (field name → old value → new value)._

| Field | Current Value | Proposed Value |
|---|---|---|
| | | |

---

## Rollback Plan

If the change causes unintended side-effects:

1. Re-open `DUTIES` on screen `PO202000`.
2. Revert the changed field(s) to the values documented in the table above.
3. Save and confirm the Landed Cost tab on IGCM3098 returns to its pre-change state.

---

## Sign-Off

| Role | Name | Date |
|---|---|---|
| Engineer who audited | | |
| Engineer who applied fix | | |
| QA / reviewer | | |
