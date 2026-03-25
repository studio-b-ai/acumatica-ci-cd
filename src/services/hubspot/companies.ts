/**
 * HubSpot Companies service
 *
 * Responsible for syncing a NormalizedCustomer to the HubSpot Companies API.
 *
 * Sync strategy
 * ─────────────
 * HubSpot does not natively deduplicate companies by an external ID, so we
 * store the Acumatica CustomerID in a custom property (`acumatica_customer_id`)
 * and use the Search API to check for an existing record before deciding
 * whether to create or update.
 *
 * Environment variables required
 * ──────────────────────────────
 *   HUBSPOT_ACCESS_TOKEN – Private App access token from HubSpot Settings →
 *                          Integrations → Private Apps.
 *                          Scopes needed: crm.objects.companies.read
 *                                         crm.objects.companies.write
 *
 * HubSpot custom properties (manual setup required)
 * ──────────────────────────────────────────────────
 *   customer_type          – Dropdown select on Company object
 *     Options (label = internal value):
 *       Retailer | Final Client | Designer | Wholesaler | Other
 *   acumatica_customer_id  – Single-line text on Company object
 */

import { NormalizedCustomer } from '../../types/customer.js';
import { CUSTOMER_TYPES } from '../../utils/constants.js';
import {
  HubSpotCompanyProperties,
  HubSpotCompanyResponse,
  HubSpotCreateCompanyRequest,
  HubSpotSyncResult,
} from './types.js';

// ── Constants ──────────────────────────────────────────────────────────────

const HUBSPOT_API_BASE = 'https://api.hubapi.com';

// ── Internal helpers ───────────────────────────────────────────────────────

/**
 * Returns the Bearer token from the environment, throwing early if it is
 * absent so callers receive a clear error rather than a 401 from HubSpot.
 */
function getAccessToken(): string {
  const token = process.env['HUBSPOT_ACCESS_TOKEN'];
  if (!token) {
    throw new Error(
      'HUBSPOT_ACCESS_TOKEN environment variable is not set. ' +
        'Create a Private App in HubSpot and add the token to your environment.',
    );
  }
  return token;
}

/**
 * Builds the HubSpot company properties payload from a NormalizedCustomer.
 *
 * customer_type is mapped directly from customer.customerType — the value is
 * already one of the CUSTOMER_TYPES constants ('Retailer', 'Final Client',
 * etc.) which must match the HubSpot dropdown option internal values exactly.
 * If customerType is somehow falsy we fall back to 'Other' as a safe default.
 */
function buildCompanyProperties(
  customer: NormalizedCustomer,
): HubSpotCompanyProperties {
  return {
    name: customer.customerName,
    phone: customer.phone,
    email: customer.email,

    // ── Customer type (custom HubSpot dropdown property) ─────────────────
    // Maps the internally-classified CustomerType to the HubSpot dropdown.
    // The fallback to CUSTOMER_TYPES.OTHER guards against any edge case where
    // customerType is an unexpected value at runtime.
    customer_type: customer.customerType || CUSTOMER_TYPES.OTHER,

    // ── Acumatica ID (custom HubSpot text property) ───────────────────────
    acumatica_customer_id: customer.customerId,
  };
}

/**
 * Uses the HubSpot Search API to find an existing company whose
 * `acumatica_customer_id` matches the given Acumatica CustomerID.
 *
 * @returns The HubSpot record ID string if found, or null if not.
 */
async function findExistingCompany(
  customerId: string,
  accessToken: string,
): Promise<string | null> {
  const url = `${HUBSPOT_API_BASE}/crm/v3/objects/companies/search`;

  const body = {
    filterGroups: [
      {
        filters: [
          {
            propertyName: 'acumatica_customer_id',
            operator: 'EQ',
            value: customerId,
          },
        ],
      },
    ],
    properties: ['acumatica_customer_id'],
    limit: 1,
  };

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(
      `HubSpot search failed (${response.status}): ${text}`,
    );
  }

  const data = (await response.json()) as {
    results: Array<{ id: string }>;
    total: number;
  };

  if (data.total > 0 && data.results[0]) {
    return data.results[0].id;
  }

  return null;
}

/**
 * Creates a new HubSpot company record.
 *
 * @returns The newly created company's HubSpot record ID.
 */
async function createCompany(
  properties: HubSpotCompanyProperties,
  accessToken: string,
): Promise<string> {
  const url = `${HUBSPOT_API_BASE}/crm/v3/objects/companies`;

  const requestBody: HubSpotCreateCompanyRequest = { properties };

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(requestBody),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(
      `HubSpot create company failed (${response.status}): ${text}`,
    );
  }

  const data = (await response.json()) as HubSpotCompanyResponse;
  return data.id;
}

/**
 * Updates an existing HubSpot company record by its HubSpot record ID.
 *
 * @returns The same HubSpot record ID that was passed in.
 */
async function updateCompany(
  hubspotId: string,
  properties: HubSpotCompanyProperties,
  accessToken: string,
): Promise<string> {
  const url = `${HUBSPOT_API_BASE}/crm/v3/objects/companies/${hubspotId}`;

  const response = await fetch(url, {
    method: 'PATCH',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ properties }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(
      `HubSpot update company failed (${response.status}): ${text}`,
    );
  }

  return hubspotId;
}

// ── Public API ─────────────────────────────────────────────────────────────

/**
 * Upserts a NormalizedCustomer to HubSpot as a Company record.
 *
 * Flow:
 *  1. Build properties payload (includes customer_type and acumatica_customer_id)
 *  2. Search HubSpot for an existing company with matching acumatica_customer_id
 *  3. Update if found; create if not
 *  4. Return a HubSpotSyncResult indicating success or failure
 *
 * @param customer - The normalized customer produced by transformCustomer().
 * @returns Promise<HubSpotSyncResult>
 */
export async function syncCustomerToHubSpot(
  customer: NormalizedCustomer,
): Promise<HubSpotSyncResult> {
  try {
    const accessToken = getAccessToken();

    // ── 1. Build properties ──────────────────────────────────────────────
    const properties = buildCompanyProperties(customer);

    // ── 2. Check for existing record ─────────────────────────────────────
    const existingId = await findExistingCompany(
      customer.customerId,
      accessToken,
    );

    // ── 3. Create or update ──────────────────────────────────────────────
    const hubspotCompanyId =
      existingId !== null
        ? await updateCompany(existingId, properties, accessToken)
        : await createCompany(properties, accessToken);

    // ── 4. Return success ────────────────────────────────────────────────
    return { success: true, hubspotCompanyId };
  } catch (err) {
    const error =
      err instanceof Error ? err.message : 'Unknown HubSpot sync error';
    return { success: false, error };
  }
}
