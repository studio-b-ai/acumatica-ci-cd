/**
 * Unit tests — HubSpot Companies service
 *
 * Tests cover:
 *   • buildCompanyProperties mapping (via syncCustomerToHubSpot with mocked fetch)
 *   • findExistingCompany search logic (create vs update branching)
 *   • createCompany / updateCompany HTTP interactions
 *   • syncCustomerToHubSpot success and error paths
 *   • Missing HUBSPOT_ACCESS_TOKEN early-exit behaviour
 *
 * All outbound fetch calls are mocked — no real HTTP requests are made.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { syncCustomerToHubSpot } from '../../src/services/hubspot/companies.js';
import { CUSTOMER_TYPES } from '../../src/utils/constants.js';
import type { NormalizedCustomer } from '../../src/types/customer.js';

// ── Fixtures ───────────────────────────────────────────────────────────────

const baseCustomer: NormalizedCustomer = {
  customerId: 'ACME001',
  customerName: 'Acme Interiors LLC',
  customerType: CUSTOMER_TYPES.DESIGNER,
  email: 'orders@acme.com',
  phone: '212-555-0100',
};

// ── Helpers ────────────────────────────────────────────────────────────────

/**
 * Build a minimal Response-like object that fetch would return.
 * We deliberately avoid importing/extending the built-in Response to keep
 * the mock surface small and environment-agnostic.
 */
function makeFetchResponse(
  body: unknown,
  status = 200,
): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => JSON.stringify(body),
    json: async () => body,
  } as unknown as Response;
}

// ── Test suite ─────────────────────────────────────────────────────────────

describe('syncCustomerToHubSpot', () => {
  // Save and restore the real global fetch / env token around each test
  const originalFetch = global.fetch;
  const originalToken = process.env['HUBSPOT_ACCESS_TOKEN'];

  beforeEach(() => {
    process.env['HUBSPOT_ACCESS_TOKEN'] = 'test-token-abc123';
  });

  afterEach(() => {
    global.fetch = originalFetch;
    if (originalToken === undefined) {
      delete process.env['HUBSPOT_ACCESS_TOKEN'];
    } else {
      process.env['HUBSPOT_ACCESS_TOKEN'] = originalToken;
    }
    vi.restoreAllMocks();
  });

  // ── Token guard ────────────────────────────────────────────────────────

  it('returns failure when HUBSPOT_ACCESS_TOKEN is not set', async () => {
    delete process.env['HUBSPOT_ACCESS_TOKEN'];

    const result = await syncCustomerToHubSpot(baseCustomer);

    expect(result.success).toBe(false);
    expect(result.error).toMatch(/HUBSPOT_ACCESS_TOKEN/);
    expect(result.hubspotCompanyId).toBeUndefined();
  });

  // ── CREATE path ────────────────────────────────────────────────────────

  it('creates a new company when no existing record is found (search returns 0 results)', async () => {
    const searchResponse = makeFetchResponse({ results: [], total: 0 });
    const createResponse = makeFetchResponse(
      { id: 'hs-new-123', properties: {} },
      201,
    );

    // Search → no match; Create → new record
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(searchResponse)   // POST /companies/search
      .mockResolvedValueOnce(createResponse);  // POST /companies

    global.fetch = mockFetch;

    const result = await syncCustomerToHubSpot(baseCustomer);

    expect(result.success).toBe(true);
    expect(result.hubspotCompanyId).toBe('hs-new-123');

    // Verify search was called first
    expect(mockFetch).toHaveBeenCalledTimes(2);
    const [searchCall, createCall] = mockFetch.mock.calls as [
      [string, RequestInit],
      [string, RequestInit],
    ];

    expect(searchCall[0]).toContain('/companies/search');
    expect(searchCall[1].method).toBe('POST');

    expect(createCall[0]).toContain('/crm/v3/objects/companies');
    expect(createCall[1].method).toBe('POST');
  });

  it('sends correct properties on create — name, phone, email, customer_type, acumatica_customer_id', async () => {
    const searchResponse = makeFetchResponse({ results: [], total: 0 });
    const createResponse = makeFetchResponse({ id: 'hs-999', properties: {} }, 201);

    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(searchResponse)
      .mockResolvedValueOnce(createResponse);

    global.fetch = mockFetch;

    await syncCustomerToHubSpot(baseCustomer);

    const createCall = mockFetch.mock.calls[1] as [string, RequestInit];
    const sentBody = JSON.parse(createCall[1].body as string) as {
      properties: Record<string, string>;
    };

    expect(sentBody.properties.name).toBe('Acme Interiors LLC');
    expect(sentBody.properties.phone).toBe('212-555-0100');
    expect(sentBody.properties.email).toBe('orders@acme.com');
    expect(sentBody.properties.customer_type).toBe(CUSTOMER_TYPES.DESIGNER);
    expect(sentBody.properties.acumatica_customer_id).toBe('ACME001');
  });

  // ── UPDATE path ────────────────────────────────────────────────────────

  it('updates an existing company when search returns a matching record', async () => {
    const existingHubSpotId = 'hs-existing-456';
    const searchResponse = makeFetchResponse({
      results: [{ id: existingHubSpotId }],
      total: 1,
    });
    const updateResponse = makeFetchResponse(
      { id: existingHubSpotId, properties: {} },
    );

    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(searchResponse)   // POST /companies/search
      .mockResolvedValueOnce(updateResponse);  // PATCH /companies/:id

    global.fetch = mockFetch;

    const result = await syncCustomerToHubSpot(baseCustomer);

    expect(result.success).toBe(true);
    expect(result.hubspotCompanyId).toBe(existingHubSpotId);

    const updateCall = mockFetch.mock.calls[1] as [string, RequestInit];
    expect(updateCall[0]).toContain(`/companies/${existingHubSpotId}`);
    expect(updateCall[1].method).toBe('PATCH');
  });

  it('sends correct properties on update', async () => {
    const existingHubSpotId = 'hs-existing-789';
    const searchResponse = makeFetchResponse({
      results: [{ id: existingHubSpotId }],
      total: 1,
    });
    const updateResponse = makeFetchResponse({ id: existingHubSpotId, properties: {} });

    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(searchResponse)
      .mockResolvedValueOnce(updateResponse);

    global.fetch = mockFetch;

    await syncCustomerToHubSpot(baseCustomer);

    const updateCall = mockFetch.mock.calls[1] as [string, RequestInit];
    const sentBody = JSON.parse(updateCall[1].body as string) as {
      properties: Record<string, string>;
    };

    expect(sentBody.properties.name).toBe('Acme Interiors LLC');
    expect(sentBody.properties.acumatica_customer_id).toBe('ACME001');
  });

  // ── Search filter payload ──────────────────────────────────────────────

  it('searches by acumatica_customer_id with EQ operator', async () => {
    const searchResponse = makeFetchResponse({ results: [], total: 0 });
    const createResponse = makeFetchResponse({ id: 'hs-0', properties: {} }, 201);

    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(searchResponse)
      .mockResolvedValueOnce(createResponse);

    global.fetch = mockFetch;

    await syncCustomerToHubSpot(baseCustomer);

    const searchCall = mockFetch.mock.calls[0] as [string, RequestInit];
    const searchBody = JSON.parse(searchCall[1].body as string) as {
      filterGroups: Array<{
        filters: Array<{ propertyName: string; operator: string; value: string }>;
      }>;
    };

    const filter = searchBody.filterGroups[0]?.filters[0];
    expect(filter?.propertyName).toBe('acumatica_customer_id');
    expect(filter?.operator).toBe('EQ');
    expect(filter?.value).toBe('ACME001');
  });

  // ── Authorization header ───────────────────────────────────────────────

  it('sends Bearer token in Authorization header on all requests', async () => {
    const searchResponse = makeFetchResponse({ results: [], total: 0 });
    const createResponse = makeFetchResponse({ id: 'hs-auth-test', properties: {} }, 201);

    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(searchResponse)
      .mockResolvedValueOnce(createResponse);

    global.fetch = mockFetch;

    await syncCustomerToHubSpot(baseCustomer);

    for (const call of mockFetch.mock.calls as [string, RequestInit][]) {
      const headers = call[1].headers as Record<string, string>;
      expect(headers['Authorization']).toBe('Bearer test-token-abc123');
    }
  });

  // ── customer_type fallback ─────────────────────────────────────────────

  it('defaults customer_type to Other when customerType is falsy', async () => {
    const customerWithEmptyType: NormalizedCustomer = {
      ...baseCustomer,
      customerType: '' as typeof CUSTOMER_TYPES.OTHER,
    };

    const searchResponse = makeFetchResponse({ results: [], total: 0 });
    const createResponse = makeFetchResponse({ id: 'hs-fallback', properties: {} }, 201);

    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(searchResponse)
      .mockResolvedValueOnce(createResponse);

    global.fetch = mockFetch;

    await syncCustomerToHubSpot(customerWithEmptyType);

    const createCall = mockFetch.mock.calls[1] as [string, RequestInit];
    const sentBody = JSON.parse(createCall[1].body as string) as {
      properties: Record<string, string>;
    };

    expect(sentBody.properties.customer_type).toBe(CUSTOMER_TYPES.OTHER);
  });

  // ── All CustomerType values ────────────────────────────────────────────

  it.each([
    CUSTOMER_TYPES.RETAILER,
    CUSTOMER_TYPES.FINAL_CLIENT,
    CUSTOMER_TYPES.DESIGNER,
    CUSTOMER_TYPES.WHOLESALER,
    CUSTOMER_TYPES.OTHER,
  ])('passes customer_type "%s" through unchanged', async (customerType) => {
    const customer: NormalizedCustomer = { ...baseCustomer, customerType };

    const searchResponse = makeFetchResponse({ results: [], total: 0 });
    const createResponse = makeFetchResponse({ id: `hs-${customerType}`, properties: {} }, 201);

    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce(searchResponse)
      .mockResolvedValueOnce(createResponse);

    global.fetch = mockFetch;

    await syncCustomerToHubSpot(customer);

    const createCall = mockFetch.mock.calls[1] as [string, RequestInit];
    const sentBody = JSON.parse(createCall[1].body as string) as {
      properties: Record<string, string>;
    };

    expect(sentBody.properties.customer_type).toBe(customerType);
  });

  // ── Error handling ─────────────────────────────────────────────────────

  it('returns failure when the search API responds with a non-OK status', async () => {
    const errorResponse = makeFetchResponse({ message: 'Unauthorized' }, 401);

    global.fetch = vi.fn().mockResolvedValueOnce(errorResponse);

    const result = await syncCustomerToHubSpot(baseCustomer);

    expect(result.success).toBe(false);
    expect(result.error).toMatch(/401/);
    expect(result.hubspotCompanyId).toBeUndefined();
  });

  it('returns failure when the create API responds with a non-OK status', async () => {
    const searchResponse = makeFetchResponse({ results: [], total: 0 });
    const createErrorResponse = makeFetchResponse({ message: 'Bad Request' }, 400);

    global.fetch = vi
      .fn()
      .mockResolvedValueOnce(searchResponse)
      .mockResolvedValueOnce(createErrorResponse);

    const result = await syncCustomerToHubSpot(baseCustomer);

    expect(result.success).toBe(false);
    expect(result.error).toMatch(/400/);
    expect(result.hubspotCompanyId).toBeUndefined();
  });

  it('returns failure when the update API responds with a non-OK status', async () => {
    const searchResponse = makeFetchResponse({
      results: [{ id: 'hs-update-fail' }],
      total: 1,
    });
    const updateErrorResponse = makeFetchResponse({ message: 'Forbidden' }, 403);

    global.fetch = vi
      .fn()
      .mockResolvedValueOnce(searchResponse)
      .mockResolvedValueOnce(updateErrorResponse);

    const result = await syncCustomerToHubSpot(baseCustomer);

    expect(result.success).toBe(false);
    expect(result.error).toMatch(/403/);
    expect(result.hubspotCompanyId).toBeUndefined();
  });

  it('returns failure when fetch throws a network error', async () => {
    global.fetch = vi.fn().mockRejectedValueOnce(new Error('Network timeout'));

    const result = await syncCustomerToHubSpot(baseCustomer);

    expect(result.success).toBe(false);
    expect(result.error).toMatch(/Network timeout/);
  });

  it('captures unknown thrown values as a generic error message', async () => {
    global.fetch = vi.fn().mockRejectedValueOnce('string error, not an Error object');

    const result = await syncCustomerToHubSpot(baseCustomer);

    expect(result.success).toBe(false);
    expect(result.error).toMatch(/Unknown HubSpot sync error/);
  });
});
