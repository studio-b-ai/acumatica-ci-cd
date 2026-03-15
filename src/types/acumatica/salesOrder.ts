/**
 * Acumatica Sales Order types for the auto-allocation workflow.
 *
 * These interfaces model the subset of fields the allocation engine reads
 * from / writes back to the Acumatica REST API.  They intentionally mirror
 * the Acumatica field-naming convention (PascalCase) so that API responses
 * can be typed with minimal transformation.
 */

// ── Individual order line ────────────────────────────────────────────────────

/**
 * A single detail line on an Acumatica Sales Order (SOLine).
 *
 * `QtyUnallocated` is a client-side computed field — it is NOT returned by the
 * Acumatica API and must be calculated as `QtyOrdered - QtyAllocated` after
 * the response is received.
 */
export interface SalesOrderLine {
  /** "SO", "TR", etc. — the order type prefix */
  OrderType: string;

  /** Human-readable order number, e.g. "000123" */
  OrderNbr: string;

  /** 1-based line number within the order */
  LineNbr: number;

  /** Acumatica inventory item ID, e.g. "FABRICROLL-7OZ-NAVY" */
  InventoryID: string;

  /** Total quantity the customer has ordered (in base UOM) */
  QtyOrdered: number;

  /** Quantity already allocated to a specific lot / location */
  QtyAllocated: number;

  /**
   * Quantity still needing allocation.
   * Computed: `QtyOrdered - QtyAllocated`.
   * Populated by the allocation engine after fetching the order — never
   * serialised back to Acumatica.
   */
  QtyUnallocated: number;
}

// ── Allocation result per line ───────────────────────────────────────────────

/**
 * The outcome of running the allocation algorithm against one SalesOrderLine.
 */
export interface AllocationResult {
  /** Matches {@link SalesOrderLine.LineNbr} */
  lineNbr: number;

  /**
   * Lot/serial numbers selected for this line, in the order they will be
   * applied.  Empty array when `status` is `'skipped'`.
   */
  lotSerialNumbers: Array<{
    /** The lot or serial number identifier in Acumatica */
    lotSerialNbr: string;
    /** Quantity to allocate from this lot */
    qty: number;
  }>;

  /** Sum of all `qty` values in {@link lotSerialNumbers} */
  totalAllocated: number;

  /**
   * Allocation decision:
   * - `success`          — lots were found and the result is within the
   *                        configured min/max percentage band.
   * - `manual_required`  — no valid lot combination could satisfy the rules;
   *                        a warehouse user must allocate manually.
   * - `skipped`          — line was intentionally excluded (e.g. non-stock
   *                        item, already fully allocated, or allocation
   *                        disabled for this order type).
   */
  status: 'success' | 'manual_required' | 'skipped';

  /**
   * Human-readable explanation — always set when `status` is
   * `'manual_required'` or `'skipped'`, optional for `'success'`.
   */
  reason?: string;
}

// ── Inbound webhook / trigger event ─────────────────────────────────────────

/**
 * The event payload that triggers the allocation workflow.
 *
 * Emitted by the Acumatica push-notification or by an internal webhook after
 * a sales order transitions to an allocatable state.
 */
export interface SalesOrderEvent {
  /** "SO", "TR", etc. */
  orderType: string;

  /** Acumatica order number, e.g. "000123" */
  orderNbr: string;

  /**
   * What action caused this event:
   * - `entry`        — order was first saved (initial creation).
   * - `unhold`       — order was taken off hold and is now open.
   * - `unbackorder`  — a back-ordered line is now available for allocation.
   */
  trigger: 'entry' | 'unhold' | 'unbackorder';
}
