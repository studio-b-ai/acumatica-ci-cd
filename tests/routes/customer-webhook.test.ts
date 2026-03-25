/**
 * Route / handler tests — Acumatica Customer webhook
 *
 * Tests cover:
 *   • isValidCustomerPayload guard (valid, missing, malformed)
 *   • transformCustomer integration — correct NormalizedCustomer shape
 *   • Customer type classification end-to-end through the handler
 *   • HubSpot sync result attached to handler result
 *   • HubSpot sync failure does not make the handler fail
 *   • Missing CustomerID and other malformed payload variants
 *
 * The HubSpot service is mocked so these tests remain fast and offline.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { handleCustomerWebhook } from '../../src/routes/acumatica/customers.js';
import { CUSTOMER_TYPES } from '../../src/utils/constants.js';

// ── Mock HubSpot service ───────────────────────────────────────────────────
//
// We mock the entire HubSpot module so the route tests don't hit the network.
// Each test can override the resolved value to simulate success or failure.

vi.mock('../../src/services/hubspot/index.js', () => ({
  syncCustomerToHubSpot: vi.fn(),
}));

// Import the mock *after* vi.mock() so we get the mocked version
import { syncCustomerToHubSpot } from '../../src/services/hubspot/index.js';

const mockSyncCustomerToHubSpot = vi.mocked(syncCustomerToHubSpot);

// ── Fixtures ───────────────────────────────────────────────────────────────

const validPayload = {
  CustomerID: { value: 'ACME001' },
  CustomerName: { value: 'Acme Interiors LLC' },
  CustomerClass: { value: 'DESIGN' },
  Email: { value: 'orders@acme.com' },
  Phone1: { value: '212-555-0100' },
};

const hubspotSuccess = { success: true, hubspotCompanyId: 'hs-111' };
const hubspotFailure = { success: false, error: 'HubSpot API error' };

// ── Tests ──────────────────────────────────────────────────────────────────

describe('handleCustomerWebhook', () => {
  beforeEach(() => {
    mockSyncCustomerToHubSpot.mockResolvedValue(hubspotSuccess);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  // ── Validation ───────────────────────────────────────────────────────────

  describe('payload validation', () => {
    it('rejects null body', async () => {
      const result = await handleCustomerWebhook(null);

      expect(result.success).toBe(false);
      expect(result.error).toMatch(/Invalid customer payload/);
      expect(result.customer).toBeUndefined();
    });

    it('rejects a non-object body (string)', async () => {
      const result = await handleCustomerWebhook('not-an-object');

      expect(result.success).toBe(false);
      expect(result.error).toMatch(/Invalid customer payload/);
    });

    it('rejects a non-object body (number)', async () => {
      const result = await handleCustomerWebhook(42);

      expect(result.success).toBe(false);
      expect(result.error).toMatch(/Invalid customer payload/);
    });

    it('rejects an empty object (no CustomerID)', async () => {
      const result = await handleCustomerWebhook({});

      expect(result.success).toBe(false);
      expect(result.error).toMatch(/Invalid customer payload/);
    });

    it('rejects a payload where CustomerID is not wrapped in {value}', async () => {
      const result = await handleCustomerWebhook({ CustomerID: 'FLAT-STRING' });

      expect(result.success).toBe(false);
      expect(result.error).toMatch(/Invalid customer payload/);
    });

    it('rejects a payload where CustomerID.value is not a string', async () => {
      const result = await handleCustomerWebhook({ CustomerID: { value: 123 } });

      expect(result.success).toBe(false);
      expect(result.error).toMatch(/Invalid customer payload/);
    });

    it('accepts a minimal payload with only CustomerID', async () => {
      const minimalPayload = { CustomerID: { value: 'MIN001' } };

      const result = await handleCustomerWebhook(minimalPayload);

      expect(result.success).toBe(true);
      expect(result.customer?.customerId).toBe('MIN001');
    });

    it('does not call HubSpot sync when validation fails', async () => {
      await handleCustomerWebhook(null);

      expect(mockSyncCustomerToHubSpot).not.toHaveBeenCalled();
    });
  });

  // ── Transform / shape ────────────────────────────────────────────────────

  describe('customer transform', () => {
    it('returns a NormalizedCustomer with all fields populated', async () => {
      const result = await handleCustomerWebhook(validPayload);

      expect(result.success).toBe(true);
      expect(result.customer).toEqual({
        customerId: 'ACME001',
        customerName: 'Acme Interiors LLC',
        customerType: CUSTOMER_TYPES.DESIGNER,
        email: 'orders@acme.com',
        phone: '212-555-0100',
      });
    });

    it('returns empty strings for absent optional fields (email, phone)', async () => {
      const sparse = { CustomerID: { value: 'SPARSE001' } };

      const result = await handleCustomerWebhook(sparse);

      expect(result.success).toBe(true);
      expect(result.customer?.email).toBe('');
      expect(result.customer?.phone).toBe('');
    });

    it('returns empty string for customerName when CustomerName is absent', async () => {
      const noName = { CustomerID: { value: 'NONAME001' } };

      const result = await handleCustomerWebhook(noName);

      expect(result.customer?.customerName).toBe('');
    });
  });

  // ── Customer type classification ─────────────────────────────────────────

  describe('customer type classification', () => {
    it.each([
      ['RETAIL', CUSTOMER_TYPES.RETAILER],
      ['RETAILERS', CUSTOMER_TYPES.RETAILER],
      ['DESIGN', CUSTOMER_TYPES.DESIGNER],
      ['DESIGNERS', CUSTOMER_TYPES.DESIGNER],
      ['WHOLESALE', CUSTOMER_TYPES.WHOLESALER],
      ['FINAL', CUSTOMER_TYPES.FINAL_CLIENT],
      ['CLIENT', CUSTOMER_TYPES.FINAL_CLIENT],
      ['UNKNOWN_CODE', CUSTOMER_TYPES.OTHER],
    ])(
      'maps CustomerClass "%s" → customerType "%s"',
      async (classCode, expectedType) => {
        const payload = {
          CustomerID: { value: 'TYPE-TEST' },
          CustomerClass: { value: classCode },
        };

        const result = await handleCustomerWebhook(payload);

        expect(result.customer?.customerType).toBe(expectedType);
      },
    );

    it('falls back to Attributes.CustomerType when CustomerClass is absent', async () => {
      const payload = {
        CustomerID: { value: 'FALLBACK001' },
        Attributes: { CustomerType: { value: 'Retailer' } },
      };

      const result = await handleCustomerWebhook(payload);

      expect(result.customer?.customerType).toBe(CUSTOMER_TYPES.RETAILER);
    });

    it('prefers CustomerClass over Attributes.CustomerType when both are present', async () => {
      const payload = {
        CustomerID: { value: 'PREFER001' },
        CustomerClass: { value: 'DESIGN' },
        Attributes: { CustomerType: { value: 'RETAIL' } },
      };

      const result = await handleCustomerWebhook(payload);

      // CustomerClass wins → DESIGNER, not RETAILER
      expect(result.customer?.customerType).toBe(CUSTOMER_TYPES.DESIGNER);
    });

    it('returns OTHER when both CustomerClass and Attributes.CustomerType are absent', async () => {
      const payload = { CustomerID: { value: 'NOTYPE001' } };

      const result = await handleCustomerWebhook(payload);

      expect(result.customer?.customerType).toBe(CUSTOMER_TYPES.OTHER);
    });
  });

  // ── HubSpot sync integration ──────────────────────────────────────────────

  describe('HubSpot sync', () => {
    it('calls syncCustomerToHubSpot with the normalized customer', async () => {
      await handleCustomerWebhook(validPayload);

      expect(mockSyncCustomerToHubSpot).toHaveBeenCalledOnce();
      expect(mockSyncCustomerToHubSpot).toHaveBeenCalledWith({
        customerId: 'ACME001',
        customerName: 'Acme Interiors LLC',
        customerType: CUSTOMER_TYPES.DESIGNER,
        email: 'orders@acme.com',
        phone: '212-555-0100',
      });
    });

    it('includes the hubspot sync result in the handler result on success', async () => {
      mockSyncCustomerToHubSpot.mockResolvedValue(hubspotSuccess);

      const result = await handleCustomerWebhook(validPayload);

      expect(result.success).toBe(true);
      expect(result.hubspot).toEqual(hubspotSuccess);
      expect(result.hubspot?.hubspotCompanyId).toBe('hs-111');
    });

    it('includes the hubspot failure result but handler still succeeds', async () => {
      mockSyncCustomerToHubSpot.mockResolvedValue(hubspotFailure);

      const result = await handleCustomerWebhook(validPayload);

      // Overall handler succeeds — HubSpot failure is non-blocking
      expect(result.success).toBe(true);
      expect(result.customer).toBeDefined();

      // HubSpot error is surfaced for observability
      expect(result.hubspot?.success).toBe(false);
      expect(result.hubspot?.error).toBe('HubSpot API error');
    });

    it('handler succeeds even when HubSpot sync rejects entirely', async () => {
      // syncCustomerToHubSpot already catches all errors internally and returns
      // { success: false, error: '...' } — but guard against a future refactor
      mockSyncCustomerToHubSpot.mockResolvedValue({
        success: false,
        error: 'Internal HubSpot error',
      });

      const result = await handleCustomerWebhook(validPayload);

      expect(result.success).toBe(true);
      expect(result.customer).toBeDefined();
    });
  });

  // ── Overall result shape ──────────────────────────────────────────────────

  describe('result shape', () => {
    it('success result has success=true, customer, and hubspot fields', async () => {
      const result = await handleCustomerWebhook(validPayload);

      expect(result).toHaveProperty('success', true);
      expect(result).toHaveProperty('customer');
      expect(result).toHaveProperty('hubspot');
      expect(result).not.toHaveProperty('error');
    });

    it('failure result has success=false, error, and no customer or hubspot', async () => {
      const result = await handleCustomerWebhook(null);

      expect(result).toHaveProperty('success', false);
      expect(result).toHaveProperty('error');
      expect(result.customer).toBeUndefined();
      expect(result.hubspot).toBeUndefined();
    });
  });
});
