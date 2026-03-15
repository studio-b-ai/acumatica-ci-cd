/**
 * Lot/serial number types for the auto-allocation workflow.
 *
 * Acumatica stores lot/serial inventory under the INLotSerialStatus DAC.
 * `LotSerialRecord` models the fields the allocation engine fetches and the
 * one derived field (`Size`) it parses from lot attributes before sorting.
 */

// ── Sort direction ────────────────────────────────────────────────────────────

/**
 * Controls the order in which lots are considered during allocation.
 *
 * - `'asc'`  — smallest lots first (used for CO / cut-order allocation so
 *               short ends are consumed before full rolls).
 * - `'desc'` — largest lots first (used for PC / piece-cut allocation so
 *               the fewest number of rolls satisfies the order).
 */
export type LotSortDirection = 'asc' | 'desc';

// ── Lot/serial record ─────────────────────────────────────────────────────────

/**
 * A single lot or serial number record as returned by the Acumatica
 * Inventory → Lot/Serial Numbers inquiry (or equivalent REST endpoint).
 *
 * `Size` is NOT a native Acumatica field — it is parsed from the lot's
 * attribute set (e.g. the "Roll Yardage" or "Cut Size" attribute) by the
 * allocation engine after the API response is received.
 */
export interface LotSerialRecord {
  /** Acumatica lot or serial number identifier */
  LotSerialNbr: string;

  /** Acumatica inventory item ID — matches {@link SalesOrderLine.InventoryID} */
  InventoryID: string;

  /**
   * Quantity available for allocation.
   * Sourced from `INLotSerialStatus.QtyAvail` (excludes reserved / on-hold
   * quantities).
   */
  QtyAvailable: number;

  /**
   * Date the lot was received or created in Acumatica.
   * Used as a tiebreaker when two lots have equal `Size`.
   * Oldest-first (FIFO) is the preferred tiebreaker for both PC and CO.
   */
  CreationDate: Date;

  /**
   * Physical size of the lot in the item's base unit of measure (typically
   * yards for fabric rolls).
   *
   * Parsed from a lot attribute (e.g. "Roll Yardage") by the allocation
   * engine.  Stored as a plain number so standard numeric comparisons and
   * sorts work without further conversion.
   *
   * A value of `0` indicates the attribute was missing or could not be
   * parsed; such lots are moved to the end of the candidate list regardless
   * of `LotSortDirection`.
   */
  Size: number;
}
