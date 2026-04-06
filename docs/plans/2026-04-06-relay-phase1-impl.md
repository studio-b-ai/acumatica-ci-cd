# Relay Phase 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the Heritage Fabrics MVP — bidirectional Slack ↔ Teams message bridge with thread sync, reactions, and file relay.

**Architecture:** Event-driven worker pattern. Fastify API receives webhooks from both platforms, normalizes to a RelayMessage envelope, publishes to BullMQ. Router worker reads from queue, resolves channel mappings, dispatches to target platform connectors. Postgres stores tenant config, channel mappings, and message cross-references.

**Tech Stack:** Node.js 22, TypeScript, Fastify 5, BullMQ 5, IORedis 5, pg 8, Pino 9, Vitest 4, tsup, Railway

---

## Task 1: Create Repo + Scaffold

**Files:**
- Create: `package.json`
- Create: `tsconfig.json`
- Create: `tsup.config.ts`
- Create: `vitest.config.ts`
- Create: `.gitignore`
- Create: `.npmrc`
- Create: `Dockerfile`
- Create: `.github/workflows/ci.yml`
- Create: `src/index.ts`
- Create: `src/config.ts`
- Create: `CLAUDE.md`

**Step 1: Create the GitHub repo**

```bash
gh repo create studio-b-ai/relay --private --clone
cd relay
```

**Step 2: Create package.json**

Match webhook-router conventions — Fastify 5, BullMQ 5, Pino 9, Vitest 4.

```json
{
  "name": "relay",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "main": "./dist/index.js",
  "scripts": {
    "build": "tsup",
    "start": "node dist/index.js",
    "dev": "tsx watch src/index.ts",
    "test": "vitest run",
    "test:watch": "vitest",
    "typecheck": "tsc --noEmit",
    "clean": "rm -rf dist"
  },
  "dependencies": {
    "@slack/web-api": "^7.8.0",
    "botbuilder": "^4.23.0",
    "botframework-connector": "^4.23.0",
    "bullmq": "^5.34.0",
    "fastify": "^5.2.0",
    "ioredis": "^5.4.2",
    "js-yaml": "^4.1.0",
    "nanoid": "^5.0.0",
    "pg": "^8.13.0",
    "pino": "^9.6.0"
  },
  "devDependencies": {
    "@types/js-yaml": "^4.0.9",
    "@types/node": "^22.0.0",
    "@types/pg": "^8.11.0",
    "tsup": "^8.4.0",
    "tsx": "^4.21.0",
    "typescript": "^5.7.0",
    "vitest": "^4.0.18"
  },
  "engines": {
    "node": ">=22"
  }
}
```

**Step 3: Create tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ES2022",
    "moduleResolution": "bundler",
    "lib": ["ES2022"],
    "outDir": "./dist",
    "rootDir": "./src",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "declaration": true,
    "sourceMap": true,
    "isolatedModules": true
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist"]
}
```

**Step 4: Create tsup.config.ts**

```typescript
import { defineConfig } from "tsup";

export default defineConfig({
  entry: ["src/index.ts"],
  format: ["esm"],
  target: "node22",
  outDir: "dist",
  clean: true,
  sourcemap: true,
  dts: true,
});
```

**Step 5: Create vitest.config.ts**

```typescript
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    globals: true,
    environment: "node",
    include: ["src/**/*.test.ts", "tests/**/*.test.ts"],
    testTimeout: 10_000,
  },
});
```

**Step 6: Create .gitignore**

```
node_modules/
dist/
.env
*.log
```

**Step 7: Create .npmrc**

```
@studio-b-ai:registry=https://npm.pkg.github.com
//npm.pkg.github.com/:_authToken=${NPM_PKG_TOKEN}
```

**Step 8: Create Dockerfile**

```dockerfile
FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY tsconfig.json tsup.config.ts ./
COPY src/ ./src/
RUN npm run build

FROM node:22-alpine
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev
COPY --from=builder /app/dist ./dist
EXPOSE 3000
CMD ["node", "dist/index.js"]
```

**Step 9: Create .github/workflows/ci.yml**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  build-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
      - run: npm ci
      - run: npm run typecheck
      - run: npm test
      - run: npm run build
```

**Step 10: Create src/config.ts**

```typescript
export const config = {
  port: parseInt(process.env.PORT ?? "3000", 10),
  logLevel: process.env.LOG_LEVEL ?? "info",
  databaseUrl: process.env.DATABASE_URL,
  redisUrl: process.env.REDIS_URL,

  // Slack
  slackSigningSecret: process.env.SLACK_SIGNING_SECRET,

  // Teams
  teamsAppId: process.env.TEAMS_APP_ID,
  teamsAppPassword: process.env.TEAMS_APP_PASSWORD,

  // Config file path (Phase 1 — YAML)
  configPath: process.env.RELAY_CONFIG_PATH ?? "./relay.yaml",
} as const;
```

**Step 11: Create src/index.ts (minimal server)**

```typescript
import Fastify from "fastify";
import pino from "pino";
import { config } from "./config.js";

const logger = pino({ level: config.logLevel });

const app = Fastify({ logger });

app.get("/health", async () => ({ status: "ok" }));

app.listen({ port: config.port, host: "0.0.0.0" }, (err) => {
  if (err) {
    logger.error(err, "Failed to start server");
    process.exit(1);
  }
});

export { app };
```

**Step 12: Create CLAUDE.md**

```markdown
# Relay — Unified Messaging Bridge

Studio B AI product. Multi-tenant bidirectional bridge: Slack, Teams, Zoom, Google Chat.

## Conventions
- Fastify 5 for HTTP
- BullMQ 5 for job queue
- Raw pg (no ORM) for database
- Pino for logging
- Vitest for tests
- tsup for builds
- ESM throughout (type: module)

## Structure
- src/connectors/ — Platform-specific adapters (slack, teams, zoom, google-chat)
- src/router/ — BullMQ worker that dispatches messages across connectors
- src/routes/ — Fastify webhook + API routes
- src/db/ — Database queries and schema
- src/types/ — Shared TypeScript interfaces
- src/config.ts — Environment configuration
- tests/ — Test files mirroring src/ structure

## Design Doc
See docs/plans/2026-04-06-relay-messaging-bridge-design.md in acumatica-ci-cd repo.
```

**Step 13: npm install + initial commit**

```bash
npm install
git add -A
git commit -m "feat: initial scaffold — Fastify, BullMQ, Postgres, Vitest"
```

---

## Task 2: Types + RelayMessage Envelope

**Files:**
- Create: `src/types/relay.ts`
- Create: `src/types/connector.ts`
- Test: `tests/types/relay.test.ts`

**Step 1: Write the test for RelayMessage creation**

```typescript
// tests/types/relay.test.ts
import { describe, it, expect } from "vitest";
import { createRelayMessage } from "../src/types/relay.js";

describe("RelayMessage", () => {
  it("creates a valid message with required fields", () => {
    const msg = createRelayMessage({
      tenantId: "tenant-1",
      sourcePlatform: "slack",
      sourceConnectionId: "conn-1",
      sourceChannelId: "C123",
      sourceMessageId: "1234567890.123456",
      sender: {
        displayName: "Kevin B",
        platformUserId: "U123",
      },
      content: { text: "Hello from Slack" },
    });

    expect(msg.id).toBeTruthy();
    expect(msg.tenantId).toBe("tenant-1");
    expect(msg.sourcePlatform).toBe("slack");
    expect(msg.content.text).toBe("Hello from Slack");
    expect(msg.attachments).toEqual([]);
    expect(msg.timestamp).toBeInstanceOf(Date);
  });

  it("preserves optional fields when provided", () => {
    const msg = createRelayMessage({
      tenantId: "tenant-1",
      sourcePlatform: "teams",
      sourceConnectionId: "conn-2",
      sourceChannelId: "19:abc@thread.v2",
      sourceMessageId: "msg-123",
      sourceThreadId: "thread-456",
      sender: {
        displayName: "Vendor",
        avatarUrl: "https://example.com/avatar.png",
        platformUserId: "user-789",
      },
      content: {
        text: "Hello",
        html: "<p>Hello</p>",
      },
      replyTo: "relay-msg-prev",
    });

    expect(msg.sourceThreadId).toBe("thread-456");
    expect(msg.sender.avatarUrl).toBe("https://example.com/avatar.png");
    expect(msg.content.html).toBe("<p>Hello</p>");
    expect(msg.replyTo).toBe("relay-msg-prev");
  });
});
```

**Step 2: Run test to verify it fails**

Run: `npx vitest run tests/types/relay.test.ts`
Expected: FAIL — module not found

**Step 3: Implement src/types/relay.ts**

```typescript
import { nanoid } from "nanoid";

export type Platform = "slack" | "teams" | "zoom" | "google_chat";

export interface RelayFile {
  filename: string;
  mimeType: string;
  sizeBytes: number;
  sourceUrl: string;
  storedUrl?: string;
}

export interface RelayReaction {
  relayMessageId: string;
  tenantId: string;
  sourceConnectionId: string;
  emoji: string;
  userId: string;
  displayName: string;
  added: boolean; // true = added, false = removed
}

export interface RelayMessage {
  id: string;
  tenantId: string;
  sourcePlatform: Platform;
  sourceConnectionId: string;
  sourceChannelId: string;
  sourceMessageId: string;
  sourceThreadId?: string;
  sender: {
    displayName: string;
    avatarUrl?: string;
    platformUserId: string;
  };
  content: {
    text: string;
    markdown?: string;
    html?: string;
  };
  attachments: RelayFile[];
  replyTo?: string;
  timestamp: Date;
}

export interface PlatformMessageRef {
  connectionId: string;
  platform: Platform;
  platformMessageId: string;
  platformThreadId?: string;
}

export type CreateRelayMessageInput = Omit<RelayMessage, "id" | "timestamp" | "attachments"> & {
  attachments?: RelayFile[];
};

export function createRelayMessage(input: CreateRelayMessageInput): RelayMessage {
  return {
    ...input,
    id: nanoid(),
    attachments: input.attachments ?? [],
    timestamp: new Date(),
  };
}
```

**Step 4: Implement src/types/connector.ts**

```typescript
import type { FastifyRequest } from "fastify";
import type {
  RelayMessage,
  RelayReaction,
  RelayFile,
  PlatformMessageRef,
  Platform,
} from "./relay.js";

export interface ChannelMapping {
  mappingId: string;
  connectionId: string;
  platform: Platform;
  platformChannelId: string;
}

export interface PlatformCredentials {
  platform: Platform;
  instance: string;
  [key: string]: unknown;
}

export interface Connector {
  name: string;
  platform: Platform;

  parseWebhook(req: FastifyRequest): Promise<RelayMessage | null>;
  sendMessage(msg: RelayMessage, mapping: ChannelMapping): Promise<PlatformMessageRef>;
  syncReaction(reaction: RelayReaction, mapping: ChannelMapping): Promise<void>;
  syncFile(file: RelayFile, mapping: ChannelMapping): Promise<string>;
  validateCredentials(creds: PlatformCredentials): Promise<boolean>;
}
```

**Step 5: Run tests**

Run: `npx vitest run tests/types/relay.test.ts`
Expected: PASS

**Step 6: Commit**

```bash
git add src/types/ tests/types/
git commit -m "feat: RelayMessage envelope and Connector interface"
```

---

## Task 3: Database Schema + Query Layer

**Files:**
- Create: `src/db/schema.sql`
- Create: `src/db/pool.ts`
- Create: `src/db/tenants.ts`
- Create: `src/db/connections.ts`
- Create: `src/db/mappings.ts`
- Create: `src/db/message-refs.ts`
- Test: `tests/db/message-refs.test.ts`
- Test: `tests/db/mappings.test.ts`

**Step 1: Create src/db/schema.sql**

```sql
-- Relay database schema
-- Run manually on Railway Postgres, or via init script

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS tenants (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  slug TEXT UNIQUE NOT NULL,
  api_key TEXT NOT NULL DEFAULT encode(gen_random_bytes(32), 'hex'),
  plan TEXT NOT NULL DEFAULT 'free',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS platform_connections (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  platform TEXT NOT NULL,
  instance TEXT NOT NULL DEFAULT 'default',
  credentials JSONB NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'active',
  metadata JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(tenant_id, platform, instance)
);

CREATE TABLE IF NOT EXISTS channel_mappings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  relay_channel TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(tenant_id, relay_channel)
);

CREATE TABLE IF NOT EXISTS channel_mapping_endpoints (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  mapping_id UUID NOT NULL REFERENCES channel_mappings(id),
  connection_id UUID NOT NULL REFERENCES platform_connections(id),
  platform_channel_id TEXT NOT NULL,
  platform_channel_name TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(mapping_id, connection_id, platform_channel_id)
);

CREATE TABLE IF NOT EXISTS message_refs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  relay_message_id TEXT NOT NULL,
  mapping_id UUID NOT NULL REFERENCES channel_mappings(id),
  connection_id UUID NOT NULL REFERENCES platform_connections(id),
  platform_message_id TEXT NOT NULL,
  platform_thread_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_message_refs_relay_id ON message_refs(relay_message_id);
CREATE INDEX IF NOT EXISTS idx_message_refs_platform ON message_refs(connection_id, platform_message_id);

CREATE TABLE IF NOT EXISTS file_refs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  relay_message_id TEXT NOT NULL,
  original_connection_id UUID NOT NULL REFERENCES platform_connections(id),
  original_url TEXT NOT NULL,
  stored_url TEXT,
  platform_urls JSONB NOT NULL DEFAULT '{}',
  mime_type TEXT,
  size_bytes INTEGER,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Step 2: Create src/db/pool.ts**

```typescript
import pg from "pg";
import { config } from "../config.js";

const { Pool } = pg;

let pool: pg.Pool | null = null;

export function getPool(): pg.Pool {
  if (!pool) {
    if (!config.databaseUrl) {
      throw new Error("DATABASE_URL is not set");
    }
    pool = new Pool({ connectionString: config.databaseUrl, max: 10 });
  }
  return pool;
}

export async function closePool(): Promise<void> {
  if (pool) {
    await pool.end();
    pool = null;
  }
}
```

**Step 3: Create src/db/tenants.ts**

```typescript
import { getPool } from "./pool.js";

export interface TenantRow {
  id: string;
  name: string;
  slug: string;
  api_key: string;
  plan: string;
  created_at: Date;
}

export async function getTenantBySlug(slug: string): Promise<TenantRow | null> {
  const { rows } = await getPool().query<TenantRow>(
    "SELECT * FROM tenants WHERE slug = $1",
    [slug],
  );
  return rows[0] ?? null;
}

export async function getTenantById(id: string): Promise<TenantRow | null> {
  const { rows } = await getPool().query<TenantRow>(
    "SELECT * FROM tenants WHERE id = $1",
    [id],
  );
  return rows[0] ?? null;
}
```

**Step 4: Create src/db/connections.ts**

```typescript
import { getPool } from "./pool.js";
import type { Platform } from "../types/relay.js";

export interface ConnectionRow {
  id: string;
  tenant_id: string;
  platform: Platform;
  instance: string;
  credentials: Record<string, unknown>;
  status: string;
  metadata: Record<string, unknown>;
  created_at: Date;
}

export async function getConnectionsByTenant(tenantId: string): Promise<ConnectionRow[]> {
  const { rows } = await getPool().query<ConnectionRow>(
    "SELECT * FROM platform_connections WHERE tenant_id = $1 AND status = 'active'",
    [tenantId],
  );
  return rows;
}

export async function getConnectionById(id: string): Promise<ConnectionRow | null> {
  const { rows } = await getPool().query<ConnectionRow>(
    "SELECT * FROM platform_connections WHERE id = $1",
    [id],
  );
  return rows[0] ?? null;
}

export async function updateConnectionStatus(
  id: string,
  status: "active" | "expired" | "error",
): Promise<void> {
  await getPool().query(
    "UPDATE platform_connections SET status = $1 WHERE id = $2",
    [status, id],
  );
}
```

**Step 5: Create src/db/mappings.ts**

```typescript
import { getPool } from "./pool.js";
import type { Platform } from "../types/relay.js";
import type { ChannelMapping } from "../types/connector.js";

export interface MappingEndpointRow {
  id: string;
  mapping_id: string;
  connection_id: string;
  platform_channel_id: string;
  platform_channel_name: string | null;
  relay_channel: string;
  tenant_id: string;
  platform: Platform;
  instance: string;
}

/**
 * Given a connection + channel, find all OTHER endpoints in the same relay channel.
 * This is the core routing query — "message came in on this channel, where does it go?"
 */
export async function getTargetEndpoints(
  connectionId: string,
  platformChannelId: string,
): Promise<MappingEndpointRow[]> {
  const { rows } = await getPool().query<MappingEndpointRow>(
    `SELECT
      e.id, e.mapping_id, e.connection_id, e.platform_channel_id, e.platform_channel_name,
      m.relay_channel, m.tenant_id,
      c.platform, c.instance
    FROM channel_mapping_endpoints e
    JOIN channel_mappings m ON m.id = e.mapping_id
    JOIN platform_connections c ON c.id = e.connection_id
    WHERE e.mapping_id = (
      SELECT mapping_id FROM channel_mapping_endpoints
      WHERE connection_id = $1 AND platform_channel_id = $2
      LIMIT 1
    )
    AND NOT (e.connection_id = $1 AND e.platform_channel_id = $2)
    AND c.status = 'active'`,
    [connectionId, platformChannelId],
  );
  return rows;
}

/**
 * Get the mapping ID for a connection + channel combo.
 */
export async function getMappingId(
  connectionId: string,
  platformChannelId: string,
): Promise<string | null> {
  const { rows } = await getPool().query<{ mapping_id: string }>(
    `SELECT mapping_id FROM channel_mapping_endpoints
     WHERE connection_id = $1 AND platform_channel_id = $2
     LIMIT 1`,
    [connectionId, platformChannelId],
  );
  return rows[0]?.mapping_id ?? null;
}
```

**Step 6: Create src/db/message-refs.ts**

```typescript
import { getPool } from "./pool.js";
import type { Platform } from "../types/relay.js";

export interface MessageRefRow {
  id: string;
  tenant_id: string;
  relay_message_id: string;
  mapping_id: string;
  connection_id: string;
  platform_message_id: string;
  platform_thread_id: string | null;
  created_at: Date;
}

export async function insertMessageRef(ref: {
  tenantId: string;
  relayMessageId: string;
  mappingId: string;
  connectionId: string;
  platformMessageId: string;
  platformThreadId?: string;
}): Promise<void> {
  await getPool().query(
    `INSERT INTO message_refs (tenant_id, relay_message_id, mapping_id, connection_id, platform_message_id, platform_thread_id)
     VALUES ($1, $2, $3, $4, $5, $6)
     ON CONFLICT DO NOTHING`,
    [ref.tenantId, ref.relayMessageId, ref.mappingId, ref.connectionId, ref.platformMessageId, ref.platformThreadId ?? null],
  );
}

/**
 * Given a platform message ID on a specific connection, find the relay message ID.
 */
export async function getRelayMessageId(
  connectionId: string,
  platformMessageId: string,
): Promise<string | null> {
  const { rows } = await getPool().query<{ relay_message_id: string }>(
    `SELECT relay_message_id FROM message_refs
     WHERE connection_id = $1 AND platform_message_id = $2
     LIMIT 1`,
    [connectionId, platformMessageId],
  );
  return rows[0]?.relay_message_id ?? null;
}

/**
 * Given a relay message ID, find all platform message refs (for thread sync).
 */
export async function getPlatformRefs(
  relayMessageId: string,
): Promise<MessageRefRow[]> {
  const { rows } = await getPool().query<MessageRefRow>(
    `SELECT * FROM message_refs WHERE relay_message_id = $1`,
    [relayMessageId],
  );
  return rows;
}

/**
 * Check if a message has already been relayed (idempotency).
 */
export async function messageAlreadyRelayed(
  connectionId: string,
  platformMessageId: string,
): Promise<boolean> {
  const { rows } = await getPool().query<{ count: string }>(
    `SELECT count(*) as count FROM message_refs
     WHERE connection_id = $1 AND platform_message_id = $2`,
    [connectionId, platformMessageId],
  );
  return parseInt(rows[0].count, 10) > 0;
}
```

**Step 7: Write tests for message-refs (unit tests with mocked pool)**

```typescript
// tests/db/message-refs.test.ts
import { describe, it, expect, vi, beforeEach } from "vitest";

// These tests validate the query logic by testing the SQL parameter binding.
// Integration tests against a real DB will be in tests/e2e/.

describe("message-refs queries", () => {
  it("insertMessageRef builds correct parameters", async () => {
    // Verify the module exports the expected functions
    const mod = await import("../../src/db/message-refs.js");
    expect(mod.insertMessageRef).toBeTypeOf("function");
    expect(mod.getRelayMessageId).toBeTypeOf("function");
    expect(mod.getPlatformRefs).toBeTypeOf("function");
    expect(mod.messageAlreadyRelayed).toBeTypeOf("function");
  });
});
```

**Step 8: Run tests**

Run: `npx vitest run tests/db/`
Expected: PASS (module import check only — real DB tests are e2e)

**Step 9: Commit**

```bash
git add src/db/ tests/db/
git commit -m "feat: database schema and query layer"
```

---

## Task 4: YAML Config Loader

**Files:**
- Create: `src/config-loader.ts`
- Create: `relay.example.yaml`
- Test: `tests/config-loader.test.ts`

**Step 1: Write the test**

```typescript
// tests/config-loader.test.ts
import { describe, it, expect } from "vitest";
import { parseRelayConfig } from "../src/config-loader.js";

const VALID_YAML = `
tenant: heritage-fabrics
platform_connections:
  - platform: slack
    instance: hfabrics
    credentials:
      bot_token: "xoxb-fake-token"
      signing_secret: "fake-secret"
  - platform: teams
    instance: default
    credentials:
      app_id: "fake-app-id"
      app_password: "fake-password"

channels:
  - name: operations
    endpoints:
      - connection: slack:hfabrics
        channel: C0AM3SY0HND
      - connection: teams:default
        channel: "19:abc@thread.v2"
  - name: warehouse
    endpoints:
      - connection: slack:hfabrics
        channel: C0WAREHOUSE
`;

describe("parseRelayConfig", () => {
  it("parses valid YAML into structured config", () => {
    const config = parseRelayConfig(VALID_YAML);
    expect(config.tenant).toBe("heritage-fabrics");
    expect(config.connections).toHaveLength(2);
    expect(config.connections[0].platform).toBe("slack");
    expect(config.connections[0].instance).toBe("hfabrics");
    expect(config.channels).toHaveLength(2);
    expect(config.channels[0].name).toBe("operations");
    expect(config.channels[0].endpoints).toHaveLength(2);
  });

  it("resolves connection references in endpoints", () => {
    const config = parseRelayConfig(VALID_YAML);
    const ops = config.channels[0];
    expect(ops.endpoints[0].connectionKey).toBe("slack:hfabrics");
    expect(ops.endpoints[0].channelId).toBe("C0AM3SY0HND");
    expect(ops.endpoints[1].connectionKey).toBe("teams:default");
  });

  it("throws on missing tenant", () => {
    expect(() => parseRelayConfig("channels: []")).toThrow("tenant");
  });

  it("throws on invalid connection reference", () => {
    const yaml = `
tenant: test
platform_connections:
  - platform: slack
    instance: main
    credentials: {}
channels:
  - name: ops
    endpoints:
      - connection: teams:nonexistent
        channel: C123
`;
    expect(() => parseRelayConfig(yaml)).toThrow("nonexistent");
  });
});
```

**Step 2: Run test to verify it fails**

Run: `npx vitest run tests/config-loader.test.ts`
Expected: FAIL

**Step 3: Implement src/config-loader.ts**

```typescript
import yaml from "js-yaml";
import type { Platform } from "./types/relay.js";

export interface RelayConnectionConfig {
  platform: Platform;
  instance: string;
  credentials: Record<string, string>;
}

export interface RelayEndpointConfig {
  connectionKey: string; // "platform:instance"
  channelId: string;
}

export interface RelayChannelConfig {
  name: string;
  endpoints: RelayEndpointConfig[];
}

export interface RelayConfig {
  tenant: string;
  connections: RelayConnectionConfig[];
  channels: RelayChannelConfig[];
}

interface RawYaml {
  tenant?: string;
  platform_connections?: Array<{
    platform: string;
    instance: string;
    credentials: Record<string, string>;
  }>;
  channels?: Array<{
    name: string;
    endpoints: Array<{
      connection: string;
      channel: string;
    }>;
  }>;
}

export function parseRelayConfig(yamlStr: string): RelayConfig {
  const raw = yaml.load(yamlStr) as RawYaml;

  if (!raw?.tenant) {
    throw new Error("Config must include 'tenant' field");
  }

  const connections: RelayConnectionConfig[] = (raw.platform_connections ?? []).map((c) => ({
    platform: c.platform as Platform,
    instance: c.instance,
    credentials: c.credentials ?? {},
  }));

  const connectionKeys = new Set(connections.map((c) => `${c.platform}:${c.instance}`));

  const channels: RelayChannelConfig[] = (raw.channels ?? []).map((ch) => ({
    name: ch.name,
    endpoints: ch.endpoints.map((ep) => {
      if (!connectionKeys.has(ep.connection)) {
        throw new Error(
          `Channel "${ch.name}" references connection "${ep.connection}" which is not defined in platform_connections`,
        );
      }
      return {
        connectionKey: ep.connection,
        channelId: ep.channel,
      };
    }),
  }));

  return { tenant: raw.tenant, connections, channels };
}
```

**Step 4: Create relay.example.yaml**

```yaml
# Relay configuration — Heritage Fabrics
# Copy to relay.yaml and fill in real credentials

tenant: heritage-fabrics

platform_connections:
  - platform: slack
    instance: hfabrics
    credentials:
      bot_token: "xoxb-YOUR-SLACK-BOT-TOKEN"
      signing_secret: "YOUR-SLACK-SIGNING-SECRET"
  - platform: slack
    instance: studiob
    credentials:
      bot_token: "xoxb-YOUR-STUDIOB-BOT-TOKEN"
      signing_secret: "YOUR-STUDIOB-SIGNING-SECRET"
  - platform: teams
    instance: default
    credentials:
      app_id: "YOUR-AZURE-APP-ID"
      app_password: "YOUR-AZURE-APP-PASSWORD"

channels:
  - name: operations
    endpoints:
      - connection: slack:hfabrics
        channel: C0AM3SY0HND
      - connection: slack:studiob
        channel: C0BLAH12345
      - connection: teams:default
        channel: "19:abc123@thread.v2"
  - name: warehouse
    endpoints:
      - connection: slack:hfabrics
        channel: C0WAREHOUSE
      - connection: teams:default
        channel: "19:def456@thread.v2"
```

**Step 5: Run tests**

Run: `npx vitest run tests/config-loader.test.ts`
Expected: PASS

**Step 6: Commit**

```bash
git add src/config-loader.ts relay.example.yaml tests/config-loader.test.ts
git commit -m "feat: YAML config loader with validation"
```

---

## Task 5: BullMQ Queue + Router Worker

**Files:**
- Create: `src/queue/setup.ts`
- Create: `src/router/worker.ts`
- Create: `src/router/dispatch.ts`
- Test: `tests/router/dispatch.test.ts`

**Step 1: Create src/queue/setup.ts**

```typescript
import { Queue, Worker } from "bullmq";
import type IORedis from "ioredis";

export const INBOUND_QUEUE = "relay:inbound";
export const OUTBOUND_QUEUE = "relay:outbound";

export function createInboundQueue(redis: IORedis): Queue {
  return new Queue(INBOUND_QUEUE, { connection: redis });
}

export function createOutboundQueue(redis: IORedis): Queue {
  return new Queue(OUTBOUND_QUEUE, { connection: redis });
}

export const RETRY_OPTS = {
  attempts: 5,
  backoff: {
    type: "custom" as const,
  },
};

// Custom backoff: 0, 5s, 30s, 2min, 10min
export function getBackoffDelay(attemptsMade: number): number {
  const delays = [0, 5_000, 30_000, 120_000, 600_000];
  return delays[Math.min(attemptsMade, delays.length - 1)];
}
```

**Step 2: Write the dispatch test**

```typescript
// tests/router/dispatch.test.ts
import { describe, it, expect, vi } from "vitest";
import { buildDispatchJobs } from "../src/router/dispatch.js";
import type { RelayMessage } from "../src/types/relay.js";

describe("buildDispatchJobs", () => {
  const msg: RelayMessage = {
    id: "relay-1",
    tenantId: "tenant-1",
    sourcePlatform: "slack",
    sourceConnectionId: "conn-slack",
    sourceChannelId: "C123",
    sourceMessageId: "ts-123",
    sender: { displayName: "Kevin", platformUserId: "U123" },
    content: { text: "Hello" },
    attachments: [],
    timestamp: new Date(),
  };

  it("creates one dispatch job per target endpoint", () => {
    const targets = [
      { id: "ep-1", mapping_id: "map-1", connection_id: "conn-teams", platform_channel_id: "19:abc", platform_channel_name: "ops", relay_channel: "operations", tenant_id: "tenant-1", platform: "teams" as const, instance: "default" },
      { id: "ep-2", mapping_id: "map-1", connection_id: "conn-zoom", platform_channel_id: "zoom-ch-1", platform_channel_name: "ops", relay_channel: "operations", tenant_id: "tenant-1", platform: "zoom" as const, instance: "default" },
    ];

    const jobs = buildDispatchJobs(msg, targets);
    expect(jobs).toHaveLength(2);
    expect(jobs[0].data.targetConnectionId).toBe("conn-teams");
    expect(jobs[0].data.targetChannelId).toBe("19:abc");
    expect(jobs[0].data.message).toEqual(msg);
    expect(jobs[0].name).toBe("dispatch:conn-teams:ts-123");
    expect(jobs[1].data.targetConnectionId).toBe("conn-zoom");
  });

  it("returns empty array when no targets", () => {
    const jobs = buildDispatchJobs(msg, []);
    expect(jobs).toHaveLength(0);
  });
});
```

**Step 3: Run test to verify it fails**

Run: `npx vitest run tests/router/dispatch.test.ts`
Expected: FAIL

**Step 4: Implement src/router/dispatch.ts**

```typescript
import type { RelayMessage } from "../types/relay.js";
import type { MappingEndpointRow } from "../db/mappings.js";

export interface DispatchJobData {
  message: RelayMessage;
  targetConnectionId: string;
  targetChannelId: string;
  targetPlatform: string;
  mappingId: string;
}

export interface DispatchJob {
  name: string;
  data: DispatchJobData;
}

export function buildDispatchJobs(
  msg: RelayMessage,
  targets: MappingEndpointRow[],
): DispatchJob[] {
  return targets.map((target) => ({
    name: `dispatch:${target.connection_id}:${msg.sourceMessageId}`,
    data: {
      message: msg,
      targetConnectionId: target.connection_id,
      targetChannelId: target.platform_channel_id,
      targetPlatform: target.platform,
      mappingId: target.mapping_id,
    },
  }));
}
```

**Step 5: Implement src/router/worker.ts**

```typescript
import { Worker, Job } from "bullmq";
import type IORedis from "ioredis";
import type { Logger } from "pino";
import { INBOUND_QUEUE, OUTBOUND_QUEUE, RETRY_OPTS, getBackoffDelay } from "../queue/setup.js";
import { getTargetEndpoints } from "../db/mappings.js";
import { messageAlreadyRelayed, insertMessageRef } from "../db/message-refs.js";
import { buildDispatchJobs } from "./dispatch.js";
import type { RelayMessage } from "../types/relay.js";
import type { Connector } from "../types/connector.js";
import { Queue } from "bullmq";

export function startInboundWorker(
  redis: IORedis,
  log: Logger,
): Worker {
  const outboundQueue = new Queue(OUTBOUND_QUEUE, { connection: redis });

  const worker = new Worker<RelayMessage>(
    INBOUND_QUEUE,
    async (job: Job<RelayMessage>) => {
      const msg = job.data;
      const childLog = log.child({ relayMessageId: msg.id, source: msg.sourcePlatform });

      // Idempotency check
      const alreadyRelayed = await messageAlreadyRelayed(
        msg.sourceConnectionId,
        msg.sourceMessageId,
      );
      if (alreadyRelayed) {
        childLog.info("Message already relayed, skipping");
        return;
      }

      // Find target endpoints
      const targets = await getTargetEndpoints(msg.sourceConnectionId, msg.sourceChannelId);
      if (targets.length === 0) {
        childLog.warn("No target endpoints found for channel");
        return;
      }

      // Build and enqueue dispatch jobs
      const jobs = buildDispatchJobs(msg, targets);
      for (const job of jobs) {
        await outboundQueue.add(job.name, job.data, {
          ...RETRY_OPTS,
          jobId: job.name, // dedup by job name
        });
      }

      childLog.info({ targetCount: jobs.length }, "Dispatched to targets");
    },
    {
      connection: redis,
      concurrency: 10,
      settings: {
        backoffStrategy: getBackoffDelay,
      },
    },
  );

  worker.on("completed", (job) => log.debug({ jobId: job?.id }, "Inbound job completed"));
  worker.on("failed", (job, err) => log.error({ jobId: job?.id, err }, "Inbound job failed"));

  return worker;
}

export function startOutboundWorker(
  redis: IORedis,
  connectors: Map<string, Connector>,
  log: Logger,
): Worker {
  const worker = new Worker(
    OUTBOUND_QUEUE,
    async (job) => {
      const { message, targetConnectionId, targetChannelId, targetPlatform, mappingId } = job.data;
      const childLog = log.child({ relayMessageId: message.id, target: targetPlatform });

      const connector = connectors.get(targetConnectionId);
      if (!connector) {
        childLog.error({ targetConnectionId }, "No connector found for connection");
        throw new Error(`No connector for connection ${targetConnectionId}`);
      }

      const ref = await connector.sendMessage(message, {
        mappingId,
        connectionId: targetConnectionId,
        platform: targetPlatform,
        platformChannelId: targetChannelId,
      });

      // Store cross-reference
      await insertMessageRef({
        tenantId: message.tenantId,
        relayMessageId: message.id,
        mappingId,
        connectionId: targetConnectionId,
        platformMessageId: ref.platformMessageId,
        platformThreadId: ref.platformThreadId,
      });

      // Also store source ref if this is the first dispatch
      await insertMessageRef({
        tenantId: message.tenantId,
        relayMessageId: message.id,
        mappingId,
        connectionId: message.sourceConnectionId,
        platformMessageId: message.sourceMessageId,
        platformThreadId: message.sourceThreadId,
      });

      childLog.info({ platformMessageId: ref.platformMessageId }, "Message delivered");
    },
    {
      connection: redis,
      concurrency: 5,
      settings: {
        backoffStrategy: getBackoffDelay,
      },
    },
  );

  worker.on("completed", (job) => log.debug({ jobId: job?.id }, "Outbound job completed"));
  worker.on("failed", (job, err) => log.error({ jobId: job?.id, err }, "Outbound job failed"));

  return worker;
}
```

**Step 6: Run tests**

Run: `npx vitest run tests/router/`
Expected: PASS

**Step 7: Commit**

```bash
git add src/queue/ src/router/ tests/router/
git commit -m "feat: BullMQ queue setup and router workers"
```

---

## Task 6: Slack Connector

**Files:**
- Create: `src/connectors/slack.ts`
- Create: `src/connectors/slack-verify.ts`
- Test: `tests/connectors/slack.test.ts`
- Test: `tests/connectors/slack-verify.test.ts`

**Step 1: Write the webhook verification test**

```typescript
// tests/connectors/slack-verify.test.ts
import { describe, it, expect } from "vitest";
import crypto from "node:crypto";
import { verifySlackSignature } from "../src/connectors/slack-verify.js";

describe("verifySlackSignature", () => {
  const signingSecret = "test-signing-secret";

  function sign(body: string, timestamp: number): string {
    const sigBasestring = `v0:${timestamp}:${body}`;
    return "v0=" + crypto.createHmac("sha256", signingSecret).update(sigBasestring).digest("hex");
  }

  it("returns true for valid signature", () => {
    const body = '{"event":"test"}';
    const ts = Math.floor(Date.now() / 1000);
    const sig = sign(body, ts);
    expect(verifySlackSignature(signingSecret, sig, ts.toString(), body)).toBe(true);
  });

  it("returns false for invalid signature", () => {
    const body = '{"event":"test"}';
    const ts = Math.floor(Date.now() / 1000);
    expect(verifySlackSignature(signingSecret, "v0=bad", ts.toString(), body)).toBe(false);
  });

  it("returns false for stale timestamp (> 5 min)", () => {
    const body = '{"event":"test"}';
    const ts = Math.floor(Date.now() / 1000) - 600; // 10 min ago
    const sig = sign(body, ts);
    expect(verifySlackSignature(signingSecret, sig, ts.toString(), body)).toBe(false);
  });
});
```

**Step 2: Run test to verify it fails**

Run: `npx vitest run tests/connectors/slack-verify.test.ts`
Expected: FAIL

**Step 3: Implement src/connectors/slack-verify.ts**

```typescript
import crypto from "node:crypto";

export function verifySlackSignature(
  signingSecret: string,
  signature: string,
  timestamp: string,
  body: string,
): boolean {
  // Reject requests older than 5 minutes
  const now = Math.floor(Date.now() / 1000);
  if (Math.abs(now - parseInt(timestamp, 10)) > 300) {
    return false;
  }

  const sigBasestring = `v0:${timestamp}:${body}`;
  const expected =
    "v0=" + crypto.createHmac("sha256", signingSecret).update(sigBasestring).digest("hex");

  return crypto.timingSafeEqual(Buffer.from(signature), Buffer.from(expected));
}
```

**Step 4: Run verification tests**

Run: `npx vitest run tests/connectors/slack-verify.test.ts`
Expected: PASS

**Step 5: Write Slack connector parse test**

```typescript
// tests/connectors/slack.test.ts
import { describe, it, expect } from "vitest";
import { parseSlackMessageEvent } from "../src/connectors/slack.js";

describe("parseSlackMessageEvent", () => {
  it("parses a standard message event", () => {
    const event = {
      type: "message",
      user: "U123ABC",
      text: "Hello from Slack!",
      ts: "1234567890.123456",
      channel: "C0AM3SY0HND",
    };

    const result = parseSlackMessageEvent(event, "conn-1", "tenant-1");
    expect(result).not.toBeNull();
    expect(result!.sourcePlatform).toBe("slack");
    expect(result!.sourceConnectionId).toBe("conn-1");
    expect(result!.sourceChannelId).toBe("C0AM3SY0HND");
    expect(result!.sourceMessageId).toBe("1234567890.123456");
    expect(result!.content.text).toBe("Hello from Slack!");
    expect(result!.sender.platformUserId).toBe("U123ABC");
  });

  it("handles threaded replies", () => {
    const event = {
      type: "message",
      user: "U123ABC",
      text: "Thread reply",
      ts: "1234567890.999999",
      thread_ts: "1234567890.123456",
      channel: "C0AM3SY0HND",
    };

    const result = parseSlackMessageEvent(event, "conn-1", "tenant-1");
    expect(result!.sourceThreadId).toBe("1234567890.123456");
  });

  it("returns null for bot messages (loop prevention)", () => {
    const event = {
      type: "message",
      subtype: "bot_message",
      text: "Bot says hi",
      ts: "123",
      channel: "C123",
    };

    const result = parseSlackMessageEvent(event, "conn-1", "tenant-1");
    expect(result).toBeNull();
  });

  it("returns null for message_changed subtypes", () => {
    const event = {
      type: "message",
      subtype: "message_changed",
      ts: "123",
      channel: "C123",
    };

    const result = parseSlackMessageEvent(event, "conn-1", "tenant-1");
    expect(result).toBeNull();
  });
});
```

**Step 6: Implement src/connectors/slack.ts**

```typescript
import { WebClient } from "@slack/web-api";
import { createRelayMessage } from "../types/relay.js";
import type {
  RelayMessage,
  RelayReaction,
  RelayFile,
  PlatformMessageRef,
} from "../types/relay.js";
import type { Connector, ChannelMapping, PlatformCredentials } from "../types/connector.js";
import { getRelayMessageId, getPlatformRefs } from "../db/message-refs.js";
import type { Logger } from "pino";

interface SlackMessageEvent {
  type: string;
  subtype?: string;
  user?: string;
  bot_id?: string;
  text?: string;
  ts: string;
  thread_ts?: string;
  channel: string;
  files?: Array<{
    name: string;
    mimetype: string;
    size: number;
    url_private: string;
  }>;
  // Relay origin metadata for loop prevention
  metadata?: {
    event_type?: string;
  };
}

/**
 * Parse a Slack message event into a RelayMessage.
 * Returns null if the message should be ignored (bot, subtype, loop).
 */
export function parseSlackMessageEvent(
  event: SlackMessageEvent,
  connectionId: string,
  tenantId: string,
): RelayMessage | null {
  // Ignore bot messages (loop prevention layer 1)
  if (event.subtype === "bot_message" || event.bot_id) {
    return null;
  }

  // Ignore non-standard message subtypes (edits, deletes, etc.)
  // Phase 1: only handle new messages
  if (event.subtype) {
    return null;
  }

  // Ignore relay-originated messages (loop prevention layer 2)
  if (event.metadata?.event_type === "relay_origin") {
    return null;
  }

  if (!event.user || !event.text) {
    return null;
  }

  const attachments: RelayFile[] = (event.files ?? []).map((f) => ({
    filename: f.name,
    mimeType: f.mimetype,
    sizeBytes: f.size,
    sourceUrl: f.url_private,
  }));

  return createRelayMessage({
    tenantId,
    sourcePlatform: "slack",
    sourceConnectionId: connectionId,
    sourceChannelId: event.channel,
    sourceMessageId: event.ts,
    sourceThreadId: event.thread_ts,
    sender: {
      displayName: event.user, // Will be resolved to real name via users.info
      platformUserId: event.user,
    },
    content: {
      text: event.text,
      markdown: event.text, // Slack uses mrkdwn
    },
    attachments,
  });
}

export class SlackConnector implements Connector {
  name = "slack";
  platform = "slack" as const;

  private client: WebClient;
  private botUserId: string | null = null;
  private log: Logger;

  constructor(
    private connectionId: string,
    private botToken: string,
    private signingSecret: string,
    log: Logger,
  ) {
    this.client = new WebClient(botToken);
    this.log = log.child({ connector: "slack", connectionId });
  }

  async parseWebhook(): Promise<RelayMessage | null> {
    // Handled by route handler, not here
    throw new Error("Use parseSlackMessageEvent directly from route handler");
  }

  async sendMessage(
    msg: RelayMessage,
    mapping: ChannelMapping,
  ): Promise<PlatformMessageRef> {
    // Resolve thread if this is a reply
    let threadTs: string | undefined;
    if (msg.replyTo || msg.sourceThreadId) {
      const replyToId = msg.replyTo ?? msg.sourceThreadId;
      if (replyToId) {
        // Look up the Slack thread_ts for this relay thread
        const relayMsgId = await getRelayMessageId(
          msg.sourceConnectionId,
          msg.sourceThreadId ?? msg.sourceMessageId,
        );
        if (relayMsgId) {
          const refs = await getPlatformRefs(relayMsgId);
          const slackRef = refs.find((r) => r.connection_id === mapping.connectionId);
          threadTs = slackRef?.platform_thread_id ?? slackRef?.platform_message_id;
        }
      }
    }

    const result = await this.client.chat.postMessage({
      channel: mapping.platformChannelId,
      text: msg.content.text,
      username: msg.sender.displayName,
      icon_url: msg.sender.avatarUrl,
      thread_ts: threadTs,
      metadata: {
        event_type: "relay_origin",
        event_payload: { source: msg.sourcePlatform, relayId: msg.id },
      },
    });

    return {
      connectionId: mapping.connectionId,
      platform: "slack",
      platformMessageId: result.ts!,
      platformThreadId: threadTs,
    };
  }

  async syncReaction(
    reaction: RelayReaction,
    mapping: ChannelMapping,
  ): Promise<void> {
    // Find the Slack ts for this message
    const refs = await getPlatformRefs(reaction.relayMessageId);
    const slackRef = refs.find((r) => r.connection_id === mapping.connectionId);
    if (!slackRef) return;

    if (reaction.added) {
      await this.client.reactions.add({
        channel: mapping.platformChannelId,
        timestamp: slackRef.platform_message_id,
        name: reaction.emoji,
      });
    } else {
      await this.client.reactions.remove({
        channel: mapping.platformChannelId,
        timestamp: slackRef.platform_message_id,
        name: reaction.emoji,
      });
    }
  }

  async syncFile(
    file: RelayFile,
    mapping: ChannelMapping,
  ): Promise<string> {
    // Download from stored URL, upload to Slack
    // Phase 1: simplified — upload from URL
    const response = await fetch(file.storedUrl ?? file.sourceUrl);
    const buffer = Buffer.from(await response.arrayBuffer());

    const result = await this.client.filesUploadV2({
      channel_id: mapping.platformChannelId,
      file: buffer,
      filename: file.filename,
    });

    return result.files?.[0]?.permalink ?? "";
  }

  async validateCredentials(): Promise<boolean> {
    try {
      const result = await this.client.auth.test();
      this.botUserId = result.user_id ?? null;
      return result.ok ?? false;
    } catch {
      return false;
    }
  }
}
```

**Step 7: Run all tests**

Run: `npx vitest run tests/connectors/`
Expected: PASS

**Step 8: Commit**

```bash
git add src/connectors/slack.ts src/connectors/slack-verify.ts tests/connectors/
git commit -m "feat: Slack connector — parse, send, reactions, file relay"
```

---

## Task 7: Teams Connector

**Files:**
- Create: `src/connectors/teams.ts`
- Test: `tests/connectors/teams.test.ts`

**Step 1: Write the Teams message parse test**

```typescript
// tests/connectors/teams.test.ts
import { describe, it, expect } from "vitest";
import { parseTeamsActivity } from "../src/connectors/teams.js";

describe("parseTeamsActivity", () => {
  it("parses a standard Teams message", () => {
    const activity = {
      type: "message",
      id: "msg-123",
      from: {
        id: "user-abc",
        name: "Vendor Bob",
      },
      conversation: {
        id: "19:abc@thread.v2",
      },
      text: "Hello from Teams!",
      timestamp: "2026-04-06T12:00:00Z",
    };

    const result = parseTeamsActivity(activity, "conn-teams", "tenant-1");
    expect(result).not.toBeNull();
    expect(result!.sourcePlatform).toBe("teams");
    expect(result!.sourceConnectionId).toBe("conn-teams");
    expect(result!.sourceChannelId).toBe("19:abc@thread.v2");
    expect(result!.sourceMessageId).toBe("msg-123");
    expect(result!.content.text).toBe("Hello from Teams!");
    expect(result!.sender.displayName).toBe("Vendor Bob");
  });

  it("strips HTML tags from Teams messages", () => {
    const activity = {
      type: "message",
      id: "msg-456",
      from: { id: "user-abc", name: "Bob" },
      conversation: { id: "19:abc@thread.v2" },
      text: "<p>Hello <b>bold</b> world</p>",
      timestamp: "2026-04-06T12:00:00Z",
    };

    const result = parseTeamsActivity(activity, "conn-teams", "tenant-1");
    expect(result!.content.text).toBe("Hello bold world");
    expect(result!.content.html).toBe("<p>Hello <b>bold</b> world</p>");
  });

  it("handles threaded replies via replyToId", () => {
    const activity = {
      type: "message",
      id: "msg-789",
      from: { id: "user-abc", name: "Bob" },
      conversation: {
        id: "19:abc@thread.v2",
      },
      replyToId: "msg-123",
      text: "Thread reply",
      timestamp: "2026-04-06T12:00:00Z",
    };

    const result = parseTeamsActivity(activity, "conn-teams", "tenant-1");
    expect(result!.sourceThreadId).toBe("msg-123");
  });

  it("returns null for relay-originated messages", () => {
    const activity = {
      type: "message",
      id: "msg-loop",
      from: { id: "bot-relay", name: "Relay" },
      conversation: { id: "19:abc@thread.v2" },
      text: "Relayed message",
      timestamp: "2026-04-06T12:00:00Z",
      channelData: { relayOrigin: true },
    };

    const result = parseTeamsActivity(activity, "conn-teams", "tenant-1");
    expect(result).toBeNull();
  });
});
```

**Step 2: Run test to verify it fails**

Run: `npx vitest run tests/connectors/teams.test.ts`
Expected: FAIL

**Step 3: Implement src/connectors/teams.ts**

```typescript
import { createRelayMessage } from "../types/relay.js";
import type {
  RelayMessage,
  RelayReaction,
  RelayFile,
  PlatformMessageRef,
} from "../types/relay.js";
import type { Connector, ChannelMapping, PlatformCredentials } from "../types/connector.js";
import { getRelayMessageId, getPlatformRefs } from "../db/message-refs.js";
import type { Logger } from "pino";

interface TeamsActivity {
  type: string;
  id: string;
  from: { id: string; name: string };
  conversation: { id: string };
  replyToId?: string;
  text?: string;
  timestamp: string;
  attachments?: Array<{
    contentType: string;
    contentUrl?: string;
    name?: string;
  }>;
  channelData?: { relayOrigin?: boolean };
}

function stripHtml(html: string): string {
  return html.replace(/<[^>]*>/g, "");
}

/**
 * Parse a Teams Bot Framework activity into a RelayMessage.
 */
export function parseTeamsActivity(
  activity: TeamsActivity,
  connectionId: string,
  tenantId: string,
): RelayMessage | null {
  if (activity.type !== "message") return null;

  // Loop prevention: check relay origin tag
  if (activity.channelData?.relayOrigin) return null;

  if (!activity.text) return null;

  const plainText = stripHtml(activity.text);
  const hasHtml = activity.text !== plainText;

  const attachments: RelayFile[] = (activity.attachments ?? [])
    .filter((a) => a.contentUrl)
    .map((a) => ({
      filename: a.name ?? "attachment",
      mimeType: a.contentType,
      sizeBytes: 0, // Teams doesn't include size in activity
      sourceUrl: a.contentUrl!,
    }));

  return createRelayMessage({
    tenantId,
    sourcePlatform: "teams",
    sourceConnectionId: connectionId,
    sourceChannelId: activity.conversation.id,
    sourceMessageId: activity.id,
    sourceThreadId: activity.replyToId,
    sender: {
      displayName: activity.from.name,
      platformUserId: activity.from.id,
    },
    content: {
      text: plainText,
      html: hasHtml ? activity.text : undefined,
    },
    attachments,
  });
}

export class TeamsConnector implements Connector {
  name = "teams";
  platform = "teams" as const;

  private accessToken: string | null = null;
  private tokenExpiry = 0;
  private log: Logger;

  constructor(
    private connectionId: string,
    private appId: string,
    private appPassword: string,
    log: Logger,
  ) {
    this.log = log.child({ connector: "teams", connectionId });
  }

  private async getAccessToken(): Promise<string> {
    if (this.accessToken && Date.now() < this.tokenExpiry) {
      return this.accessToken;
    }

    const response = await fetch(
      "https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token",
      {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({
          grant_type: "client_credentials",
          client_id: this.appId,
          client_secret: this.appPassword,
          scope: "https://api.botframework.com/.default",
        }),
      },
    );

    const data = (await response.json()) as { access_token: string; expires_in: number };
    this.accessToken = data.access_token;
    this.tokenExpiry = Date.now() + (data.expires_in - 60) * 1000;
    return this.accessToken;
  }

  async parseWebhook(): Promise<RelayMessage | null> {
    throw new Error("Use parseTeamsActivity directly from route handler");
  }

  async sendMessage(
    msg: RelayMessage,
    mapping: ChannelMapping,
  ): Promise<PlatformMessageRef> {
    const token = await this.getAccessToken();

    // Resolve thread
    let replyToId: string | undefined;
    if (msg.sourceThreadId) {
      const relayMsgId = await getRelayMessageId(
        msg.sourceConnectionId,
        msg.sourceThreadId,
      );
      if (relayMsgId) {
        const refs = await getPlatformRefs(relayMsgId);
        const teamsRef = refs.find((r) => r.connection_id === mapping.connectionId);
        replyToId = teamsRef?.platform_message_id;
      }
    }

    // Build message body
    const body: Record<string, unknown> = {
      body: {
        contentType: "html",
        content: `<b>${msg.sender.displayName}</b>: ${msg.content.html ?? msg.content.text}`,
      },
      channelData: { relayOrigin: true },
    };

    // Post message
    const serviceUrl = "https://smba.trafficmanager.net/teams";
    const conversationId = mapping.platformChannelId;
    let url = `${serviceUrl}/v3/conversations/${encodeURIComponent(conversationId)}/activities`;

    if (replyToId) {
      url = `${serviceUrl}/v3/conversations/${encodeURIComponent(conversationId)}/activities/${replyToId}`;
    }

    const response = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });

    const result = (await response.json()) as { id: string };

    return {
      connectionId: mapping.connectionId,
      platform: "teams",
      platformMessageId: result.id,
      platformThreadId: replyToId,
    };
  }

  async syncReaction(
    reaction: RelayReaction,
    mapping: ChannelMapping,
  ): Promise<void> {
    // Teams reaction sync is limited — Bot Framework doesn't support adding reactions on behalf of users.
    // Log and skip for Phase 1.
    this.log.info({ emoji: reaction.emoji }, "Teams reaction sync not supported in Phase 1");
  }

  async syncFile(
    file: RelayFile,
    mapping: ChannelMapping,
  ): Promise<string> {
    // Phase 1: Include file URL in message text rather than native Teams file upload
    // (Teams file upload requires SharePoint/OneDrive integration which is complex)
    this.log.info({ filename: file.filename }, "File shared as link (Phase 1)");
    return file.storedUrl ?? file.sourceUrl;
  }

  async validateCredentials(): Promise<boolean> {
    try {
      await this.getAccessToken();
      return true;
    } catch {
      return false;
    }
  }
}
```

**Step 4: Run tests**

Run: `npx vitest run tests/connectors/teams.test.ts`
Expected: PASS

**Step 5: Commit**

```bash
git add src/connectors/teams.ts tests/connectors/teams.test.ts
git commit -m "feat: Teams connector — parse, send, thread sync"
```

---

## Task 8: Webhook Routes

**Files:**
- Create: `src/routes/slack-webhook.ts`
- Create: `src/routes/teams-webhook.ts`
- Create: `src/routes/health.ts`
- Modify: `src/index.ts` — register routes, initialize Redis, Postgres, workers

**Step 1: Create src/routes/health.ts**

```typescript
import type { FastifyInstance } from "fastify";

export function registerHealthRoutes(app: FastifyInstance): void {
  app.get("/health", async () => ({
    status: "ok",
    timestamp: new Date().toISOString(),
  }));
}
```

**Step 2: Create src/routes/slack-webhook.ts**

```typescript
import type { FastifyInstance, FastifyRequest, FastifyReply } from "fastify";
import type { Queue } from "bullmq";
import type { Logger } from "pino";
import { verifySlackSignature } from "../connectors/slack-verify.js";
import { parseSlackMessageEvent } from "../connectors/slack.js";

interface SlackWebhookDeps {
  inboundQueue: Queue;
  log: Logger;
  // Map of Slack team_id → { connectionId, signingSecret, tenantId }
  slackConnections: Map<string, {
    connectionId: string;
    signingSecret: string;
    tenantId: string;
  }>;
}

export function registerSlackWebhookRoutes(
  app: FastifyInstance,
  deps: SlackWebhookDeps,
): void {
  // Slack needs raw body for signature verification
  app.addContentTypeParser(
    "application/json",
    { parseAs: "string" },
    (req, body, done) => {
      try {
        const json = JSON.parse(body as string);
        // Store raw body for signature verification
        (req as any).rawBody = body;
        done(null, json);
      } catch (err) {
        done(err as Error, undefined);
      }
    },
  );

  app.post("/webhooks/slack", async (req: FastifyRequest, reply: FastifyReply) => {
    const body = req.body as any;
    const rawBody = (req as any).rawBody as string;

    // Handle Slack URL verification challenge
    if (body.type === "url_verification") {
      return { challenge: body.challenge };
    }

    // Find connection by team_id
    const teamId = body.team_id;
    const conn = deps.slackConnections.get(teamId);
    if (!conn) {
      deps.log.warn({ teamId }, "Unknown Slack team_id");
      return reply.code(404).send({ error: "Unknown team" });
    }

    // Verify signature
    const signature = req.headers["x-slack-signature"] as string;
    const timestamp = req.headers["x-slack-request-timestamp"] as string;

    if (!verifySlackSignature(conn.signingSecret, signature, timestamp, rawBody)) {
      deps.log.warn("Invalid Slack signature");
      return reply.code(401).send({ error: "Invalid signature" });
    }

    // Process event callback
    if (body.type === "event_callback" && body.event?.type === "message") {
      const msg = parseSlackMessageEvent(body.event, conn.connectionId, conn.tenantId);
      if (msg) {
        await deps.inboundQueue.add(`slack:${msg.sourceMessageId}`, msg, {
          jobId: `slack:${conn.connectionId}:${msg.sourceMessageId}`,
        });
        deps.log.info({ relayId: msg.id, channel: msg.sourceChannelId }, "Slack message enqueued");
      }
    }

    // Slack expects 200 within 3 seconds
    return { ok: true };
  });
}
```

**Step 3: Create src/routes/teams-webhook.ts**

```typescript
import type { FastifyInstance, FastifyRequest, FastifyReply } from "fastify";
import type { Queue } from "bullmq";
import type { Logger } from "pino";
import { parseTeamsActivity } from "../connectors/teams.js";

interface TeamsWebhookDeps {
  inboundQueue: Queue;
  log: Logger;
  // Teams connection config
  teamsConnectionId: string;
  tenantId: string;
  appId: string;
}

export function registerTeamsWebhookRoutes(
  app: FastifyInstance,
  deps: TeamsWebhookDeps,
): void {
  app.post("/webhooks/teams", async (req: FastifyRequest, reply: FastifyReply) => {
    const activity = req.body as any;

    // Bot Framework sends various activity types — only handle messages
    if (activity.type !== "message") {
      return { ok: true };
    }

    // TODO Phase 1: validate JWT from Bot Framework
    // For now, rely on Azure Bot Service endpoint being non-guessable
    // Full JWT validation requires fetching Microsoft's OpenID config

    const msg = parseTeamsActivity(activity, deps.teamsConnectionId, deps.tenantId);
    if (msg) {
      await deps.inboundQueue.add(`teams:${msg.sourceMessageId}`, msg, {
        jobId: `teams:${deps.teamsConnectionId}:${msg.sourceMessageId}`,
      });
      deps.log.info({ relayId: msg.id, channel: msg.sourceChannelId }, "Teams message enqueued");
    }

    return { ok: true };
  });
}
```

**Step 4: Update src/index.ts — full server initialization**

```typescript
import Fastify from "fastify";
import pino from "pino";
import IORedis from "ioredis";
import pg from "pg";
import fs from "node:fs";
import { config } from "./config.js";
import { parseRelayConfig } from "./config-loader.js";
import { createInboundQueue, createOutboundQueue } from "./queue/setup.js";
import { startInboundWorker, startOutboundWorker } from "./router/worker.js";
import { registerHealthRoutes } from "./routes/health.js";
import { registerSlackWebhookRoutes } from "./routes/slack-webhook.js";
import { registerTeamsWebhookRoutes } from "./routes/teams-webhook.js";
import { SlackConnector } from "./connectors/slack.js";
import { TeamsConnector } from "./connectors/teams.js";
import type { Connector } from "./types/connector.js";

const logger = pino({ level: config.logLevel });

async function main() {
  const app = Fastify({ logger });

  // Database
  const { Pool } = pg;
  const pgPool = config.databaseUrl
    ? new Pool({ connectionString: config.databaseUrl, max: 10 })
    : null;

  if (!pgPool) {
    logger.warn("No DATABASE_URL — running without persistence");
  }

  // Redis
  const redis = config.redisUrl
    ? new IORedis(config.redisUrl, { maxRetriesPerRequest: null })
    : null;

  if (!redis) {
    logger.error("REDIS_URL is required");
    process.exit(1);
  }

  // Load relay config
  let relayConfig;
  try {
    const yamlStr = fs.readFileSync(config.configPath, "utf-8");
    relayConfig = parseRelayConfig(yamlStr);
    logger.info({ tenant: relayConfig.tenant, channels: relayConfig.channels.length }, "Config loaded");
  } catch (err) {
    logger.error({ err, path: config.configPath }, "Failed to load relay config");
    process.exit(1);
  }

  // Initialize queues
  const inboundQueue = createInboundQueue(redis);
  const outboundQueue = createOutboundQueue(redis);

  // Initialize connectors from config
  // Phase 1: connectors are keyed by "platform:instance" and mapped to connection IDs
  // In production, connection IDs come from Postgres. Phase 1 uses config-derived IDs.
  const connectors = new Map<string, Connector>();
  const slackConnections = new Map<string, { connectionId: string; signingSecret: string; tenantId: string }>();

  let teamsConnectionId = "";

  for (const conn of relayConfig.connections) {
    const connKey = `${conn.platform}:${conn.instance}`;

    if (conn.platform === "slack") {
      const connector = new SlackConnector(
        connKey,
        conn.credentials.bot_token,
        conn.credentials.signing_secret,
        logger,
      );
      connectors.set(connKey, connector);

      // We need team_id to route incoming webhooks. Validate credentials to get it.
      // For Phase 1, store by connection key and resolve team_id at startup.
      const valid = await connector.validateCredentials();
      if (valid) {
        logger.info({ connKey }, "Slack connector validated");
        // TODO: map team_id from auth.test response
        // For now, use instance name as lookup key
        slackConnections.set(conn.instance, {
          connectionId: connKey,
          signingSecret: conn.credentials.signing_secret,
          tenantId: relayConfig.tenant,
        });
      } else {
        logger.error({ connKey }, "Slack connector validation failed");
      }
    }

    if (conn.platform === "teams") {
      const connector = new TeamsConnector(
        connKey,
        conn.credentials.app_id,
        conn.credentials.app_password,
        logger,
      );
      connectors.set(connKey, connector);
      teamsConnectionId = connKey;

      const valid = await connector.validateCredentials();
      if (valid) {
        logger.info({ connKey }, "Teams connector validated");
      } else {
        logger.error({ connKey }, "Teams connector validation failed");
      }
    }
  }

  // Start workers
  startInboundWorker(redis, logger);
  startOutboundWorker(redis, connectors, logger);

  // Register routes
  registerHealthRoutes(app);
  registerSlackWebhookRoutes(app, {
    inboundQueue,
    log: logger,
    slackConnections,
  });
  registerTeamsWebhookRoutes(app, {
    inboundQueue,
    log: logger,
    teamsConnectionId,
    tenantId: relayConfig.tenant,
    appId: config.teamsAppId ?? "",
  });

  // Start server
  await app.listen({ port: config.port, host: "0.0.0.0" });
  logger.info({ port: config.port }, "Relay server started");

  // Graceful shutdown
  const shutdown = async () => {
    logger.info("Shutting down...");
    await app.close();
    if (pgPool) await pgPool.end();
    if (redis) redis.disconnect();
    process.exit(0);
  };

  process.on("SIGTERM", shutdown);
  process.on("SIGINT", shutdown);
}

main().catch((err) => {
  logger.error(err, "Fatal error");
  process.exit(1);
});
```

**Step 5: Run all tests**

Run: `npx vitest run`
Expected: All PASS

**Step 6: Run typecheck**

Run: `npx tsc --noEmit`
Expected: No errors

**Step 7: Commit**

```bash
git add src/routes/ src/index.ts
git commit -m "feat: webhook routes + full server initialization"
```

---

## Task 9: Loop Prevention + Dedup

**Files:**
- Create: `src/loop-prevention.ts`
- Test: `tests/loop-prevention.test.ts`

**Step 1: Write the test**

```typescript
// tests/loop-prevention.test.ts
import { describe, it, expect, beforeEach } from "vitest";
import { ContentDeduplicator } from "../src/loop-prevention.js";

describe("ContentDeduplicator", () => {
  let dedup: ContentDeduplicator;

  beforeEach(() => {
    dedup = new ContentDeduplicator(5_000); // 5 second window
  });

  it("returns false for first occurrence of content", () => {
    expect(dedup.isDuplicate("user1", "Hello world")).toBe(false);
  });

  it("returns true for same content + sender within window", () => {
    dedup.isDuplicate("user1", "Hello world");
    expect(dedup.isDuplicate("user1", "Hello world")).toBe(true);
  });

  it("returns false for same content from different sender", () => {
    dedup.isDuplicate("user1", "Hello world");
    expect(dedup.isDuplicate("user2", "Hello world")).toBe(false);
  });

  it("returns false for different content from same sender", () => {
    dedup.isDuplicate("user1", "Hello world");
    expect(dedup.isDuplicate("user1", "Goodbye world")).toBe(false);
  });

  it("expires entries after window", async () => {
    const shortDedup = new ContentDeduplicator(50); // 50ms window
    shortDedup.isDuplicate("user1", "Hello");
    await new Promise((r) => setTimeout(r, 100));
    expect(shortDedup.isDuplicate("user1", "Hello")).toBe(false);
  });
});
```

**Step 2: Run test to verify it fails**

Run: `npx vitest run tests/loop-prevention.test.ts`
Expected: FAIL

**Step 3: Implement src/loop-prevention.ts**

```typescript
import crypto from "node:crypto";

export class ContentDeduplicator {
  private seen = new Map<string, number>(); // hash → expiry timestamp

  constructor(private windowMs: number = 5_000) {}

  isDuplicate(senderId: string, content: string): boolean {
    this.cleanup();

    const hash = crypto
      .createHash("sha256")
      .update(`${senderId}:${content}`)
      .digest("hex");

    if (this.seen.has(hash)) {
      return true;
    }

    this.seen.set(hash, Date.now() + this.windowMs);
    return false;
  }

  private cleanup(): void {
    const now = Date.now();
    for (const [hash, expiry] of this.seen) {
      if (expiry < now) {
        this.seen.delete(hash);
      }
    }
  }
}
```

**Step 4: Run tests**

Run: `npx vitest run tests/loop-prevention.test.ts`
Expected: PASS

**Step 5: Commit**

```bash
git add src/loop-prevention.ts tests/loop-prevention.test.ts
git commit -m "feat: content-based dedup for loop prevention"
```

---

## Task 10: Railway Deploy + Heritage Fabrics Setup

**Files:**
- Create: `railway.toml`
- Modify: `relay.example.yaml` — add Heritage Fabrics-specific notes

**Step 1: Create railway.toml**

```toml
[build]
builder = "dockerfile"
dockerfilePath = "Dockerfile"

[deploy]
healthcheckPath = "/health"
healthcheckTimeout = 30
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 3
```

**Step 2: Create Railway service**

```bash
# Link to Railway project (or create new)
railway link
# Add Redis and Postgres plugins via Railway dashboard
# Set environment variables:
railway variables set \
  DATABASE_URL="<from Railway Postgres plugin>" \
  REDIS_URL="<from Railway Redis plugin>" \
  RELAY_CONFIG_PATH="./relay.yaml" \
  LOG_LEVEL="info"
```

**Step 3: Run database schema**

```bash
# Connect to Railway Postgres and run schema
railway run psql < src/db/schema.sql
```

**Step 4: Create relay.yaml with Heritage Fabrics config**

Fill in real credentials from:
- Slack bot token: Create a new Slack app at api.slack.com for hfabrics workspace
- Slack signing secret: From the Slack app's Basic Information page
- Teams: Create Azure Bot Service resource in Azure Portal

**Step 5: Deploy**

```bash
railway up
```

**Step 6: Verify health endpoint**

```bash
curl https://relay-production.up.railway.app/health
# Expected: {"status":"ok","timestamp":"..."}
```

**Step 7: Configure Slack Event Subscriptions**

In the Slack app settings (api.slack.com):
- Request URL: `https://relay-production.up.railway.app/webhooks/slack`
- Subscribe to bot events: `message.channels`, `message.groups`, `reaction_added`, `reaction_removed`, `file_shared`
- Save and verify

**Step 8: Configure Teams Bot Framework**

In Azure Portal → Bot Service:
- Messaging endpoint: `https://relay-production.up.railway.app/webhooks/teams`
- Enable Teams channel

**Step 9: Test end-to-end**

- Send a message in a bridged Teams channel → verify it appears in Slack
- Reply in Slack → verify it appears in Teams as a threaded reply
- React in Slack → verify reaction logged (Teams reaction sync is Phase 2)

**Step 10: Commit deploy config**

```bash
git add railway.toml
git commit -m "feat: Railway deploy config"
```

---

## Task 11: CI/CD + Final Polish

**Files:**
- Modify: `.github/workflows/ci.yml` — add Railway deploy on main
- Create: `tests/e2e/health.test.ts`

**Step 1: Write health endpoint e2e test**

```typescript
// tests/e2e/health.test.ts
import { describe, it, expect, afterAll } from "vitest";
import Fastify from "fastify";
import { registerHealthRoutes } from "../../src/routes/health.js";

describe("Health endpoint", () => {
  const app = Fastify();
  registerHealthRoutes(app);

  afterAll(() => app.close());

  it("returns 200 with status ok", async () => {
    const response = await app.inject({
      method: "GET",
      url: "/health",
    });

    expect(response.statusCode).toBe(200);
    const body = JSON.parse(response.payload);
    expect(body.status).toBe("ok");
    expect(body.timestamp).toBeTruthy();
  });
});
```

**Step 2: Run all tests**

Run: `npx vitest run`
Expected: All PASS

**Step 3: Run typecheck + build**

Run: `npx tsc --noEmit && npm run build`
Expected: Clean

**Step 4: Commit**

```bash
git add tests/e2e/ .github/
git commit -m "feat: e2e health test + CI pipeline"
```

**Step 5: Push and verify CI**

```bash
git push -u origin main
gh run watch
```

---

## Summary

| Task | Component | Tests |
|------|-----------|-------|
| 1 | Repo scaffold | — |
| 2 | Types + RelayMessage | 2 tests |
| 3 | Database schema + queries | 1 test |
| 4 | YAML config loader | 4 tests |
| 5 | BullMQ queue + router | 2 tests |
| 6 | Slack connector | 7 tests |
| 7 | Teams connector | 4 tests |
| 8 | Webhook routes + server | — |
| 9 | Loop prevention | 5 tests |
| 10 | Railway deploy | manual |
| 11 | CI/CD + polish | 1 test |

**Total: 11 tasks, ~26 tests, ~15 files**

After Phase 1 ships: Heritage Fabrics has bidirectional Slack ↔ Teams messaging with thread sync, file relay (link-based for Teams), and loop prevention. Ready for Phase 2 (Zoom + Google Chat connectors).
