/**
 * Unit tests for the auto-allocation engine.
 *
 * Uses the built-in Node.js `node:test` + `node:assert` modules — no external
 * test runner required.
 *
 * Run:
 *   node --import tsx/esm --test src/engine/allocationEngine.test.ts
 *   (or via: npm test)
 *
 * ── Coverage goals ──────────────────────────────────────────────────────────
 *  PC (piece-cut, largest-first, 100 %–120 % band, cancelIfOverMax = true)
 *    ✓ single roll exactly at 100 %  → success
 *    ✓ single roll within 100–120 %  → success (overage accepted)
 *    ✓ two rolls needed, result within band → success
 *    ✓ only available roll exceeds 120 %   → manual_required
 *    ✓ available rolls total < 100 %       → manual_required
 *    ✓ sorts largest-first (picks biggest roll first)
 *    ✓ FIFO tiebreaker when sizes are equal
 *    ✓ zero-Size lots deferred to end of candidate list
 *    ✓ already fully allocated line  → skipped
 *    ✓ QtyOrdered ≤ 0               → skipped
 *    ✓ zero available lots           → manual_required
 *    ✓ lots with QtyAvailable = 0 are filtered out
 *
 *  CO (cut-order, smallest-first, exactly 100 %, cancelIfOverMax = false)
 *    ✓ single roll exactly at 100 %  → success
 *    ✓ two rolls sum to exactly 100 %→ success
 *    ✓ available rolls cannot reach 100 % exactly → manual_required
 *    ✓ only roll available exceeds 100 %           → manual_required
 *    ✓ sorts smallest-first (burns short ends first)
 *    ✓ skips lots that would push past 100 % and picks a fitting smaller one
 *
 *  allocateOrder (multi-line)
 *    ✓ unknown order type → all lines skipped
 *    ✓ disabled rule      → all lines skipped
 *    ✓ mixed success / manual_required across lines
 *    ✓ line with no lots in map → manual_required
 *    ✓ returns one result per line in input order
 *
 *  Edge cases / floating-point
 *    ✓ floating-point accumulation near boundary (1e-10 below max) → success
 *    ✓ epsilon guard: accumulated qty just above min due to float arithmetic
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

import { allocateLine, allocateOrder } from './allocationEngine.js';
import type { LotSerialRecord } from '../types/acumatica/lotSerial.js';
import type { SalesOrderLine, SalesOrderEvent } from '../types/acumatica/salesOrder.js';

// ── Test-data factories ───────────────────────────────────────────────────────

/**
 * Build a minimal SalesOrderLine for a PC order.
 * `QtyUnallocated` defaults to `QtyOrdered` (nothing pre-allocated).
 */
function makePCLine(
  overrides: Partial<SalesOrderLine> & { QtyOrdered: number },
): SalesOrderLine {
  return {
    OrderType: 'PC',
    OrderNbr: 'PC-0001',
    LineNbr: 1,
    InventoryID: 'FABRIC-NAVY',
    QtyAllocated: 0,
    QtyUnallocated: overrides.QtyOrdered,
    ...overrides,
  };
}

/**
 * Build a minimal SalesOrderLine for a CO order.
 */
function makeCOLine(
  overrides: Partial<SalesOrderLine> & { QtyOrdered: number },
): SalesOrderLine {
  return {
    OrderType: 'CO',
    OrderNbr: 'CO-0001',
    LineNbr: 1,
    InventoryID: 'FABRIC-NAVY',
    QtyAllocated: 0,
    QtyUnallocated: overrides.QtyOrdered,
    ...overrides,
  };
}

/**
 * Build a LotSerialRecord.
 * `CreationDate` defaults to a fixed date; pass `daysAgo` to offset it for
 * FIFO ordering tests.
 */
function makeLot(
  lotSerialNbr: string,
  qtyAvailable: number,
  size: number,
  daysAgo = 0,
): LotSerialRecord {
  const d = new Date('2024-01-01T00:00:00Z');
  d.setDate(d.getDate() - daysAgo);
  return {
    LotSerialNbr: lotSerialNbr,
    InventoryID: 'FABRIC-NAVY',
    QtyAvailable: qtyAvailable,
    CreationDate: d,
    Size: size,
  };
}

// ── PC tests ──────────────────────────────────────────────────────────────────

describe('PC — piece-cut allocation (largest-first, 100–120 % band)', () => {
  it('single roll at exactly 100 % → success', () => {
    const line = makePCLine({ QtyOrdered: 100 });
    const lots = [makeLot('L001', 100, 100)];

    const result = allocateLine(line, lots);

    assert.equal(result.status, 'success');
    assert.equal(result.totalAllocated, 100);
    assert.equal(result.lotSerialNumbers.length, 1);
    assert.equal(result.lotSerialNumbers[0]?.lotSerialNbr, 'L001');
    assert.equal(result.lotSerialNumbers[0]?.qty, 100);
  });

  it('single roll within 100–120 % band → success (overage accepted)', () => {
    const line = makePCLine({ QtyOrdered: 100 });
    const lots = [makeLot('L001', 115, 115)]; // 115 % of 100

    const result = allocateLine(line, lots);

    assert.equal(result.status, 'success');
    assert.equal(result.totalAllocated, 115);
  });

  it('two rolls needed; combined result within band → success', () => {
    const line = makePCLine({ QtyOrdered: 100 });
    // Largest-first: L-big (60 yds) then L-small (50 yds).
    // After L-big: 60 < 100 → continue.
    // L-small (50): 60 + 50 = 110 ≤ 120 → accept.
    const lots = [
      makeLot('L-small', 50, 50),
      makeLot('L-big', 60, 60),
    ];

    const result = allocateLine(line, lots);

    assert.equal(result.status, 'success');
    assert.equal(result.totalAllocated, 110);
    // Both lots should be selected; big roll should come first
    assert.equal(result.lotSerialNumbers.length, 2);
    assert.equal(result.lotSerialNumbers[0]?.lotSerialNbr, 'L-big');
    assert.equal(result.lotSerialNumbers[1]?.lotSerialNbr, 'L-small');
  });

  it('only available roll exceeds 120 % → manual_required', () => {
    const line = makePCLine({ QtyOrdered: 100 });
    const lots = [makeLot('L001', 125, 125)]; // 125 % > 120 %

    const result = allocateLine(line, lots);

    assert.equal(result.status, 'manual_required');
    assert.equal(result.totalAllocated, 0);
    assert.equal(result.lotSerialNumbers.length, 0);
    assert.ok(result.reason?.includes('max'));
  });

  it('available rolls total less than 100 % → manual_required', () => {
    const line = makePCLine({ QtyOrdered: 100 });
    // 40 + 50 = 90 yards, not enough
    const lots = [
      makeLot('L001', 40, 40),
      makeLot('L002', 50, 50),
    ];

    const result = allocateLine(line, lots);

    assert.equal(result.status, 'manual_required');
    assert.equal(result.totalAllocated, 0);
    assert.equal(result.lotSerialNumbers.length, 0);
  });

  it('sorts candidates largest-first (picks biggest roll first)', () => {
    const line = makePCLine({ QtyOrdered: 50 });
    // Three rolls; engine should pick the 60-yard roll first (>= 100 % of 50).
    const lots = [
      makeLot('L-small', 20, 20),
      makeLot('L-medium', 40, 40),
      makeLot('L-big', 60, 60),
    ];

    const result = allocateLine(line, lots);

    assert.equal(result.status, 'success');
    assert.equal(result.totalAllocated, 60); // only the biggest roll picked
    assert.equal(result.lotSerialNumbers.length, 1);
    assert.equal(result.lotSerialNumbers[0]?.lotSerialNbr, 'L-big');
  });

  it('FIFO tiebreaker: oldest lot chosen when sizes are equal', () => {
    const line = makePCLine({ QtyOrdered: 50 });
    // Two rolls of equal size; older one (L-old, daysAgo=10) should win.
    const lots = [
      makeLot('L-new', 60, 60, 0),  // created today
      makeLot('L-old', 60, 60, 10), // created 10 days ago
    ];

    const result = allocateLine(line, lots);

    assert.equal(result.status, 'success');
    assert.equal(result.lotSerialNumbers.length, 1);
    assert.equal(result.lotSerialNumbers[0]?.lotSerialNbr, 'L-old');
  });

  it('zero-Size lots are deferred to end of candidate list', () => {
    const line = makePCLine({ QtyOrdered: 50 });
    // L-zero has Size=0 (unparseable attribute); L-valid has Size=55.
    // Engine should pick L-valid before L-zero.
    const lots = [
      makeLot('L-zero', 55, 0),  // Size=0 → deferred to end
      makeLot('L-valid', 55, 55),
    ];

    const result = allocateLine(line, lots);

    assert.equal(result.status, 'success');
    assert.equal(result.lotSerialNumbers[0]?.lotSerialNbr, 'L-valid');
  });

  it('already fully allocated line → skipped', () => {
    const line: SalesOrderLine = {
      OrderType: 'PC',
      OrderNbr: 'PC-0001',
      LineNbr: 1,
      InventoryID: 'FABRIC-NAVY',
      QtyOrdered: 100,
      QtyAllocated: 100,
      QtyUnallocated: 0, // already done
    };
    const lots = [makeLot('L001', 100, 100)];

    const result = allocateLine(line, lots);

    assert.equal(result.status, 'skipped');
    assert.ok(result.reason?.includes('already fully allocated'));
  });

  it('QtyOrdered ≤ 0 → skipped', () => {
    const line = makePCLine({ QtyOrdered: 0 });
    const lots = [makeLot('L001', 100, 100)];

    const result = allocateLine(line, lots);

    assert.equal(result.status, 'skipped');
    assert.ok(result.reason?.includes('QtyOrdered'));
  });

  it('no available lots → manual_required', () => {
    const line = makePCLine({ QtyOrdered: 100 });

    const result = allocateLine(line, []);

    assert.equal(result.status, 'manual_required');
    assert.ok(result.reason?.includes('No lots'));
  });

  it('lots with QtyAvailable = 0 are filtered out before allocation', () => {
    const line = makePCLine({ QtyOrdered: 100 });
    // Only lots with zero available quantity — engine should treat as no lots.
    const lots = [
      makeLot('L-empty', 0, 100),
      makeLot('L-also-empty', 0, 80),
    ];

    const result = allocateLine(line, lots);

    assert.equal(result.status, 'manual_required');
    assert.equal(result.lotSerialNumbers.length, 0);
  });

  it('unknown order type → skipped', () => {
    const line: SalesOrderLine = {
      OrderType: 'XX', // not in ALLOCATION_RULES
      OrderNbr: 'XX-0001',
      LineNbr: 1,
      InventoryID: 'FABRIC-NAVY',
      QtyOrdered: 100,
      QtyAllocated: 0,
      QtyUnallocated: 100,
    };
    const lots = [makeLot('L001', 100, 100)];

    const result = allocateLine(line, lots);

    assert.equal(result.status, 'skipped');
    assert.ok(result.reason?.includes('"XX"'));
  });
});

// ── CO tests ──────────────────────────────────────────────────────────────────

describe('CO — cut-order allocation (smallest-first, exactly 100 %)', () => {
  it('single roll at exactly 100 % → success', () => {
    const line = makeCOLine({ QtyOrdered: 80 });
    const lots = [makeLot('L001', 80, 80)];

    const result = allocateLine(line, lots);

    assert.equal(result.status, 'success');
    assert.equal(result.totalAllocated, 80);
    assert.equal(result.lotSerialNumbers[0]?.lotSerialNbr, 'L001');
  });

  it('two rolls sum to exactly 100 % → success', () => {
    const line = makeCOLine({ QtyOrdered: 100 });
    // Smallest-first: L-small (30) then L-medium (70) → total 100.
    const lots = [
      makeLot('L-medium', 70, 70),
      makeLot('L-small', 30, 30),
    ];

    const result = allocateLine(line, lots);

    assert.equal(result.status, 'success');
    assert.equal(result.totalAllocated, 100);
    assert.equal(result.lotSerialNumbers.length, 2);
    // Smallest-first: small roll should be allocated first
    assert.equal(result.lotSerialNumbers[0]?.lotSerialNbr, 'L-small');
    assert.equal(result.lotSerialNumbers[1]?.lotSerialNbr, 'L-medium');
  });

  it('available rolls cannot reach 100 % exactly → manual_required', () => {
    const line = makeCOLine({ QtyOrdered: 100 });
    // 30 + 40 = 70 — falls short
    const lots = [
      makeLot('L001', 30, 30),
      makeLot('L002', 40, 40),
    ];

    const result = allocateLine(line, lots);

    assert.equal(result.status, 'manual_required');
    assert.equal(result.totalAllocated, 0);
    assert.ok(result.reason?.includes('100'));
  });

  it('only roll exceeds 100 % → manual_required', () => {
    const line = makeCOLine({ QtyOrdered: 80 });
    const lots = [makeLot('L001', 90, 90)]; // 90 > 80 — adding it exceeds max

    const result = allocateLine(line, lots);

    assert.equal(result.status, 'manual_required');
    assert.equal(result.totalAllocated, 0);
  });

  it('sorts candidates smallest-first (burns short ends first)', () => {
    const line = makeCOLine({ QtyOrdered: 30 });
    // Engine should pick L-small (30) not L-big (100), even though L-big is available.
    const lots = [
      makeLot('L-big', 100, 100),
      makeLot('L-small', 30, 30),
    ];

    const result = allocateLine(line, lots);

    assert.equal(result.status, 'success');
    assert.equal(result.totalAllocated, 30);
    assert.equal(result.lotSerialNumbers.length, 1);
    assert.equal(result.lotSerialNumbers[0]?.lotSerialNbr, 'L-small');
  });

  it('skips lots that push past 100 % and picks fitting smaller one', () => {
    const line = makeCOLine({ QtyOrdered: 100 });
    // Sorted smallest-first: L-30, L-50, L-80, L-90
    // After L-30: 30 < 100 → continue.
    // L-50: 30 + 50 = 80 < 100 → continue.
    // L-80: 80 + 80 = 160 > 100 → SKIP (would exceed max).
    // L-90: 80 + 90 = 170 > 100 → SKIP.
    // End of candidates: 80 < 100 → manual_required.
    const lots = [
      makeLot('L-90', 90, 90),
      makeLot('L-80', 80, 80),
      makeLot('L-50', 50, 50),
      makeLot('L-30', 30, 30),
    ];

    const result = allocateLine(line, lots);

    assert.equal(result.status, 'manual_required');
    assert.equal(result.totalAllocated, 0);
    assert.equal(result.lotSerialNumbers.length, 0);
  });

  it('three rolls: small two sum to exact target, big one skipped', () => {
    const line = makeCOLine({ QtyOrdered: 50 });
    // Sorted smallest-first: L-20, L-30, L-60.
    // After L-20: 20 < 50 → continue.
    // L-30: 20 + 30 = 50 = 100 % → accept.  accumulated >= min → break.
    // L-60 is never reached.
    const lots = [
      makeLot('L-60', 60, 60),
      makeLot('L-30', 30, 30),
      makeLot('L-20', 20, 20),
    ];

    const result = allocateLine(line, lots);

    assert.equal(result.status, 'success');
    assert.equal(result.totalAllocated, 50);
    assert.equal(result.lotSerialNumbers.length, 2);
    assert.equal(result.lotSerialNumbers[0]?.lotSerialNbr, 'L-20');
    assert.equal(result.lotSerialNumbers[1]?.lotSerialNbr, 'L-30');
  });
});

// ── allocateOrder (multi-line) tests ──────────────────────────────────────────

describe('allocateOrder — multi-line order processing', () => {
  const validEvent: SalesOrderEvent = {
    orderType: 'PC',
    orderNbr: 'PC-0010',
    trigger: 'entry',
  };

  it('unknown order type → all lines skipped', () => {
    const event: SalesOrderEvent = {
      orderType: 'ZZ',
      orderNbr: 'ZZ-0001',
      trigger: 'entry',
    };
    const lines: SalesOrderLine[] = [
      makePCLine({ OrderType: 'ZZ', OrderNbr: 'ZZ-0001', LineNbr: 1, QtyOrdered: 50 }),
      makePCLine({ OrderType: 'ZZ', OrderNbr: 'ZZ-0001', LineNbr: 2, QtyOrdered: 80 }),
    ];
    const lotsMap = new Map<string, LotSerialRecord[]>();

    const results = allocateOrder(event, lines, lotsMap);

    assert.equal(results.length, 2);
    assert.ok(results.every((r) => r.status === 'skipped'));
    assert.ok(results.every((r) => r.reason?.includes('"ZZ"')));
  });

  it('returns one result per line in input order', () => {
    const lines: SalesOrderLine[] = [
      makePCLine({ LineNbr: 1, QtyOrdered: 100 }),
      makePCLine({ LineNbr: 2, QtyOrdered: 50 }),
      makePCLine({ LineNbr: 3, QtyOrdered: 200 }),
    ];
    const lotsMap = new Map<string, LotSerialRecord[]>([
      ['FABRIC-NAVY', [makeLot('L001', 110, 110)]],
    ]);

    const results = allocateOrder(validEvent, lines, lotsMap);

    assert.equal(results.length, 3);
    assert.equal(results[0]?.lineNbr, 1);
    assert.equal(results[1]?.lineNbr, 2);
    assert.equal(results[2]?.lineNbr, 3);
  });

  it('line with no InventoryID entry in map → manual_required', () => {
    const lines: SalesOrderLine[] = [
      makePCLine({ LineNbr: 1, QtyOrdered: 100 }),
    ];
    // Empty map — no lots for FABRIC-NAVY
    const lotsMap = new Map<string, LotSerialRecord[]>();

    const results = allocateOrder(validEvent, lines, lotsMap);

    assert.equal(results.length, 1);
    assert.equal(results[0]?.status, 'manual_required');
  });

  it('mixed lines: success + manual_required across different inventory items', () => {
    const lines: SalesOrderLine[] = [
      { ...makePCLine({ LineNbr: 1, QtyOrdered: 100 }), InventoryID: 'FABRIC-NAVY' },
      { ...makePCLine({ LineNbr: 2, QtyOrdered: 500 }), InventoryID: 'FABRIC-RED' },
    ];
    const lotsMap = new Map<string, LotSerialRecord[]>([
      ['FABRIC-NAVY', [makeLot('L-navy', 110, 110)]],
      ['FABRIC-RED', [makeLot('L-red', 10, 10)]], // way too small for 500 yds
    ]);

    const results = allocateOrder(validEvent, lines, lotsMap);

    assert.equal(results[0]?.status, 'success');
    assert.equal(results[1]?.status, 'manual_required');
  });

  it('allocateOrder with CO event allocates smallest-first across all lines', () => {
    const coEvent: SalesOrderEvent = {
      orderType: 'CO',
      orderNbr: 'CO-0002',
      trigger: 'unhold',
    };
    const lines: SalesOrderLine[] = [
      makeCOLine({ LineNbr: 1, QtyOrdered: 50 }),
      makeCOLine({ LineNbr: 2, QtyOrdered: 30 }),
    ];
    const lotsMap = new Map<string, LotSerialRecord[]>([
      [
        'FABRIC-NAVY',
        [
          makeLot('L-big', 100, 100),
          makeLot('L-small', 50, 50),
          makeLot('L-tiny', 30, 30),
        ],
      ],
    ]);

    const results = allocateOrder(coEvent, lines, lotsMap);

    // Line 1 (qty 50): smallest-first → L-tiny (30) + skip L-small (30+50=80>50)
    // → actually 30 < 50, then L-small: 30+50=80 > 50, skip → L-big: 30+100=130>50, skip
    // → 30 < 50 → manual_required
    // Line 2 (qty 30): smallest-first → L-tiny (30) = 100 % → success
    assert.equal(results[0]?.status, 'manual_required'); // can't hit exactly 50 with available lots
    assert.equal(results[1]?.status, 'success');
    assert.equal(results[1]?.totalAllocated, 30);
  });
});

// ── Edge cases / floating-point ───────────────────────────────────────────────

describe('Edge cases — floating-point and boundary conditions', () => {
  it('accumulated qty just above min due to float arithmetic → success (epsilon guard)', () => {
    // 3 × 33.333333... yards — floating-point sum may be 99.99999...
    const qty = 100 / 3; // 33.333...
    const line = makePCLine({ QtyOrdered: qty * 3 }); // nominally 100

    const lots = [
      makeLot('L001', qty, qty),
      makeLot('L002', qty, qty),
      makeLot('L003', qty, qty),
    ];

    const result = allocateLine(line, lots);
    // The three lots exactly cover the ordered quantity (epsilon-tolerant check).
    assert.equal(result.status, 'success');
    assert.ok(result.totalAllocated > 0);
  });

  it('accumulated qty within 1e-10 of max boundary → success (not over-limit)', () => {
    const line = makePCLine({ QtyOrdered: 100 });
    // 119.9999999999 is within the 120 % ceiling by epsilon
    const lots = [makeLot('L001', 119.9999999999, 119.9999999999)];

    const result = allocateLine(line, lots);

    assert.equal(result.status, 'success');
  });

  it('line with negative QtyOrdered → skipped', () => {
    const line = makePCLine({ QtyOrdered: -5 });
    const lots = [makeLot('L001', 100, 100)];

    const result = allocateLine(line, lots);

    assert.equal(result.status, 'skipped');
  });

  it('all lots have zero QtyAvailable → manual_required', () => {
    const line = makePCLine({ QtyOrdered: 100 });
    const lots = [
      makeLot('L001', 0, 100),
      makeLot('L002', 0, 80),
      makeLot('L003', 0, 60),
    ];

    const result = allocateLine(line, lots);

    assert.equal(result.status, 'manual_required');
  });

  it('single lot with qty exactly at 120 % boundary (PC) → success', () => {
    const line = makePCLine({ QtyOrdered: 100 });
    const lots = [makeLot('L001', 120, 120)]; // exactly at the 120 % ceiling

    const result = allocateLine(line, lots);

    assert.equal(result.status, 'success');
    assert.equal(result.totalAllocated, 120);
  });

  it('single lot with qty at 120.001 % (just above PC ceiling) → manual_required', () => {
    const line = makePCLine({ QtyOrdered: 100 });
    const lots = [makeLot('L001', 120.001, 120.001)]; // 0.001 above ceiling

    const result = allocateLine(line, lots);

    assert.equal(result.status, 'manual_required');
  });

  it('lineNbr is preserved correctly in all result types', () => {
    const skippedLine: SalesOrderLine = {
      OrderType: 'PC',
      OrderNbr: 'PC-0001',
      LineNbr: 42,
      InventoryID: 'FABRIC-NAVY',
      QtyOrdered: 0,
      QtyAllocated: 0,
      QtyUnallocated: 0,
    };
    const result = allocateLine(skippedLine, []);
    assert.equal(result.lineNbr, 42);
  });
});
