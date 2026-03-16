/**
 * Auto-allocation engine for Heritage Fabrics / Studio B.
 *
 * Given a sales order line and the available lot/serial candidates for its
 * inventory item, this module selects the best set of lots that satisfies the
 * allocation rules configured in {@link ALLOCATION_RULES}.
 *
 * ── Responsibilities ────────────────────────────────────────────────────────
 *  1. Validate that a rule exists and is enabled for the given order type.
 *  2. Filter out lots that are fully unavailable (QtyAvailable === 0).
 *  3. Sort the candidate lots according to the rule's `sizeSortDirection`
 *     (largest-first for PC, smallest-first for CO), using `CreationDate`
 *     (oldest first / FIFO) as a tiebreaker.
 *  4. Greedily accumulate full lots until:
 *       a. The accumulated quantity lands within [minAllocationPct, maxAllocationPct]
 *          of the ordered quantity — success.
 *       b. The next lot would push the total over the maximum — stop and evaluate
 *          whether to mark the line as `manual_required` (PC) or simply leave
 *          the partial accumulation (CO already stops at exactly 100 %).
 *       c. No lots remain and the minimum has not been reached — `manual_required`.
 *  5. Return a typed {@link AllocationResult} for every line.
 *
 * ── fullLotOnly ──────────────────────────────────────────────────────────────
 *  Both PC and CO require full-lot allocation.  The engine therefore never
 *  splits a lot — it either takes the entire `QtyAvailable` of a lot or
 *  skips it entirely.  A lot is skipped when adding it would exceed
 *  `maxAllocationPct * QtyOrdered`.
 *
 * ── Floating-point tolerance ─────────────────────────────────────────────────
 *  Fabric quantities are measured in yards and stored as decimals.  To avoid
 *  IEEE-754 rounding surprises when comparing accumulated quantities against
 *  percentage thresholds, all comparisons use a small epsilon (1e-9).
 */

import type { AllocationRule } from '../config/allocationConfig.js';
import { ALLOCATION_RULES } from '../config/allocationConfig.js';
import type { LotSerialRecord } from '../types/acumatica/lotSerial.js';
import type {
  AllocationResult,
  SalesOrderLine,
  SalesOrderEvent,
} from '../types/acumatica/salesOrder.js';

// ── Constants ─────────────────────────────────────────────────────────────────

/**
 * Floating-point epsilon used in quantity comparisons.
 * 1e-9 yards (sub-nanometre) is well below any physically meaningful tolerance.
 */
const EPSILON = 1e-9;

// ── Internal helpers ──────────────────────────────────────────────────────────

/**
 * Returns `true` when `value >= threshold - EPSILON`.
 * Avoids false negatives from accumulated floating-point rounding errors.
 */
function geq(value: number, threshold: number): boolean {
  return value >= threshold - EPSILON;
}

/**
 * Returns `true` when `value <= threshold + EPSILON`.
 * Avoids false positives when a tiny rounding error nudges a value just over
 * a maximum threshold.
 */
function leq(value: number, threshold: number): boolean {
  return value <= threshold + EPSILON;
}

/**
 * Sort comparator that orders lots by `Size` in the requested direction,
 * using `CreationDate` (oldest-first / FIFO) as a tiebreaker.
 *
 * Lots with `Size === 0` (missing or unparseable attribute) are always placed
 * at the end of the list regardless of direction, so the engine considers
 * properly-sized rolls first.
 *
 * @param a - First lot candidate
 * @param b - Second lot candidate
 * @param direction - `'asc'` for smallest-first, `'desc'` for largest-first
 */
function compareLots(
  a: LotSerialRecord,
  b: LotSerialRecord,
  direction: 'asc' | 'desc',
): number {
  // Push zero-size lots to the end regardless of direction
  if (a.Size === 0 && b.Size !== 0) return 1;
  if (b.Size === 0 && a.Size !== 0) return -1;

  // Primary: sort by Size in the requested direction
  const sizeDiff = direction === 'desc' ? b.Size - a.Size : a.Size - b.Size;
  if (sizeDiff !== 0) return sizeDiff;

  // Tiebreaker: oldest lot first (FIFO)
  return a.CreationDate.getTime() - b.CreationDate.getTime();
}

/**
 * Core greedy allocation algorithm.
 *
 * Iterates through the sorted lot candidates, accumulating full lots until the
 * total falls within the [min, max] percentage band defined by `rule`.
 *
 * @param line    - The sales order line being allocated
 * @param lots    - Lot candidates, pre-sorted in preference order
 * @param rule    - Allocation rule for this order type
 * @returns       - An {@link AllocationResult} describing the outcome
 */
function greedyAllocate(
  line: SalesOrderLine,
  lots: LotSerialRecord[],
  rule: AllocationRule,
): AllocationResult {
  const minQty = rule.minAllocationPct * line.QtyOrdered;
  const maxQty = rule.maxAllocationPct * line.QtyOrdered;

  const selected: Array<{ lotSerialNbr: string; qty: number }> = [];
  let accumulated = 0;

  for (const lot of lots) {
    // If we've already reached the minimum, stop adding more lots.
    // (For CO, min === max === 100 %, so this exits as soon as we hit 100 %.)
    if (geq(accumulated, minQty)) break;

    const lotQty = lot.QtyAvailable;

    // Would adding this lot exceed the maximum?
    if (!leq(accumulated + lotQty, maxQty)) {
      // fullLotOnly: we cannot take a partial quantity.
      // Skip this lot and continue looking for a smaller one that fits.
      continue;
    }

    // Accept this lot in full.
    selected.push({ lotSerialNbr: lot.LotSerialNbr, qty: lotQty });
    accumulated += lotQty;
  }

  const totalAllocated = accumulated;

  // ── Evaluate outcome ──────────────────────────────────────────────────────

  if (geq(totalAllocated, minQty) && leq(totalAllocated, maxQty)) {
    // Happy path: within the acceptable band.
    return {
      lineNbr: line.LineNbr,
      lotSerialNumbers: selected,
      totalAllocated,
      status: 'success',
    };
  }

  // Below minimum — could not fill the order.
  if (rule.cancelIfOverMax) {
    // PC: there may be lots available but adding any one of them would exceed
    // the maximum.  Signal for manual review.
    return {
      lineNbr: line.LineNbr,
      lotSerialNumbers: [],
      totalAllocated: 0,
      status: 'manual_required',
      reason:
        `Unable to allocate line ${line.LineNbr}: accumulated ${totalAllocated.toFixed(4)} ` +
        `of required min ${minQty.toFixed(4)} without exceeding max ${maxQty.toFixed(4)}. ` +
        `Manual review required.`,
    };
  }

  // CO (cancelIfOverMax === false): could not reach exactly 100 %.
  return {
    lineNbr: line.LineNbr,
    lotSerialNumbers: [],
    totalAllocated: 0,
    status: 'manual_required',
    reason:
      `Unable to allocate line ${line.LineNbr}: no full-lot combination reaches ` +
      `exactly ${(rule.minAllocationPct * 100).toFixed(0)} % of ordered qty ` +
      `${line.QtyOrdered}. Manual allocation required.`,
  };
}

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Allocate lots for a single sales order line.
 *
 * This is the primary entry point for the allocation engine when processing
 * individual lines (e.g. streaming through order lines one at a time).
 *
 * @param line       - The sales order line to allocate
 * @param candidates - All available lots for `line.InventoryID`, unsorted
 * @returns          - {@link AllocationResult} with the selected lots and status
 *
 * @example
 * ```ts
 * const result = allocateLine(line, availableLots);
 * if (result.status === 'success') {
 *   await writeAllocationsToAcumatica(result.lotSerialNumbers);
 * }
 * ```
 */
export function allocateLine(
  line: SalesOrderLine,
  candidates: LotSerialRecord[],
): AllocationResult {
  // ── 1. Look up the allocation rule ───────────────────────────────────────
  const rule: AllocationRule | undefined = ALLOCATION_RULES[line.OrderType];

  if (rule === undefined) {
    return {
      lineNbr: line.LineNbr,
      lotSerialNumbers: [],
      totalAllocated: 0,
      status: 'skipped',
      reason: `No allocation rule configured for order type "${line.OrderType}".`,
    };
  }

  if (!rule.enabled) {
    return {
      lineNbr: line.LineNbr,
      lotSerialNumbers: [],
      totalAllocated: 0,
      status: 'skipped',
      reason: `Allocation is disabled for order type "${line.OrderType}".`,
    };
  }

  // ── 2. Guard: nothing to allocate ────────────────────────────────────────
  if (line.QtyOrdered <= 0) {
    return {
      lineNbr: line.LineNbr,
      lotSerialNumbers: [],
      totalAllocated: 0,
      status: 'skipped',
      reason: `Line ${line.LineNbr} has QtyOrdered ≤ 0 — nothing to allocate.`,
    };
  }

  if (line.QtyUnallocated <= EPSILON) {
    return {
      lineNbr: line.LineNbr,
      lotSerialNumbers: [],
      totalAllocated: 0,
      status: 'skipped',
      reason: `Line ${line.LineNbr} is already fully allocated.`,
    };
  }

  // ── 3. Filter and sort candidates ────────────────────────────────────────
  const available = candidates.filter((lot) => lot.QtyAvailable > EPSILON);

  if (available.length === 0) {
    return {
      lineNbr: line.LineNbr,
      lotSerialNumbers: [],
      totalAllocated: 0,
      status: 'manual_required',
      reason: `No lots with available quantity found for inventory item "${line.InventoryID}".`,
    };
  }

  const sorted = [...available].sort((a, b) =>
    compareLots(a, b, rule.sizeSortDirection),
  );

  // ── 4. Run the greedy allocation ─────────────────────────────────────────
  return greedyAllocate(line, sorted, rule);
}

/**
 * Allocate lots for all lines on a sales order.
 *
 * Iterates through each line in `lines` and calls {@link allocateLine}.
 * The `lotsByInventoryID` map must be pre-populated with all available
 * lot/serial candidates for every `InventoryID` that appears in `lines`.
 *
 * Lines whose `InventoryID` has no entry in `lotsByInventoryID` are treated
 * as having zero candidates and will be marked `manual_required` unless they
 * are already fully allocated or have a zero/negative ordered quantity.
 *
 * @param event             - The trigger event carrying `orderType` and `orderNbr`
 * @param lines             - All detail lines from the sales order
 * @param lotsByInventoryID - Map of InventoryID → available lot candidates
 * @returns                 - Array of {@link AllocationResult}, one per line,
 *                            in the same order as `lines`
 *
 * @example
 * ```ts
 * const results = allocateOrder(event, orderLines, lotsMap);
 * const failures = results.filter(r => r.status === 'manual_required');
 * if (failures.length > 0) { await flagForManualReview(failures); }
 * ```
 */
export function allocateOrder(
  event: SalesOrderEvent,
  lines: SalesOrderLine[],
  lotsByInventoryID: Map<string, LotSerialRecord[]>,
): AllocationResult[] {
  // Validate the order type up front so we can short-circuit all lines if
  // the rule is absent or disabled — avoids redundant per-line lookups.
  const rule: AllocationRule | undefined = ALLOCATION_RULES[event.orderType];

  if (rule === undefined) {
    return lines.map((line) => ({
      lineNbr: line.LineNbr,
      lotSerialNumbers: [],
      totalAllocated: 0,
      status: 'skipped' as const,
      reason: `No allocation rule configured for order type "${event.orderType}".`,
    }));
  }

  if (!rule.enabled) {
    return lines.map((line) => ({
      lineNbr: line.LineNbr,
      lotSerialNumbers: [],
      totalAllocated: 0,
      status: 'skipped' as const,
      reason: `Allocation is disabled for order type "${event.orderType}".`,
    }));
  }

  return lines.map((line) => {
    const candidates = lotsByInventoryID.get(line.InventoryID) ?? [];
    return allocateLine(line, candidates);
  });
}
