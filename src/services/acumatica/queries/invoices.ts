/**
 * Invoice queries for a given customer.
 *
 * Endpoint : GET /entity/default/24.200.001/Invoice
 * Screen   : AR301000  (DocType=INV)
 *
 * Entity name "Invoice" and screen "AR301000" are confirmed by
 * publish-manifest.json ("Invoice" → screen: "AR301000") and
 * post-publish-hook.ts DAC_TO_ENTITY mapping
 * ('PX.Objects.AR.ARInvoice' → 'Invoice').
 */

import { acumaticaGet, ACUMATICA_BASE_URL, unwrap } from '../acumaticaService.js';

// ── Types ─────────────────────────────────────────────────────────────────────

/** Raw field shape returned by the Acumatica REST API (value-wrapped scalars). */
interface RawInvoice {
  ReferenceNbr?: { value: string };
  Status?: { value: string };
  Amount?: { value: number };
  Balance?: { value: number };
  Date?: { value: string };
  CustomerID?: { value: string };
  Type?: { value: string };
}

/** Clean, unwrapped record shape returned by getCustomerInvoices(). */
export interface CustomerInvoice {
  /** Acumatica AR reference number, e.g. "INV-000456" */
  referenceNbr: string;
  /** Invoice status, e.g. "Open", "Closed", "Overdue" */
  status: string;
  /** Invoice amount (original billed amount) */
  amount: number;
  /** Outstanding balance remaining */
  balance: number;
  /** ISO 8601 date string of the invoice */
  date: string;
  /**
   * Direct deep-link URL into the Acumatica AR301000 screen.
   * Format: https://{baseUrl}/Main?ScreenId=AR301000&DocType=INV&RefNbr={refNbr}
   * DocType is always INV — filtered in the API query below.
   */
  acumaticaUrl: string;
}

// ── API call ──────────────────────────────────────────────────────────────────

/**
 * Retrieve the most recent 10 AR invoices for a given Acumatica customer.
 *
 * Filters to `Type eq 'INV'` (standard invoices only — excludes credit memos
 * 'CRM', debit adjustments 'DRM', etc.) so the AR301000 deep-link is always
 * valid. The Acumatica OData filter uses the short doc-type code ('INV'), not
 * the display label ('Invoice').
 *
 * Uses the same OData query pattern as getCustomerSalesOrders() and
 * entity-sync.py fetch_all(): $filter + $top + $orderby + $select.
 *
 * @param customerId - Acumatica CustomerID (e.g. "C000123" or "HERITAGE")
 * @returns Array of up to 10 invoices, newest first
 *
 * @example
 *   const invoices = await getCustomerInvoices('C000123');
 *   console.log(invoices[0].acumaticaUrl);
 */
export async function getCustomerInvoices(
  customerId: string,
): Promise<CustomerInvoice[]> {
  if (!customerId?.trim()) {
    throw new Error('getCustomerInvoices: customerId must be a non-empty string');
  }

  const raw = await acumaticaGet<RawInvoice[]>('Invoice', {
    // Filter to this customer + standard invoices only (Type 'INV' — excludes
    // credit memos 'CRM', debit adjustments 'DRM', etc.).
    // Acumatica OData uses the short doc-type code ('INV'), not the display
    // label ('Invoice'), so 'Type eq Invoice' would return no results.
    $filter: `CustomerID eq '${customerId.trim()}' and Type eq 'INV'`,
    // Return newest 10 invoices
    $top: '10',
    // Newest first — Date descending
    $orderby: 'Date desc',
    // Fetch only the fields we need
    $select: 'ReferenceNbr,Status,Amount,Balance,Date',
  });

  // Guard against null/non-array responses
  if (!Array.isArray(raw)) {
    throw new Error(
      `getCustomerInvoices: unexpected API response shape for customer "${customerId}"`,
    );
  }

  return raw.map((invoice): CustomerInvoice => {
    const referenceNbr = unwrap(invoice.ReferenceNbr) ?? '';

    return {
      referenceNbr,
      status: unwrap(invoice.Status) ?? '',
      amount: unwrap(invoice.Amount) ?? 0,
      balance: unwrap(invoice.Balance) ?? 0,
      date: unwrap(invoice.Date) ?? '',
      // Deep-link URL — format confirmed by publish-manifest.json (AR301000)
      // DocType=INV always valid because we filter Type eq 'INV' above
      acumaticaUrl:
        `${ACUMATICA_BASE_URL}/Main?ScreenId=AR301000` +
        `&DocType=INV` +
        `&RefNbr=${encodeURIComponent(referenceNbr)}`,
    };
  });
}
