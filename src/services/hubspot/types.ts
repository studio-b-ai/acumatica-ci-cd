/**
 * HubSpot service types
 *
 * Defines the TypeScript interfaces for data sent to HubSpot via the
 * Companies API.  Every field listed here must exist as a property in the
 * target HubSpot portal; custom properties (e.g. customer_type) must be
 * created manually in HubSpot Settings → Properties → Company Properties
 * before they can receive data.
 */

import { CustomerType } from '../../utils/constants.js';

// ── Company properties payload ─────────────────────────────────────────────

/**
 * Properties sent to the HubSpot Companies API when creating or updating a
 * company record.
 *
 * Native HubSpot properties:
 *   name    – company display name (built-in)
 *   phone   – primary phone (built-in)
 *   email   – contact email (built-in; stored on the company object here for
 *             simplicity; a separate Contact record may also be warranted)
 *
 * Custom HubSpot properties (must be created manually in HubSpot):
 *   customer_type – dropdown property on the Company object.
 *     Internal name : customer_type
 *     Field type    : Dropdown select
 *     Options (label = internal value):
 *       Retailer | Final Client | Designer | Wholesaler | Other
 *
 *   acumatica_customer_id – single-line text; stores the Acumatica CustomerID
 *     so records can be de-duplicated / looked up across syncs.
 */
export interface HubSpotCompanyProperties {
  /** Company display name — maps to HubSpot built-in "name" property */
  name: string;

  /** Primary phone number — maps to HubSpot built-in "phone" property */
  phone: string;

  /** Contact email — maps to HubSpot built-in "email" property */
  email: string;

  /**
   * Customer classification derived from the Acumatica CustomerClass /
   * Attributes.CustomerType field.
   *
   * Maps to the HubSpot *custom* dropdown property "customer_type".
   * Allowed values (must match HubSpot option internal values exactly):
   *   'Retailer' | 'Final Client' | 'Designer' | 'Wholesaler' | 'Other'
   *
   * Manual setup required in HubSpot:
   *   Settings → Properties → Company Properties → Create Property
   *   Internal name: customer_type  |  Field type: Dropdown select
   */
  customer_type: CustomerType;

  /**
   * Acumatica CustomerID stored on the HubSpot company for cross-system
   * de-duplication.
   *
   * Maps to the HubSpot *custom* single-line text property
   * "acumatica_customer_id".
   */
  acumatica_customer_id: string;
}

// ── HubSpot API request / response shapes ─────────────────────────────────

/** Request body sent to POST /crm/v3/objects/companies */
export interface HubSpotCreateCompanyRequest {
  properties: HubSpotCompanyProperties;
}

/**
 * Minimal shape of the HubSpot API response for a company create/update.
 * The actual response contains many more fields; we only type what we use.
 */
export interface HubSpotCompanyResponse {
  /** HubSpot internal record ID (numeric string) */
  id: string;
  properties: HubSpotCompanyProperties;
}

/** Outcome returned by our HubSpot service layer to the calling handler */
export interface HubSpotSyncResult {
  success: boolean;
  /** HubSpot record ID when the upsert succeeded */
  hubspotCompanyId?: string;
  error?: string;
}
