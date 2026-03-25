/**
 * Acumatica → webhook-router: Customer webhook handler
 *
 * Acumatica fires a Business Event webhook whenever a Customer record is
 * created or updated.  The raw payload is validated, transformed into our
 * internal NormalizedCustomer shape (including customerType classification),
 * and then forwarded to downstream consumers.
 *
 * Expected raw payload shape (subset):
 * {
 *   "CustomerID":    { "value": "ACME001" },
 *   "CustomerName":  { "value": "Acme Interiors LLC" },
 *   "CustomerClass": { "value": "DESIGN" },   // primary type signal
 *   "Email":         { "value": "orders@acme.com" },
 *   "Phone1":        { "value": "212-555-0100" },
 *   "Attributes": {                           // fallback type signal
 *     "CustomerType": { "value": "Designer" }
 *   }
 * }
 */

import { transformCustomer } from '../../transforms/customer.js';
import {
  AcumaticaCustomerPayload,
  NormalizedCustomer,
} from '../../types/customer.js';

// ── Lightweight result type returned by the handler ───────────────────────

export interface CustomerHandlerResult {
  success: boolean;
  customer?: NormalizedCustomer;
  error?: string;
}

// ── Payload validation ─────────────────────────────────────────────────────

/**
 * Minimal guard: confirms the payload is a non-null object so that
 * transformCustomer can safely access optional nested fields.
 *
 * Acumatica always includes CustomerID in Customer events; if it is missing
 * we treat the payload as malformed.
 */
function isValidCustomerPayload(
  body: unknown,
): body is AcumaticaCustomerPayload {
  if (typeof body !== 'object' || body === null) return false;
  const candidate = body as Record<string, unknown>;
  // CustomerID is the minimum required field for a meaningful customer event
  return (
    'CustomerID' in candidate &&
    typeof (candidate.CustomerID as Record<string, unknown>)?.value === 'string'
  );
}

// ── Handler ───────────────────────────────────────────────────────────────

/**
 * Processes a raw Acumatica Customer webhook payload.
 *
 * The raw body is passed through as-is from the HTTP request; CustomerClass
 * and Attributes.CustomerType are both forwarded to transformCustomer so the
 * type classification logic has access to both fields.
 *
 * @param rawBody - The parsed JSON body of the incoming Acumatica webhook.
 * @returns A CustomerHandlerResult indicating success/failure and, on success,
 *          the normalized customer object.
 */
export function handleCustomerWebhook(
  rawBody: unknown,
): CustomerHandlerResult {
  // ── 1. Validate ──────────────────────────────────────────────────────────
  if (!isValidCustomerPayload(rawBody)) {
    return {
      success: false,
      error: 'Invalid customer payload: missing or malformed CustomerID',
    };
  }

  // ── 2. Transform ─────────────────────────────────────────────────────────
  //
  // transformCustomer receives the full raw payload, which includes:
  //   • CustomerClass – preferred source for type classification
  //   • Attributes.CustomerType – fallback source
  // Both are read directly from rawBody without re-mapping so no field is
  // inadvertently dropped before the transform sees it.
  const customer = transformCustomer(rawBody);

  // ── 3. Return normalized result ──────────────────────────────────────────
  return {
    success: true,
    customer,
  };
}
