/**
 * Sales Order queries for a given customer.
 *
 * Endpoint : GET /entity/default/24.200.001/SalesOrder
 * Screen   : SO301000
 *
 * Field names match the Acumatica default/24.200.001 entity schema and are
 * confirmed by entity-sync.py ENTITY_CONFIG ("SalesOrder") and
 * publish-manifest.json ("SalesOrder" → screen: "SO301000").
 */

import { acumaticaGet, ACUMATICA_BASE_URL, unwrap } from '../acumaticaService.js';

// ── Types ─────────────────────────────────────────────────────────────────────

/** Raw field shape returned by the Acumatica REST API (value-wrapped scalars). */
interface RawSalesOrder {
  OrderNbr?: { value: string };
  OrderType?: { value: string };
  Status?: { value: string };
  OrderedQty?: { value: number };
  OrderTotal?: { value: number };
  Date?: { value: string };
  CustomerID?: { value: string };
}

/** Clean, unwrapped record shape returned by getCustomerSalesOrders(). */
export interface CustomerSalesOrder {
  /** Acumatica order number, e.g. "SO-000123" */
  orderNbr: string;
  /** Order type code, e.g. "PC", "CO", "SO" */
  orderType: string;
  /** Order status, e.g. "Open", "Completed", "Cancelled" */
  status: string;
  /** Total quantity ordered */
  orderedQty: number;
  /** Order total value */
  orderTotal: number;
  /** ISO 8601 date string of the order */
  date: string;
  /**
   * Direct deep-link URL into the Acumatica SO301000 screen.
   * Format: https://{baseUrl}/Main?ScreenId=SO301000&OrderType={type}&OrderNbr={nbr}
   */
  acumaticaUrl: string;
}

// ── API call ─────────────────────────────────────────────────────────────────

/**
 * Retrieve the most recent 10 sales orders for a given Acumatica customer.
 *
 * Uses OData $filter, $top, $orderby, and $select to minimise payload size
 * and return results sorted newest-first — the same query pattern used in
 * entity-sync.py fetch_all() but with explicit field selection.
 *
 * @param customerId - Acumatica CustomerID (e.g. "C000123" or "HERITAGE")
 * @returns Array of up to 10 orders, newest first
 *
 * @example
 *   const orders = await getCustomerSalesOrders('C000123');
 *   console.log(orders[0].acumaticaUrl);
 */
export async function getCustomerSalesOrders(
  customerId: string,
): Promise<CustomerSalesOrder[]> {
  if (!customerId?.trim()) {
    throw new Error('getCustomerSalesOrders: customerId must be a non-empty string');
  }

  const raw = await acumaticaGet<RawSalesOrder[]>('SalesOrder', {
    // Filter to this customer only
    $filter: `CustomerID eq '${customerId.trim()}'`,
    // Return newest 10 orders
    $top: '10',
    // Newest first — Date descending
    $orderby: 'Date desc',
    // Fetch only the fields we need (reduces payload size)
    $select: 'OrderNbr,OrderType,Status,OrderedQty,OrderTotal,Date',
  });

  // Acumatica always returns an array; guard against null/non-array responses
  if (!Array.isArray(raw)) {
    throw new Error(
      `getCustomerSalesOrders: unexpected API response shape for customer "${customerId}"`,
    );
  }

  return raw.map((order): CustomerSalesOrder => {
    const orderNbr = unwrap(order.OrderNbr) ?? '';
    const orderType = unwrap(order.OrderType) ?? '';

    return {
      orderNbr,
      orderType,
      status: unwrap(order.Status) ?? '',
      orderedQty: unwrap(order.OrderedQty) ?? 0,
      orderTotal: unwrap(order.OrderTotal) ?? 0,
      date: unwrap(order.Date) ?? '',
      // Deep-link URL — format confirmed by publish-manifest.json (SO301000)
      acumaticaUrl:
        `${ACUMATICA_BASE_URL}/Main?ScreenId=SO301000` +
        `&OrderType=${encodeURIComponent(orderType)}` +
        `&OrderNbr=${encodeURIComponent(orderNbr)}`,
    };
  });
}
