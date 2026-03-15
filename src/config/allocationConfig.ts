/**
 * Allocation rules configuration for the auto-allocation workflow.
 *
 * Each key is an Acumatica OrderType prefix.  Rules govern how the engine
 * selects and validates lot/serial candidates for a sales order line.
 *
 * ── Business rules recap ────────────────────────────────────────────────────
 *
 *  PC (Piece-Cut):
 *    • Sort lots largest → smallest so the order can be filled with the
 *      fewest number of rolls.
 *    • Accept any combination that lands between 100 % and 120 % of the
 *      ordered quantity (fabric is cut from a roll; a little overage is fine
 *      and expected).
 *    • Must allocate a full lot at a time — no partial-roll splits.
 *    • If the only available option exceeds 120 %, cancel/skip rather than
 *      over-allocate; a buyer will need to adjust the order or source more
 *      appropriate rolls.
 *    • Never update the order quantity to match the allocated amount.
 *
 *  CO (Cut-Order):
 *    • Sort lots smallest → largest to burn through short ends first and keep
 *      larger rolls available for future piece-cut orders.
 *    • Target exactly 100 % — no overage permitted.
 *    • Must allocate a full lot at a time.
 *    • If allocation hits 100 % exactly, great; if it can't, fall back to
 *      manual.  (cancelIfOverMax is false because 100 % is also the max —
 *      there is no "over-max" scenario in practice; the engine simply won't
 *      select a lot that would push past 100 %.)
 *    • Never update the order quantity.
 *
 * ── Environment-variable overrides ─────────────────────────────────────────
 *
 *  ALLOC_PC_MIN_PCT   — override PC minAllocationPct  (float, e.g. "1.00")
 *  ALLOC_PC_MAX_PCT   — override PC maxAllocationPct  (float, e.g. "1.20")
 *  ALLOC_CO_MIN_PCT   — override CO minAllocationPct  (float, e.g. "1.00")
 *  ALLOC_CO_MAX_PCT   — override CO maxAllocationPct  (float, e.g. "1.00")
 *
 *  These are intentionally limited to threshold overrides so the core
 *  business logic (sort direction, fullLotOnly, cancelIfOverMax) remains
 *  code-controlled and change-tracked.
 */

import type { LotSortDirection } from '../types/acumatica/lotSerial.js';

// ── Rule shape ────────────────────────────────────────────────────────────────

export interface AllocationRule {
  /**
   * Master switch.  When `false` the engine skips all lines for this order
   * type and marks them `'skipped'` without attempting allocation.
   */
  enabled: boolean;

  /**
   * Order in which lots are evaluated.
   * `'desc'` = largest first (PC), `'asc'` = smallest first (CO).
   */
  sizeSortDirection: LotSortDirection;

  /**
   * Minimum acceptable total allocation as a fraction of QtyOrdered.
   * `1.00` = must allocate at least 100 % of the ordered quantity.
   */
  minAllocationPct: number;

  /**
   * Maximum acceptable total allocation as a fraction of QtyOrdered.
   * `1.20` = may allocate up to 120 % of the ordered quantity.
   * `1.00` = no overage permitted.
   */
  maxAllocationPct: number;

  /**
   * When `true` each selected lot must be consumed in its entirety —
   * the engine never takes a partial quantity from a lot.
   *
   * Both PC and CO require full-lot allocation because fabric is cut from
   * rolls and partial-roll records complicate physical inventory.
   */
  fullLotOnly: boolean;

  /**
   * When `true` and the only candidate combination that covers `minAllocationPct`
   * would exceed `maxAllocationPct`, the line is marked `'manual_required'`
   * instead of proceeding with the over-allocation.
   *
   * Set to `true` for PC (has a real 120 % ceiling).
   * Set to `false` for CO (max === min === 100 %, so the engine already
   * never selects lots that push past 100 %; this flag is a no-op in practice
   * but kept explicit for clarity and future rule changes).
   */
  cancelIfOverMax: boolean;

  /**
   * When `true` the engine writes the actual allocated quantity back to
   * `SOLine.OrderQty` before saving the allocation.
   *
   * Currently `false` for both PC and CO — the order quantity is always
   * set by the sales team; the engine only allocates lots to match it.
   */
  updateOrderQty: boolean;
}

// ── Helper: parse a float from an env var with a fallback ────────────────────

function envFloat(varName: string, fallback: number): number {
  const raw = process.env[varName];
  if (raw === undefined || raw.trim() === '') return fallback;
  const parsed = parseFloat(raw);
  if (isNaN(parsed) || parsed <= 0) {
    console.warn(
      `[allocationConfig] ${varName}="${raw}" is not a valid positive number — using default ${fallback}`,
    );
    return fallback;
  }
  return parsed;
}

// ── Rule registry ─────────────────────────────────────────────────────────────

/**
 * Allocation rules keyed by Acumatica OrderType.
 *
 * Consumed by the allocation engine at runtime:
 * ```ts
 * const rule = ALLOCATION_RULES[event.orderType];
 * if (!rule || !rule.enabled) { ... }
 * ```
 */
export const ALLOCATION_RULES: Record<string, AllocationRule> = {
  /**
   * PC — Piece-Cut orders.
   *
   * Large fabric rolls are allocated largest-first so a single roll can
   * satisfy the full order.  Up to 20 % overage is acceptable because the
   * cutter will trim to length; going above 120 % wastes material and
   * requires buyer approval, so we cancel and flag for manual review instead.
   */
  PC: {
    enabled: true,
    sizeSortDirection: 'desc', // largest lot → smallest; minimise roll count
    minAllocationPct: envFloat('ALLOC_PC_MIN_PCT', 1.0), // must cover 100 %
    maxAllocationPct: envFloat('ALLOC_PC_MAX_PCT', 1.2), // allow up to 120 %
    fullLotOnly: true, // never split a roll
    cancelIfOverMax: true, // > 120 %? escalate to manual, do not over-allocate
    updateOrderQty: false, // order qty is sales-team controlled
  },

  /**
   * CO — Cut-Order orders.
   *
   * Short-end rolls are consumed first to keep the warehouse tidy and
   * preserve larger rolls for piece-cut demand.  The target is exactly 100 %
   * — no overage — so min === max.  If the engine can't hit exactly 100 %
   * with full lots it falls back to manual; there is no meaningful
   * "cancel if over max" scenario when max === min.
   */
  CO: {
    enabled: true,
    sizeSortDirection: 'asc', // smallest lot → largest; burn short ends first
    minAllocationPct: envFloat('ALLOC_CO_MIN_PCT', 1.0), // must cover 100 %
    maxAllocationPct: envFloat('ALLOC_CO_MAX_PCT', 1.0), // exactly 100 %, no overage
    fullLotOnly: true, // never split a roll
    cancelIfOverMax: false, // max === min; over-max is structurally impossible
    updateOrderQty: false, // order qty is sales-team controlled
  },
} as const;
