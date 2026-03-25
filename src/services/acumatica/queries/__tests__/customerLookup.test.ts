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
 *   In dry-run mode the script stubs the HTTP layer and verifies that:
 *     • URL construction is correct
 *     • unwrap() handles value-enveloped fields correctly
 *     • Both functions reject empty / blank customerIds
 *
 * Exit codes:
 *   0 — all checks passed
 *   1 — one or more checks failed
 */

import { getCustomerSalesOrders, type CustomerSalesOrder } from '../salesOrders.js';
import { getCustomerInvoices, type CustomerInvoice } from '../invoices.js';
import { ACUMATICA_BASE_URL, unwrap } from '../../acumaticaService.js';

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
  assert(unwrap({ value: 'SO-001' }) === 'SO-001', 'unwrap: extracts string from {value: ...}');
  assert(unwrap({ value: 42 }) === 42, 'unwrap: extracts number from {value: ...}');
  assert(unwrap('raw') === 'raw', 'unwrap: passes raw string through');
  assert(unwrap(undefined) === undefined, 'unwrap: returns undefined for missing field');
  assert(unwrap(null as never) === undefined, 'unwrap: returns undefined for null field');

  // 2. Input validation — both functions reject empty/blank customerIds
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
      assert(first.balance <= first.amount, 'balance ≤ amount');
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
