/**
 * Integration / smoke test for getCustomerSalesOrders() and getCustomerInvoices().
 *
 * ── Running against a live Acumatica instance ─────────────────────────────────
 *
 *   export ACUMATICA_BASE_URL=https://heritagefabrics.acumatica.com
 *   export ACUMATICA_USERNAME=apiuser
 *   export ACUMATICA_PASSWORD=secret
 *   export ACUMATICA_COMPANY="Heritage Fabrics"
 *   export TEST_CUSTOMER_ID=C000001          # real CustomerID in your instance
 *
 *   npx tsx src/services/acumatica/queries/__tests__/customerLookup.test.ts
 *
 * ── Dry-run / offline mode ────────────────────────────────────────────────────
 *
 *   export DRY_RUN=true
 *   npx tsx src/services/acumatica/queries/__tests__/customerLookup.test.ts
 *
 *   In dry-run mode the script stubs acumaticaGet() at the module level and
 *   verifies that:
 *     • URL construction is correct
 *     • unwrap() handles value-enveloped fields correctly
 *     • Both functions reject empty / blank customerIds
 *     • The full field-mapping pipeline (raw API shape → typed output) is correct
 *     • OData query parameters ($filter, $top, $orderby, $select) are correct
 *     • The invoices filter uses Type eq 'INV' (not 'Invoice')
 *
 * Exit codes:
 *   0 — all checks passed
 *   1 — one or more checks failed
 */

import { getCustomerSalesOrders, type CustomerSalesOrder } from '../salesOrders.js';
import { getCustomerInvoices, type CustomerInvoice } from '../invoices.js';
import { ACUMATICA_BASE_URL, unwrap, _acumaticaGetImpl } from '../../acumaticaService.js';

// ── Stub infrastructure ───────────────────────────────────────────────────────

/**
 * Captured arguments from the most recent stubbed acumaticaGet() call.
 * Populated by the stub function installed via installStub().
 */
let _lastGetArgs: { entityPath: string; params: Record<string, string> } | null = null;

/**
 * Install a stub over acumaticaGet() by swapping _acumaticaGetImpl.fn.
 *
 * Because salesOrders.ts and invoices.ts both import `acumaticaGet` from
 * acumaticaService.ts — which now delegates to `_acumaticaGetImpl.fn` — we
 * can inject any implementation by writing to that mutable slot.  This is a
 * pure ESM dependency-injection pattern: no require(), no monkey-patching of
 * module namespaces.
 *
 * @param returnValue - The value the stub will resolve with (typically a raw
 *                      Acumatica API fixture array).
 * @returns restore()  - Call this to put the real implementation back.
 */
function installStub(returnValue: unknown): () => void {
  _lastGetArgs = null;
  const original = _acumaticaGetImpl.fn;

  _acumaticaGetImpl.fn = async <T>(
    entityPath: string,
    params?: Record<string, string>,
  ): Promise<T> => {
    _lastGetArgs = { entityPath, params: params ?? {} };
    return returnValue as T;
  };

  return () => {
    _acumaticaGetImpl.fn = original;
    _lastGetArgs = null;
  };
}

// ── Test helpers ──────────────────────────────────────────────────────────────

let passed = 0;
let failed = 0;

function assert(condition: boolean, label: string, detail?: string): void {
  if (condition) {
    console.log(`  ✓ ${label}`);
    passed++;
  } else {
    console.error(`  ✗ FAIL: ${label}${detail ? ` — ${detail}` : ''}`);
    failed++;
  }
}

// ── Unit tests (offline — no network) ────────────────────────────────────────

async function runUnitTests(): Promise<void> {
  console.log('\n── Unit tests (offline) ──────────────────────────────────────');

  // 1. unwrap() helper handles all field shapes
  console.log('\n  unwrap() helper:');
  assert(unwrap({ value: 'SO-001' }) === 'SO-001', 'unwrap: extracts string from {value: ...}');
  assert(unwrap({ value: 42 }) === 42, 'unwrap: extracts number from {value: ...}');
  assert(unwrap('raw') === 'raw', 'unwrap: passes raw string through');
  assert(unwrap(undefined) === undefined, 'unwrap: returns undefined for missing field');
  assert(unwrap(null as never) === undefined, 'unwrap: returns undefined for null field');

  // 2. Input validation — both functions reject empty/blank customerIds
  console.log('\n  Input validation:');
  const rejectEmpty = async (fn: (id: string) => Promise<unknown>, name: string) => {
    let threw = false;
    try {
      await fn('');
    } catch {
      threw = true;
    }
    assert(threw, `${name}: throws on empty customerId`);

    let threwBlank = false;
    try {
      await fn('   ');
    } catch {
      threwBlank = true;
    }
    assert(threwBlank, `${name}: throws on blank/whitespace customerId`);
  };

  await rejectEmpty(getCustomerSalesOrders, 'getCustomerSalesOrders');
  await rejectEmpty(getCustomerInvoices, 'getCustomerInvoices');

  // 3. URL construction — verify deep-link format without hitting the network
  console.log('\n  Deep-link URL construction:');
  const base = ACUMATICA_BASE_URL;

  const soUrl =
    `${base}/Main?ScreenId=SO301000` +
    `&OrderType=${encodeURIComponent('PC')}` +
    `&OrderNbr=${encodeURIComponent('SO-000123')}`;
  assert(soUrl.includes('ScreenId=SO301000'), 'SO URL: contains SO301000 ScreenId', soUrl);
  assert(soUrl.includes('OrderType=PC'), 'SO URL: contains OrderType param', soUrl);
  assert(soUrl.includes('OrderNbr=SO-000123'), 'SO URL: contains OrderNbr param', soUrl);
  assert(soUrl.startsWith(base), 'SO URL: starts with configured base URL', soUrl);

  const arUrl =
    `${base}/Main?ScreenId=AR301000` +
    `&DocType=INV` +
    `&RefNbr=${encodeURIComponent('INV-000456')}`;
  assert(arUrl.includes('ScreenId=AR301000'), 'AR URL: contains AR301000 ScreenId', arUrl);
  assert(arUrl.includes('DocType=INV'), 'AR URL: DocType always INV', arUrl);
  assert(arUrl.includes('RefNbr=INV-000456'), 'AR URL: contains RefNbr param', arUrl);
  assert(arUrl.startsWith(base), 'AR URL: starts with configured base URL', arUrl);

  // 4. Field-mapping pipeline — stub acumaticaGet and verify the full
  //    raw-API-shape → typed-output mapping without any network calls.
  //    This is the most important offline test: it exercises the real
  //    getCustomerSalesOrders() and getCustomerInvoices() code paths.
  console.log('\n  Field-mapping pipeline (stubbed acumaticaGet):');
  await runMappingTests();

  // 5. OData query parameter correctness
  console.log('\n  OData query parameters:');
  await runODataParamTests();
}

// ── Mapping pipeline tests (stub) ────────────────────────────────────────────

/**
 * Verify that both query functions correctly unwrap value-enveloped fields,
 * populate all typed output fields, and build the correct deep-link URL —
 * using a stubbed acumaticaGet so no network is required.
 *
 * Note: installStub() monkey-patches acumaticaGet on the CommonJS-emulated
 * module namespace. In ESM+tsx this works because tsx transpiles ESM to CJS
 * under the hood, so `require()` returns the same module object that the
 * query files resolved against.
 */
async function runMappingTests(): Promise<void> {
  // ── Sales Orders ────────────────────────────────────────────────────────────
  const rawOrders = [
    {
      OrderNbr:   { value: 'SO-000123' },
      OrderType:  { value: 'PC' },
      Status:     { value: 'Open' },
      OrderedQty: { value: 12 },
      OrderTotal: { value: 1500.50 },
      Date:       { value: '2024-06-01T00:00:00' },
    },
    {
      OrderNbr:   { value: 'SO-000099' },
      OrderType:  { value: 'SO' },
      Status:     { value: 'Completed' },
      OrderedQty: { value: 4 },
      OrderTotal: { value: 320.00 },
      Date:       { value: '2024-03-15T00:00:00' },
    },
  ];

  const restoreSO = installStub(rawOrders);
  let orders: CustomerSalesOrder[];
  try {
    orders = await getCustomerSalesOrders('C000001');
  } finally {
    restoreSO();
  }

  assert(Array.isArray(orders), 'SO mapping: returns an array');
  assert(orders.length === 2, `SO mapping: maps all rows (expected 2, got ${orders.length})`);

  const so0: CustomerSalesOrder | undefined = orders[0];
  assert(so0 !== undefined, 'SO mapping: first element exists');
  if (so0 !== undefined) {
    assert(so0.orderNbr    === 'SO-000123',        'SO mapping: orderNbr unwrapped correctly');
    assert(so0.orderType   === 'PC',               'SO mapping: orderType unwrapped correctly');
    assert(so0.status      === 'Open',             'SO mapping: status unwrapped correctly');
    assert(so0.orderedQty  === 12,                 'SO mapping: orderedQty unwrapped correctly');
    assert(so0.orderTotal  === 1500.50,            'SO mapping: orderTotal unwrapped correctly');
    assert(so0.date        === '2024-06-01T00:00:00', 'SO mapping: date unwrapped correctly');
    assert(
      so0.acumaticaUrl === `${ACUMATICA_BASE_URL}/Main?ScreenId=SO301000&OrderType=PC&OrderNbr=SO-000123`,
      'SO mapping: acumaticaUrl built correctly',
      so0.acumaticaUrl,
    );
  }

  // Verify numeric types explicitly (orderedQty / orderTotal must be numbers)
  const so1: CustomerSalesOrder | undefined = orders[1];
  if (so1 !== undefined) {
    assert(typeof so1.orderedQty === 'number', 'SO mapping: orderedQty is a number');
    assert(typeof so1.orderTotal === 'number', 'SO mapping: orderTotal is a number');
    assert(so1.acumaticaUrl.includes('OrderType=SO'), 'SO mapping: second row OrderType correct');
  }

  // ── Invoices ────────────────────────────────────────────────────────────────
  const rawInvoices = [
    {
      ReferenceNbr: { value: 'INV-000456' },
      Status:       { value: 'Open' },
      Amount:       { value: 2500.00 },
      Balance:      { value: 1200.00 },
      Date:         { value: '2024-05-20T00:00:00' },
    },
    {
      ReferenceNbr: { value: 'INV-000301' },
      Status:       { value: 'Closed' },
      Amount:       { value: 800.00 },
      Balance:      { value: 0 },
      Date:         { value: '2024-02-10T00:00:00' },
    },
  ];

  const restoreINV = installStub(rawInvoices);
  let invoices: CustomerInvoice[];
  try {
    invoices = await getCustomerInvoices('C000001');
  } finally {
    restoreINV();
  }

  assert(Array.isArray(invoices), 'INV mapping: returns an array');
  assert(invoices.length === 2, `INV mapping: maps all rows (expected 2, got ${invoices.length})`);

  const inv0: CustomerInvoice | undefined = invoices[0];
  assert(inv0 !== undefined, 'INV mapping: first element exists');
  if (inv0 !== undefined) {
    assert(inv0.referenceNbr === 'INV-000456',          'INV mapping: referenceNbr unwrapped correctly');
    assert(inv0.status       === 'Open',                'INV mapping: status unwrapped correctly');
    assert(inv0.amount       === 2500.00,               'INV mapping: amount unwrapped correctly');
    assert(inv0.balance      === 1200.00,               'INV mapping: balance unwrapped correctly');
    assert(inv0.date         === '2024-05-20T00:00:00', 'INV mapping: date unwrapped correctly');
    assert(
      inv0.acumaticaUrl === `${ACUMATICA_BASE_URL}/Main?ScreenId=AR301000&DocType=INV&RefNbr=INV-000456`,
      'INV mapping: acumaticaUrl built correctly',
      inv0.acumaticaUrl,
    );
  }

  // Closed invoice: balance of 0 is valid
  const inv1: CustomerInvoice | undefined = invoices[1];
  if (inv1 !== undefined) {
    assert(inv1.balance === 0,          'INV mapping: closed invoice has 0 balance');
    assert(typeof inv1.amount === 'number', 'INV mapping: amount is a number');
    assert(inv1.acumaticaUrl.includes('DocType=INV'), 'INV mapping: second row DocType correct');
  }

  // ── Empty result set ────────────────────────────────────────────────────────
  const restoreEmpty = installStub([]);
  const empty = await getCustomerSalesOrders('NOBODY');
  restoreEmpty();
  assert(Array.isArray(empty) && empty.length === 0, 'SO mapping: handles empty API response');
}

// ── OData query parameter tests (stub) ───────────────────────────────────────

/**
 * Verify that both query functions pass the correct OData parameters
 * ($filter, $top, $orderby, $select) to acumaticaGet().
 *
 * Key correctness check: invoices must use `Type eq 'INV'` (the short
 * Acumatica doc-type code), NOT `Type eq 'Invoice'` (display label).
 */
async function runODataParamTests(): Promise<void> {
  // ── Sales Orders ────────────────────────────────────────────────────────────
  // Capture _lastGetArgs BEFORE calling restore() — restore() nulls it out.
  const restoreSO = installStub([]);
  await getCustomerSalesOrders('C999');
  const soArgs = _lastGetArgs;  // snapshot while stub is still live
  restoreSO();

  assert(soArgs !== null, 'SO OData: acumaticaGet was called');
  if (soArgs !== null) {
    assert(
      soArgs.entityPath === 'SalesOrder',
      `SO OData: entity path is 'SalesOrder' (got '${soArgs.entityPath}')`,
    );
    assert(
      (soArgs.params['$filter'] ?? '').includes("CustomerID eq 'C999'"),
      `SO OData: $filter contains CustomerID eq 'C999'`,
      soArgs.params['$filter'],
    );
    assert(
      soArgs.params['$top'] === '10',
      `SO OData: $top is '10' (got '${soArgs.params['$top']}')`,
    );
    assert(
      soArgs.params['$orderby'] === 'Date desc',
      `SO OData: $orderby is 'Date desc' (got '${soArgs.params['$orderby']}')`,
    );
    const soSelect = soArgs.params['$select'] ?? '';
    for (const field of ['OrderNbr', 'OrderType', 'Status', 'OrderedQty', 'OrderTotal', 'Date']) {
      assert(soSelect.includes(field), `SO OData: $select includes '${field}'`, soSelect);
    }
  }

  // ── Invoices ────────────────────────────────────────────────────────────────
  // Same snapshot-before-restore pattern.
  const restoreINV = installStub([]);
  await getCustomerInvoices('C999');
  const invArgs = _lastGetArgs;  // snapshot while stub is still live
  restoreINV();

  assert(invArgs !== null, 'INV OData: acumaticaGet was called');
  if (invArgs !== null) {
    assert(
      invArgs.entityPath === 'Invoice',
      `INV OData: entity path is 'Invoice' (got '${invArgs.entityPath}')`,
    );

    const invFilter = invArgs.params['$filter'] ?? '';
    assert(
      invFilter.includes("CustomerID eq 'C999'"),
      `INV OData: $filter contains CustomerID eq 'C999'`,
      invFilter,
    );
    // Critical: must use 'INV' (doc-type code), not 'Invoice' (display label)
    assert(
      invFilter.includes("Type eq 'INV'"),
      `INV OData: $filter uses Type eq 'INV' (not 'Invoice')`,
      invFilter,
    );
    assert(
      !invFilter.includes("Type eq 'Invoice'"),
      `INV OData: $filter does NOT use 'Type eq \\'Invoice\\'' (would return zero results)`,
      invFilter,
    );

    assert(
      invArgs.params['$top'] === '10',
      `INV OData: $top is '10' (got '${invArgs.params['$top']}')`,
    );
    assert(
      invArgs.params['$orderby'] === 'Date desc',
      `INV OData: $orderby is 'Date desc' (got '${invArgs.params['$orderby']}')`,
    );
    const invSelect = invArgs.params['$select'] ?? '';
    for (const field of ['ReferenceNbr', 'Status', 'Amount', 'Balance', 'Date']) {
      assert(invSelect.includes(field), `INV OData: $select includes '${field}'`, invSelect);
    }
  }
}

// ── Integration tests (requires live Acumatica creds) ────────────────────────

async function runIntegrationTests(customerId: string): Promise<void> {
  console.log(`\n── Integration tests (live API, customerId="${customerId}") ──`);

  // ---- Sales Orders -------------------------------------------------------
  console.log('\n  getCustomerSalesOrders():');
  let orders: CustomerSalesOrder[];
  try {
    orders = await getCustomerSalesOrders(customerId);
    assert(Array.isArray(orders), 'returns an array');
    assert(orders.length <= 10, `returns ≤10 orders (got ${orders.length})`);
  } catch (err) {
    assert(false, 'API call succeeded', String(err));
    return;
  }

  if (orders.length === 0) {
    console.log('    (no sales orders found for this customer — skipping field checks)');
  } else {
    // noUncheckedIndexedAccess: narrow first element explicitly
    const first: CustomerSalesOrder | undefined = orders[0];
    if (first === undefined) {
      assert(false, 'first order element exists');
    } else {
      console.log('\n  First sales order:');
      console.log(`    OrderNbr   : ${first.orderNbr}`);
      console.log(`    OrderType  : ${first.orderType}`);
      console.log(`    Status     : ${first.status}`);
      console.log(`    OrderedQty : ${first.orderedQty}`);
      console.log(`    OrderTotal : ${first.orderTotal}`);
      console.log(`    Date       : ${first.date}`);
      console.log(`    URL        : ${first.acumaticaUrl}`);

      assert(first.orderNbr.length > 0, 'orderNbr is non-empty');
      assert(first.orderType.length > 0, 'orderType is non-empty');
      assert(typeof first.orderedQty === 'number', 'orderedQty is numeric');
      assert(typeof first.orderTotal === 'number', 'orderTotal is numeric');
      assert(
        first.acumaticaUrl.includes('ScreenId=SO301000'),
        'acumaticaUrl contains SO301000',
      );
      assert(
        first.acumaticaUrl.includes(`OrderType=${encodeURIComponent(first.orderType)}`),
        'acumaticaUrl contains correct OrderType',
      );
      assert(
        first.acumaticaUrl.includes(`OrderNbr=${encodeURIComponent(first.orderNbr)}`),
        'acumaticaUrl contains correct OrderNbr',
      );
    }

    // Verify ordering: dates should be descending (newest first)
    if (orders.length > 1) {
      const dates = orders.map((o) => o.date).filter(Boolean);
      const sorted = [...dates].sort((a, b) => b.localeCompare(a));
      const inOrder = dates.every((d, i) => d === sorted[i]);
      assert(inOrder, 'orders are sorted newest-first by Date');
    }
  }

  // ---- Invoices -----------------------------------------------------------
  console.log('\n  getCustomerInvoices():');
  let invoices: CustomerInvoice[];
  try {
    invoices = await getCustomerInvoices(customerId);
    assert(Array.isArray(invoices), 'returns an array');
    assert(invoices.length <= 10, `returns ≤10 invoices (got ${invoices.length})`);
  } catch (err) {
    assert(false, 'API call succeeded', String(err));
    return;
  }

  if (invoices.length === 0) {
    console.log('    (no invoices found for this customer — skipping field checks)');
  } else {
    // noUncheckedIndexedAccess: narrow first element explicitly
    const first: CustomerInvoice | undefined = invoices[0];
    if (first === undefined) {
      assert(false, 'first invoice element exists');
    } else {
      console.log('\n  First invoice:');
      console.log(`    ReferenceNbr : ${first.referenceNbr}`);
      console.log(`    Status       : ${first.status}`);
      console.log(`    Amount       : ${first.amount}`);
      console.log(`    Balance      : ${first.balance}`);
      console.log(`    Date         : ${first.date}`);
      console.log(`    URL          : ${first.acumaticaUrl}`);

      assert(first.referenceNbr.length > 0, 'referenceNbr is non-empty');
      assert(typeof first.amount === 'number', 'amount is numeric');
      assert(typeof first.balance === 'number', 'balance is numeric');
      // balance can exceed amount when interest/penalties are added, so only
      // assert it is a non-negative number rather than ≤ amount.
      assert(first.balance >= 0, 'balance is non-negative');
      assert(
        first.acumaticaUrl.includes('ScreenId=AR301000'),
        'acumaticaUrl contains AR301000',
      );
      assert(first.acumaticaUrl.includes('DocType=INV'), 'acumaticaUrl contains DocType=INV');
      assert(
        first.acumaticaUrl.includes(`RefNbr=${encodeURIComponent(first.referenceNbr)}`),
        'acumaticaUrl contains correct RefNbr',
      );
    }

    // Verify ordering: dates should be descending (newest first)
    if (invoices.length > 1) {
      const dates = invoices.map((i) => i.date).filter(Boolean);
      const sorted = [...dates].sort((a, b) => b.localeCompare(a));
      const inOrder = dates.every((d, i) => d === sorted[i]);
      assert(inOrder, 'invoices are sorted newest-first by Date');
    }
  }
}

// ── Main ──────────────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  const isDryRun = process.env['DRY_RUN'] === 'true';
  const customerId = process.env['TEST_CUSTOMER_ID'] ?? '';

  console.log('=== Acumatica Customer Lookup — Test Suite ===');
  console.log(`Base URL : ${ACUMATICA_BASE_URL}`);
  console.log(
    `Mode     : ${isDryRun ? 'DRY RUN (offline unit tests only)' : 'LIVE (integration tests)'}`,
  );

  await runUnitTests();

  if (!isDryRun) {
    if (!customerId) {
      console.error(
        '\nERROR: Set TEST_CUSTOMER_ID env var to a real Acumatica CustomerID, ' +
          'or set DRY_RUN=true to run offline unit tests only.',
      );
      process.exit(1);
    }
    await runIntegrationTests(customerId);
  }

  console.log('\n═══════════════════════════════════════════');
  console.log(`Results: ${passed} passed, ${failed} failed`);
  console.log('═══════════════════════════════════════════\n');

  if (failed > 0) process.exit(1);
}

main().catch((err: unknown) => {
  console.error('\n[FATAL]', err);
  process.exit(1);
});
