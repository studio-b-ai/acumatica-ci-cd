/**
 * Types for the internal/normalized customer representation.
 *
 * AcumaticaCustomerPayload  – shape of the raw webhook body from Acumatica
 * NormalizedCustomer        – our internal customer object passed downstream
 */

import { CustomerType } from '../utils/constants.js';

// ── Raw Acumatica payload ──────────────────────────────────────────────────

/** A single Acumatica field value wrapper (the API wraps scalars in {value}) */
export interface AcuFieldValue<T = string> {
  value: T;
}

/** Sparse shape of the Acumatica Customer entity as received in webhook events */
export interface AcumaticaCustomerPayload {
  /** e.g. { value: "RETAILER" } */
  CustomerID?: AcuFieldValue;

  /** e.g. { value: "Acme Interiors LLC" } */
  CustomerName?: AcuFieldValue;

  /**
   * Primary signal for customer type classification.
   * CustomerClass is a configurable class code on the Customer record
   * (e.g. "RETAIL", "DESIGN", "WHOLESALE").
   */
  CustomerClass?: AcuFieldValue;

  /** Email address stored on the customer record */
  Email?: AcuFieldValue;

  /** Main phone number */
  Phone1?: AcuFieldValue;

  /**
   * Acumatica generic attributes bag.
   * CustomerType may appear here as a fallback when CustomerClass is absent.
   */
  Attributes?: {
    CustomerType?: AcuFieldValue;
    [key: string]: AcuFieldValue | undefined;
  };

  // Allow arbitrary additional fields from the Acumatica payload
  [key: string]: unknown;
}

// ── Normalized internal customer ───────────────────────────────────────────

/** The canonical customer object used internally and sent downstream */
export interface NormalizedCustomer {
  /** Acumatica CustomerID (e.g. "ACME001") */
  customerId: string;

  /** Display name */
  customerName: string;

  /** Classified customer type derived from CustomerClass / Attributes */
  customerType: CustomerType;

  /** Contact email, or empty string if absent */
  email: string;

  /** Primary phone number, or empty string if absent */
  phone: string;
}
