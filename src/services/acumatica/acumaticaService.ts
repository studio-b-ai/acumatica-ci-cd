/**
 * Acumatica service façade.
 *
 * Re-exports the shared client and exposes convenience helpers consumed
 * by higher-level query modules (salesOrders.ts, invoices.ts).
 *
 * Keeps query modules thin: they call acumaticaGet() directly rather than
 * instantiating their own HTTP layers, matching server.py's acumatica_get()
 * pattern where a single shared session handles all requests.
 */

export {
  acumaticaGet,
  ensureAuthenticated,
  logout,
  ACUMATICA_BASE_URL,
  API_BASE,
} from './acumaticaClient.js';

/**
 * Unwrap an Acumatica `{value: T}` field envelope.
 * Acumatica REST API wraps every scalar in `{ "value": <actual> }`.
 * Returns the raw value, or `undefined` if absent.
 *
 * @example
 *   unwrap(record.OrderNbr)  // "SO-000123"
 */
export function unwrap<T>(field: { value: T } | T | undefined): T | undefined {
  if (field === undefined || field === null) return undefined;
  if (typeof field === 'object' && field !== null && 'value' in (field as object)) {
    return (field as { value: T }).value;
  }
  return field as T;
}
