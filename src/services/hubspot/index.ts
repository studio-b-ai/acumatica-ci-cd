/**
 * HubSpot service — public barrel export
 *
 * Re-exports the public surface of the HubSpot integration so consumers
 * can import from 'src/services/hubspot' without knowing the internal
 * file layout.
 *
 * Usage:
 *   import { syncCustomerToHubSpot } from '../../services/hubspot/index.js';
 */

export { syncCustomerToHubSpot } from './companies.js';
export type {
  HubSpotCompanyProperties,
  HubSpotCompanyResponse,
  HubSpotCreateCompanyRequest,
  HubSpotSyncResult,
} from './types.js';
