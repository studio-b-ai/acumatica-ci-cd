/**
 * Customer data transform
 *
 * Converts a raw Acumatica Customer webhook payload into our internal
 * NormalizedCustomer shape.
 *
 * Classification logic (mapCustomerType):
 *   Acumatica exposes the customer's category via two locations:
 *     1. CustomerClass.value  – the preferred source (a configurable class code)
 *     2. Attributes.CustomerType.value – a fallback generic attribute
 *   We inspect whichever is present (preferring CustomerClass) and map it to
 *   one of the known CUSTOMER_TYPES values using keyword matching.
 */

import { CUSTOMER_TYPES, CustomerType } from '../utils/constants.js';
import {
  AcumaticaCustomerPayload,
  NormalizedCustomer,
} from '../types/customer.js';

// ── Type classification helper ─────────────────────────────────────────────

/**
 * Maps a raw Acumatica customer class / type string to one of our internal
 * CustomerType constants.
 *
 * Matching is case-insensitive and keyword-based so it is resilient to minor
 * variations in how Acumatica class codes are named (e.g. "RETAIL",
 * "RETAILERS", "RETL" would all need the substring "RETAIL" — only the first
 * two would match; the abbreviated form would fall through to OTHER, which is
 * the safe default).
 *
 * @param rawType - The raw string from CustomerClass.value or
 *                  Attributes.CustomerType.value.  May be undefined if the
 *                  field is absent on the payload.
 * @returns One of the CUSTOMER_TYPES values.
 */
export function mapCustomerType(rawType?: string): CustomerType {
  if (!rawType) return CUSTOMER_TYPES.OTHER;

  const normalized = rawType.toUpperCase().trim();

  if (normalized.includes('RETAIL')) return CUSTOMER_TYPES.RETAILER;
  if (normalized.includes('FINAL') || normalized.includes('CLIENT'))
    return CUSTOMER_TYPES.FINAL_CLIENT;
  if (normalized.includes('DESIGN')) return CUSTOMER_TYPES.DESIGNER;
  if (normalized.includes('WHOLESALE')) return CUSTOMER_TYPES.WHOLESALER;

  return CUSTOMER_TYPES.OTHER;
}

// ── Main transform ─────────────────────────────────────────────────────────

/**
 * Transforms a raw Acumatica Customer payload into a NormalizedCustomer.
 *
 * CustomerClass is preferred for type classification; Attributes.CustomerType
 * is used as a fallback when CustomerClass is absent or empty.
 *
 * @param raw - The raw payload object from the Acumatica webhook body.
 * @returns A fully-populated NormalizedCustomer object.
 */
export function transformCustomer(
  raw: AcumaticaCustomerPayload,
): NormalizedCustomer {
  // Prefer CustomerClass; fall back to the generic Attributes bag
  const rawTypeValue =
    raw.CustomerClass?.value || raw.Attributes?.CustomerType?.value;

  const customerType = mapCustomerType(rawTypeValue);

  return {
    customerId: raw.CustomerID?.value ?? '',
    customerName: raw.CustomerName?.value ?? '',
    customerType,
    email: raw.Email?.value ?? '',
    phone: raw.Phone1?.value ?? '',
  };
}
