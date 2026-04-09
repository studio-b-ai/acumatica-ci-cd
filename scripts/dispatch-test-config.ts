/**
 * GitHub repository_dispatch helper for auto-adding Playwright test config entries.
 *
 * Drop this file into any service (webhook-router, acumatica-ci-cd) and call
 * the appropriate function after creating HubSpot properties, pipelines, or
 * Acumatica custom fields.
 *
 * Auth: acuops-agent GitHub App (App ID 3316941, Installation ID 122409174).
 * Requires env vars:
 *   - ACUOPS_AGENT_APP_ID
 *   - ACUOPS_AGENT_INSTALLATION_ID
 *   - ACUOPS_AGENT_PRIVATE_KEY (RSA PEM)
 *
 * The acuops-agent identity replaces GH_PAT_DISPATCH (Kevin's PAT) so audit
 * logs show acuops-agent[bot] instead of a human user. See plan doc:
 * docs/plans/2026-04-08-acuops-agent-github-app-setup.md
 *
 * Target: studio-b-ai/ui-test-suite → update-test-configs.yml workflow
 */

import { createSign } from 'node:crypto';

const GITHUB_API = 'https://api.github.com';
const TARGET_REPO = 'studio-b-ai/ui-test-suite';

// Cached installation token (re-minted per process; tokens are valid ~1h)
let cachedToken: { token: string; expiresAt: number } | null = null;

/**
 * Mint or return a cached acuops-agent installation token.
 * Returns null if any required env var is missing.
 */
async function getAcuopsAgentToken(): Promise<string | null> {
  // Return cached token if it's still valid (5-minute safety buffer)
  if (cachedToken && cachedToken.expiresAt - 5 * 60 * 1000 > Date.now()) {
    return cachedToken.token;
  }

  const appId = process.env.ACUOPS_AGENT_APP_ID;
  const installationId = process.env.ACUOPS_AGENT_INSTALLATION_ID;
  const privateKey = process.env.ACUOPS_AGENT_PRIVATE_KEY;

  if (!appId || !installationId || !privateKey) {
    return null;
  }

  // Build JWT (RS256, max lifetime per GitHub: 10 minutes)
  const now = Math.floor(Date.now() / 1000);
  const header = Buffer.from(JSON.stringify({ alg: 'RS256', typ: 'JWT' })).toString('base64url');
  const payload = Buffer.from(
    JSON.stringify({ iat: now - 60, exp: now + 9 * 60, iss: appId }),
  ).toString('base64url');
  const signingInput = `${header}.${payload}`;
  const signer = createSign('RSA-SHA256');
  signer.update(signingInput);
  const signature = signer.sign(privateKey).toString('base64url');
  const jwt = `${signingInput}.${signature}`;

  // Exchange JWT for an installation access token
  const tokenRes = await fetch(
    `${GITHUB_API}/app/installations/${installationId}/access_tokens`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${jwt}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
      },
    },
  );

  if (!tokenRes.ok) {
    console.error(
      `[dispatch-test-config] acuops-agent token mint failed: HTTP ${tokenRes.status} ${await tokenRes.text()}`,
    );
    return null;
  }

  const data = (await tokenRes.json()) as { token: string; expires_at: string };
  cachedToken = { token: data.token, expiresAt: new Date(data.expires_at).getTime() };
  return data.token;
}

async function dispatch(command: string, args: string): Promise<boolean> {
  const token = await getAcuopsAgentToken();
  if (!token) {
    console.warn(
      '[dispatch-test-config] acuops-agent env vars not set (ACUOPS_AGENT_APP_ID / ACUOPS_AGENT_INSTALLATION_ID / ACUOPS_AGENT_PRIVATE_KEY) — skipping test config dispatch',
    );
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
