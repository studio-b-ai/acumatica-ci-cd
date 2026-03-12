/**
 * GitHub repository_dispatch helper for auto-adding Playwright test config entries.
 *
 * Drop this file into any service (webhook-router, acumatica-ci-cd) and call
 * the appropriate function after creating HubSpot properties, pipelines, or
 * Acumatica custom fields.
 *
 * Requires: GH_PAT_DISPATCH env var (GitHub PAT with `repo` scope)
 * Target: studio-b-ai/heritage-wms → update-test-configs.yml workflow
 */

const GITHUB_API = 'https://api.github.com';
const TARGET_REPO = 'studio-b-ai/heritage-wms';

async function dispatch(command: string, args: string): Promise<boolean> {
  const token = process.env.GH_PAT_DISPATCH;
  if (!token) {
    console.warn('[dispatch-test-config] GH_PAT_DISPATCH not set — skipping test config dispatch');
    return false;
  }

  try {
    const res = await fetch(`${GITHUB_API}/repos/${TARGET_REPO}/dispatches`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/vnd.github+json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        event_type: 'add-test-config',
        client_payload: { command, args },
      }),
    });

    if (res.status === 204) {
      console.log(`[dispatch-test-config] Dispatched: ${command} ${args}`);
      return true;
    }

    console.error(`[dispatch-test-config] GitHub API returned ${res.status}: ${await res.text()}`);
    return false;
  } catch (err) {
    console.error('[dispatch-test-config] Dispatch failed:', err);
    return false;
  }
}

// ── Public API ─────────────────────────────────────────────────────────────────

/**
 * Call after creating a HubSpot property via the CRM v3 API.
 *
 * @param objectType - HubSpot object type (deals, companies, contacts, tickets, line_items)
 * @param propertyName - Internal property name (e.g., 'acumatica_warehouse')
 * @param label - Display label (e.g., 'Warehouse')
 * @param acumaticaSource - Acumatica field this maps from (e.g., 'WarehouseID')
 */
export async function dispatchSyncProperty(
  objectType: string,
  propertyName: string,
  label: string,
  acumaticaSource: string,
): Promise<boolean> {
  return dispatch(
    'add-sync-property',
    `--objectType ${objectType} --propertyName ${propertyName} --label "${label}" --acumaticaSource "${acumaticaSource}"`,
  );
}

/**
 * Call after creating a HubSpot pipeline via the Pipelines API.
 *
 * @param name - Pipeline display name
 * @param pipelineId - HubSpot pipeline ID (returned from create API)
 * @param objectType - HubSpot object type (deals, tickets, '0-970')
 * @param stages - Array of {label, stageId} from the created pipeline
 */
export async function dispatchPipeline(
  name: string,
  pipelineId: string,
  objectType: string,
  stages: { label: string; stageId: string }[],
): Promise<boolean> {
  return dispatch(
    'add-pipeline',
    `--name "${name}" --pipelineId ${pipelineId} --objectType ${objectType} --stages '${JSON.stringify(stages)}'`,
  );
}

/**
 * Call after deploying an Acumatica customization project with new UDFs.
 *
 * @param entity - Acumatica entity name (e.g., 'SalesOrder')
 * @param path - Field path (e.g., 'custom.Document.UsrNewField')
 * @param label - Human-readable label
 * @param fieldType - 'inline' for custom.View.Field, 'attribute' for Attributes[]
 */
export async function dispatchCustomField(
  entity: string,
  path: string,
  label: string,
  fieldType: 'inline' | 'attribute',
): Promise<boolean> {
  return dispatch(
    'add-custom-field',
    `--entity ${entity} --path "${path}" --label "${label}" --fieldType ${fieldType}`,
  );
}
