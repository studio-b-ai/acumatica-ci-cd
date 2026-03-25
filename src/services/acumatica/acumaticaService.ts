/**
 * Acumatica service façade.
 *
 * Re-exports the shared client and exposes convenience helpers consumed
 * by higher-level query modules (salesOrders.ts, invoices.ts).
 *
 * Keeps query modules thin: they call acumaticaGet() directly rather than
 * instantiating their own HTTP layers, matching server.py's acumatica_get()
 * pattern where a single shared session handles all requests.
 *
 * ── Testable seam ────────────────────────────────────────────────────────────
 * Query modules import `acumaticaGet` from this file (not from acumaticaClient
 * directly). Tests can swap the implementation at runtime by writing to the
 * exported `_acumaticaGetImpl` slot — an ESM-safe alternative to require()-
 * based monkey-patching.  Production code always reads through the slot, so
 * the swap is transparent to salesOrders.ts and invoices.ts.
 *
 * Usage in tests (see customerLookup.test.ts):
 *   import { _acumaticaGetImpl } from '../../acumaticaService.js';
 *   const original = _acumaticaGetImpl.fn;
 *   _acumaticaGetImpl.fn = async (path, params) => stubbedData;
 *   // ... run test ...
 *   _acumaticaGetImpl.fn = original;   // restore
 */

import { acumaticaGet as _realGet } from './acumaticaClient.js';

export {
  ensureAuthenticated,
  logout,
  ACUMATICA_BASE_URL,
  API_BASE,
} from './acumaticaClient.js';

// ── Testable seam ─────────────────────────────────────────────────────────────

/**
 * Mutable slot holding the active acumaticaGet implementation.
 * In production this always holds the real network implementation.
 * Tests may temporarily swap `.fn` to a stub; they MUST restore it afterwards.
 *
 * Using an object wrapper (rather than a plain `let` export) is required for
 * ESM: named exports are live bindings but are read-only from outside the
 * module, whereas a mutable property on an exported object can be written by
 * any importer — giving tests a clean injection point.
 */
export const _acumaticaGetImpl: {
  fn: <T = unknown>(entityPath: string, params?: Record<string, string>) => Promise<T>;
} = {
  fn: _realGet,
};

/**
 * GET from the Acumatica entity API.
 * Delegates to `_acumaticaGetImpl.fn` so the implementation can be swapped
 * out by tests without a network connection.
 *
 * @param entityPath - Relative path under API_BASE (e.g. "SalesOrder")
 * @param params     - OData query string parameters
 */
export function acumaticaGet<T = unknown>(
  entityPath: string,
  params?: Record<string, string>,
): Promise<T> {
  return _acumaticaGetImpl.fn<T>(entityPath, params);
}

// ── Helpers ───────────────────────────────────────────────────────────────────

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
