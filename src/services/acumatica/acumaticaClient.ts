/**
 * Acumatica REST API client with cookie-based session management.
 *
 * Auth pattern mirrors server.py (login → cookie session → logout) and
 * entity-sync.py (AcumaticaEntityClient), adapted for TypeScript/Node.
 *
 * Environment variables (all read from process.env):
 *   ACUMATICA_BASE_URL   — e.g. https://heritagefabrics.acumatica.com
 *   ACUMATICA_USERNAME   — API user
 *   ACUMATICA_PASSWORD   — API password
 *   ACUMATICA_COMPANY    — Tenant / company name (default: "Heritage Fabrics")
 *   ACUMATICA_ENDPOINT   — REST endpoint name (default: "default")
 *   ACUMATICA_VERSION    — Endpoint version (default: "24.200.001")
 */

import https from 'node:https';
import http from 'node:http';
import { URL } from 'node:url';

// ── Config ────────────────────────────────────────────────────────────────────

export const ACUMATICA_BASE_URL: string =
  (process.env.ACUMATICA_BASE_URL ?? 'https://heritagefabrics.acumatica.com').replace(/\/$/, '');

const USERNAME: string = process.env.ACUMATICA_USERNAME ?? '';
const PASSWORD: string = process.env.ACUMATICA_PASSWORD ?? '';
const COMPANY: string = process.env.ACUMATICA_COMPANY ?? 'Heritage Fabrics';
const ENDPOINT: string = process.env.ACUMATICA_ENDPOINT ?? 'default';
const VERSION: string = process.env.ACUMATICA_VERSION ?? '24.200.001';

export const API_BASE: string = `${ACUMATICA_BASE_URL}/entity/${ENDPOINT}/${VERSION}`;

// ── Cookie jar (in-process singleton — same pattern as server.py _session) ───

let _sessionCookies: string[] = [];
let _authenticated = false;

/** Clear the stored session cookies (used on logout or re-auth). */
function clearSession(): void {
  _sessionCookies = [];
  _authenticated = false;
}

/** Merge Set-Cookie headers into the cookie jar. */
function storeCookies(setCookieHeaders: string | string[] | undefined): void {
  if (!setCookieHeaders) return;
  const incoming = Array.isArray(setCookieHeaders)
    ? setCookieHeaders
    : [setCookieHeaders];
  for (const raw of incoming) {
    // Store only the key=value portion (strip Path/Expires/etc.)
    const kv = (raw.split(';')[0] ?? '').trim();
    if (!kv) continue;
    const name = kv.split('=')[0] ?? '';
    // Replace existing cookie with same name
    const idx = _sessionCookies.findIndex((c) => c.startsWith(name + '='));
    if (idx >= 0) {
      _sessionCookies.splice(idx, 1, kv);
    } else {
      _sessionCookies.push(kv);
    }
  }
}

/** Build the Cookie header string from stored cookies. */
function buildCookieHeader(): string {
  return _sessionCookies.join('; ');
}

// ── Core HTTP helper ──────────────────────────────────────────────────────────

interface RequestOptions {
  method: 'GET' | 'POST' | 'PUT' | 'DELETE';
  url: string;
  body?: unknown;
  timeoutMs?: number;
}

interface RawResponse {
  status: number;
  headers: http.IncomingHttpHeaders;
  body: string;
}

/** Low-level HTTP request using Node's built-in http/https modules (no deps). */
function rawRequest(opts: RequestOptions): Promise<RawResponse> {
  return new Promise((resolve, reject) => {
    const parsed = new URL(opts.url);
    const isHttps = parsed.protocol === 'https:';
    const bodyStr = opts.body !== undefined ? JSON.stringify(opts.body) : undefined;

    const reqOpts: http.RequestOptions = {
      hostname: parsed.hostname,
      port: parsed.port || (isHttps ? 443 : 80),
      path: parsed.pathname + parsed.search,
      method: opts.method,
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        ...(bodyStr ? { 'Content-Length': Buffer.byteLength(bodyStr).toString() } : {}),
        ...(buildCookieHeader() ? { Cookie: buildCookieHeader() } : {}),
      },
    };

    const transport = isHttps ? https : http;
    const req = transport.request(reqOpts, (res: http.IncomingMessage) => {
      storeCookies(res.headers['set-cookie']);
      let data = '';
      res.on('data', (chunk: Buffer | string) => (data += chunk.toString()));
      res.on('end', () =>
        resolve({ status: res.statusCode ?? 0, headers: res.headers, body: data }),
      );
    });

    req.on('error', reject);
    if (opts.timeoutMs) req.setTimeout(opts.timeoutMs, () => req.destroy(new Error('Request timed out')));
    if (bodyStr) req.write(bodyStr);
    req.end();
  });
}

// ── Auth ──────────────────────────────────────────────────────────────────────

/**
 * Authenticate against Acumatica and store the session cookie.
 * Idempotent — skips if already authenticated.
 * Matches server.py get_session() / entity-sync.py AcumaticaEntityClient.login()
 */
export async function ensureAuthenticated(): Promise<void> {
  if (_authenticated) return;

  if (!USERNAME || !PASSWORD) {
    throw new Error(
      'Acumatica credentials missing. Set ACUMATICA_USERNAME and ACUMATICA_PASSWORD env vars.',
    );
  }

  const res = await rawRequest({
    method: 'POST',
    url: `${ACUMATICA_BASE_URL}/entity/auth/login`,
    body: { name: USERNAME, password: PASSWORD, company: COMPANY },
    timeoutMs: 30_000,
  });

  if (res.status !== 204) {
    throw new Error(
      `Acumatica login failed (HTTP ${res.status}): ${res.body.slice(0, 300)}`,
    );
  }

  _authenticated = true;
}

/**
 * Log out and clear the session.
 * Mirrors server.py / entity-sync.py logout() — best-effort (ignores errors).
 */
export async function logout(): Promise<void> {
  if (!_authenticated) return;
  try {
    await rawRequest({
      method: 'POST',
      url: `${ACUMATICA_BASE_URL}/entity/auth/logout`,
      timeoutMs: 15_000,
    });
  } catch {
    // Logout failure is non-fatal — session will expire server-side
  } finally {
    clearSession();
  }
}

// ── Public API wrappers ───────────────────────────────────────────────────────

/**
 * GET from the Acumatica entity API.
 * Auto-authenticates if needed. Throws on non-2xx.
 *
 * @param entityPath - Relative path under API_BASE (e.g. "SalesOrder")
 * @param params     - Query string parameters
 */
export async function acumaticaGet<T = unknown>(
  entityPath: string,
  params?: Record<string, string>,
): Promise<T> {
  await ensureAuthenticated();

  const url = new URL(`${API_BASE}/${entityPath.replace(/^\//, '')}`);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      url.searchParams.set(k, v);
    }
  }

  const res = await rawRequest({ method: 'GET', url: url.toString(), timeoutMs: 60_000 });

  if (res.status === 401) {
    // Session expired — re-authenticate once and retry
    clearSession();
    await ensureAuthenticated();
    const retry = await rawRequest({ method: 'GET', url: url.toString(), timeoutMs: 60_000 });
    if (retry.status < 200 || retry.status >= 300) {
      throw new Error(
        `Acumatica GET ${entityPath} failed after re-auth (HTTP ${retry.status}): ${retry.body.slice(0, 300)}`,
      );
    }
    return retry.body ? (JSON.parse(retry.body) as T) : ({} as T);
  }

  if (res.status < 200 || res.status >= 300) {
    throw new Error(
      `Acumatica GET ${entityPath} failed (HTTP ${res.status}): ${res.body.slice(0, 300)}`,
    );
  }

  return res.body ? (JSON.parse(res.body) as T) : ({} as T);
}
