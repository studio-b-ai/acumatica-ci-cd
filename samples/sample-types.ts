/**
 * Shared type definitions for the Heritage Fabrics samples request form.
 *
 * These types are consumed by:
 *  - The samples request form front-end (field names / validation shapes)
 *  - The MCP server tool handler (acumatica_create_sales_order)
 *  - Any webhook or CI/CD step that processes a samples submission
 *
 * The `comments` field (added in this enhancement) carries free-text customer
 * input from the form.  It is optional so existing integrations that do not
 * yet pass comments remain fully compatible.  When present the server maps it
 * to the `Note` field on the Acumatica Sales Order so warehouse staff see it
 * immediately on SO301000 without opening any custom panel.
 */

// ─── Line item ───────────────────────────────────────────────────────────────

/**
 * A single fabric/product line on a samples request.
 */
export interface SampleLineItem {
  /** Acumatica inventory ID (e.g. 'LINEN-NAT-60'). */
  inventory_id: string;

  /** Quantity requested (whole bolts or yards depending on UOM). */
  quantity: number;

  /**
   * Acumatica warehouse ID to fulfil from.
   * Optional — omit to let Acumatica apply the customer/item default.
   */
  warehouse_id?: string;
}

// ─── Samples request form payload ────────────────────────────────────────────

/**
 * The full payload submitted when a customer completes the samples request form.
 *
 * All fields map 1-to-1 to the `acumatica_create_sales_order` tool arguments
 * so that the webhook handler can forward the object directly with no
 * field-name translation.
 */
export interface SamplesRequestPayload {
  /** Acumatica customer account ID (e.g. 'C000123'). Required. */
  customer_id: string;

  /**
   * Sales order type.  Defaults to `'SO'` when omitted.
   * Override to `'RM'` for return-merchandise orders, etc.
   */
  order_type?: string;

  /**
   * Short description / external reference written to the SO Description
   * header field (visible in the order selector list on SO301000).
   * Distinct from `comments` — both can coexist on the same order.
   */
  description?: string;

  /** One or more fabric/product line items. At least one is required. */
  line_items: SampleLineItem[];

  /**
   * Optional free-text customer comment from the samples request form.
   *
   * When non-empty this value is written to the **Note** field on the
   * resulting Acumatica Sales Order (the 📎 Notes panel on SO301000),
   * prefixed with `"Customer comment from samples form: "` so warehouse
   * staff can immediately identify its origin.
   *
   * Whitespace-only strings are treated as absent (no Note is written).
   *
   * Added in enhancement #43375885829 — add a comment field to the samples
   * request form.
   */
  comments?: string;
}

// ─── Submission result ───────────────────────────────────────────────────────

/**
 * Shape returned to the form front-end after a successful submission.
 * The actual Acumatica record data is flattened into the `order` field.
 */
export interface SamplesSubmissionResult {
  /** `true` when the Sales Order was created without error. */
  success: boolean;

  /** The Acumatica Sales Order number (e.g. 'SO-000123'). */
  order_nbr: string;

  /** ISO-8601 UTC timestamp of when the order was created. */
  created_at: string;

  /**
   * Echo of the comments that were written to the Note field.
   * `undefined` when no comments were provided.
   */
  comments_saved?: string;
}

// ─── Validation helpers ──────────────────────────────────────────────────────

/**
 * Validates a `SamplesRequestPayload` and returns a list of human-readable
 * error messages.  An empty array means the payload is valid.
 *
 * This is a pure TypeScript function — safe to call in any environment
 * (browser, Node, Deno) without network access.
 *
 * @example
 * ```ts
 * const errors = validateSamplesPayload(formData);
 * if (errors.length) { showValidationErrors(errors); return; }
 * await submitSamplesRequest(formData);
 * ```
 */
export function validateSamplesPayload(payload: SamplesRequestPayload): string[] {
  const errors: string[] = [];

  if (!payload.customer_id?.trim()) {
    errors.push('customer_id is required');
  }

  if (!Array.isArray(payload.line_items) || payload.line_items.length === 0) {
    errors.push('At least one line_item is required');
  } else {
    payload.line_items.forEach((item, idx) => {
      if (!item.inventory_id?.trim()) {
        errors.push(`line_items[${idx}].inventory_id is required`);
      }
      if (typeof item.quantity !== 'number' || item.quantity <= 0) {
        errors.push(`line_items[${idx}].quantity must be a positive number`);
      }
    });
  }

  // comments: no validation rule — any string (or absence) is acceptable.
  // Whitespace-only is silently treated as absent by the server.

  return errors;
}

/**
 * Returns `true` when a `SamplesRequestPayload` passes all validation rules.
 * Convenience wrapper around {@link validateSamplesPayload}.
 */
export function isSamplesPayloadValid(payload: SamplesRequestPayload): boolean {
  return validateSamplesPayload(payload).length === 0;
}
