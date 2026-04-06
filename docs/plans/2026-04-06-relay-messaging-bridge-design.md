# Relay — Unified Messaging Bridge

**Date:** 2026-04-06
**Status:** Approved
**Product:** Relay by Studio B AI
**Repo:** `studio-b-ai/relay` (new, standalone)
**Hosting:** Railway

## Problem

Small and mid-market businesses use multiple messaging platforms (Slack, Microsoft Teams, Zoom Chat, Google Chat). Messages get missed, context gets fragmented, and people waste time checking multiple apps. Heritage Fabrics experiences this daily — vendors message on Teams, internal ops runs on Slack, some partners use Zoom or Google Chat.

Existing solutions (Mio, Sameroom) are $5-10/user/month SaaS products with limited customization. Studio B wants to build this as a product: dogfood it on Heritage Fabrics, then sell to the Acumatica VAR channel and broader SMB market.

## Solution

Relay is a multi-tenant, bidirectional messaging bridge. It consolidates messages from Microsoft Teams, Zoom Chat, Google Chat, and multiple Slack workspaces into a unified view. Messages, threads, reactions, and files sync across all connected platforms in real time.

Key differentiator: Relay treats every platform as a peer. Slack is the recommended hub, but no platform is privileged in the architecture. Multiple instances of the same platform (e.g., two Slack workspaces) are first-class citizens.

## Architecture

Event-driven worker pattern with platform-specific connectors.

```
                         ┌──────────────┐
[Slack WS 1] ←→ [Connector] ──→ │              │ ──→ [Connector] ←→ [Teams]
[Slack WS 2] ←→ [Connector] ──→ │  BullMQ      │ ──→ [Connector] ←→ [Zoom]
                         │  Router      │
[Google Chat] ←→ [Connector] ──→ │              │ ──→ [Connector] ←→ [Future]
                         └──────────────┘
                               ↕
                           [Postgres]
                         (config, refs)
```

### Components

| Component | Purpose |
|-----------|---------|
| API Server | REST API for tenant config, channel mappings, health. Serves webhook endpoints for each platform. |
| Connectors | Platform-specific adapters. Each handles auth, webhook ingestion, message sending, and format translation. |
| Router | BullMQ worker. Reads inbound messages, resolves channel mappings, transforms format, dispatches to target connectors. |
| Store | Postgres for tenant config, channel mappings, message ID cross-references. Redis for queue + ephemeral state. |

### Tech Stack

- **Runtime:** Node.js + TypeScript
- **Framework:** Fastify
- **Queue:** BullMQ on Redis
- **DB:** Postgres (Railway managed)
- **File Storage:** Cloudflare R2 (intermediate storage for file relay)
- **Hosting:** Railway

## Connector Interface

Each connector implements a common interface:

```typescript
interface Connector {
  name: string
  // Inbound: parse platform webhook → RelayMessage
  parseWebhook(req: FastifyRequest): Promise<RelayMessage | null>
  // Outbound: send RelayMessage → platform API
  sendMessage(msg: RelayMessage, mapping: ChannelMapping): Promise<PlatformMessageRef>
  // Sync: threads, reactions, file transfers
  syncReaction(msg: RelayReaction, mapping: ChannelMapping): Promise<void>
  syncFile(file: RelayFile, mapping: ChannelMapping): Promise<string>
  // Auth
  validateCredentials(creds: PlatformCredentials): Promise<boolean>
}
```

### Platform Details

**Slack**
- Inbound: Events API (message, reaction_added, reaction_removed, file_shared)
- Outbound: Web API (chat.postMessage, reactions.add, files.upload)
- Auth Phase 1: Bot token + signing secret. Phase 2: OAuth app install flow.
- Identity: Messages from other platforms appear as Relay bot with sender's name/avatar via `username` + `icon_url` params.
- Multiple workspaces supported — each workspace is a separate connection with its own bot token.

**Microsoft Teams**
- Inbound: Bot Framework webhook (Azure Bot Service). Receives message, messageReaction, fileConsent activities.
- Outbound: Microsoft Graph API (`/teams/{id}/channels/{id}/messages`)
- Auth Phase 1: Azure AD app registration + bot token. Phase 2: Teams app manifest for marketplace.
- Requires Azure Bot Service resource — cannot receive raw webhooks.

**Zoom Chat**
- Inbound: Zoom Webhook (Event Subscriptions for chat_message.sent, reaction.added)
- Outbound: Zoom Chat API (`/chat/users/{userId}/messages`)
- Auth Phase 1: Server-to-Server OAuth app. Phase 2: Zoom Marketplace app.
- Rate limits: 10 req/sec. Queue backpressure handles this.

**Google Chat**
- Inbound: Google Chat API via Pub/Sub push or HTTP bot events.
- Outbound: Google Chat API (`spaces.messages.create`)
- Auth Phase 1: Service account + Chat API enabled in Google Workspace. Phase 2: Google Workspace Marketplace app.
- Production event delivery requires Pub/Sub topic.

## Message Envelope

```typescript
interface RelayMessage {
  id: string                    // Relay's internal ID
  tenantId: string
  sourcePlatform: Platform      // 'slack' | 'teams' | 'zoom' | 'google_chat'
  sourceConnectionId: string    // FK to platform_connections (distinguishes instances)
  sourceChannelId: string       // Platform-native channel ID
  sourceMessageId: string       // Platform-native message ID
  sourceThreadId?: string       // For threaded replies
  sender: {
    displayName: string
    avatarUrl?: string
    platformUserId: string
  }
  content: {
    text: string                // Plain text
    markdown?: string           // Rich text (platform-native markdown)
    html?: string               // For platforms that use HTML (Teams)
  }
  attachments: RelayFile[]
  replyTo?: string              // Relay message ID this is replying to
  timestamp: Date
}
```

## Data Model

### tenants
```
id              UUID PK
name            text            -- "Heritage Fabrics"
slug            text UNIQUE     -- "heritage-fabrics"
api_key         text            -- for API auth
plan            text            -- 'free' | 'pro' | 'enterprise'
created_at      timestamp
```

### platform_connections
```
id              UUID PK
tenant_id       UUID FK → tenants
platform        text            -- 'slack' | 'teams' | 'zoom' | 'google_chat'
instance        text            -- distinguishes multiple connections on same platform
                                -- e.g., 'hfabrics' vs 'studiob' for two Slack workspaces
                                -- nullable, defaults to platform name
credentials     jsonb           -- encrypted bot tokens, OAuth tokens, signing secrets
status          text            -- 'active' | 'expired' | 'error'
metadata        jsonb           -- team/workspace name, bot user ID, etc.
created_at      timestamp
UNIQUE(tenant_id, platform, instance)
```

### channel_mappings
```
id              UUID PK
tenant_id       UUID FK → tenants
relay_channel   text            -- logical group name, e.g. "operations"
created_at      timestamp
```

### channel_mapping_endpoints
```
id              UUID PK
mapping_id      UUID FK → channel_mappings
connection_id   UUID FK → platform_connections
platform_channel_id   text      -- native channel ID
platform_channel_name text      -- human-readable
created_at      timestamp
UNIQUE(mapping_id, connection_id, platform_channel_id)
```

### message_refs
```
id              UUID PK
tenant_id       UUID FK → tenants
relay_message_id    text        -- Relay's internal message ID
mapping_id      UUID FK → channel_mappings
connection_id   UUID FK → platform_connections
platform_message_id text        -- native message ID (Slack ts, Teams messageId)
platform_thread_id  text        -- native thread root ID (nullable)
created_at      timestamp
INDEX(relay_message_id)
INDEX(connection_id, platform_message_id)
```

### file_refs
```
id              UUID PK
relay_message_id    text
original_connection_id UUID FK → platform_connections
original_url    text
stored_url      text            -- R2 intermediate storage URL
platform_urls   jsonb           -- { "slack:hfabrics": "https://...", "teams": "https://..." }
mime_type       text
size_bytes      integer
created_at      timestamp
```

### Channel Mapping Config (Phase 1 — YAML)

```yaml
tenant: heritage-fabrics
platform_connections:
  - platform: slack
    instance: hfabrics
    credentials: { bot_token: "xoxb-hf-..." }
  - platform: slack
    instance: studiob
    credentials: { bot_token: "xoxb-sb-..." }
  - platform: teams
    instance: default
    credentials: { bot_id: "...", bot_password: "..." }

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

## Message Flow

### Inbound (Teams → Slack example)

1. Teams sends webhook to `POST /webhooks/teams/:tenantId`
2. Teams connector validates Bot Framework JWT
3. Connector normalizes to RelayMessage envelope
4. RelayMessage published to BullMQ queue `relay:inbound`
5. Router worker picks it up, looks up channel mapping (Teams channel → relay channel → all other endpoints)
6. For each target endpoint, a dispatch job is enqueued to `relay:outbound:{platform}`
7. Slack connector formats message (username, avatar, attachments) and posts via Slack API
8. Message ID cross-reference stored in `message_refs`

### Thread Sync

1. Zoom user replies to a message in a thread
2. Zoom webhook includes parent message ID
3. Look up `message_refs` WHERE `connection_id=zoom AND platform_message_id=parentId` → get `relay_message_id`
4. Look up all other `message_refs` with that `relay_message_id` → get Slack `ts`, Teams `messageId`, etc.
5. Post reply as threaded reply on each platform using their native thread ID

### File Relay

1. Source connector detects file attachment
2. File downloaded from source platform (auth-gated URLs require platform credentials)
3. File uploaded to Cloudflare R2 intermediate storage
4. For each target platform, file re-uploaded via their API
5. Platform-specific URLs stored in `file_refs.platform_urls`

## Loop Prevention

Critical for bidirectional bridges.

1. **Origin tag:** Every outbound message includes `relay-origin` metadata (Slack: message metadata, Teams: adaptive card hidden field, Zoom/GChat: custom properties)
2. **Inbound filter:** Webhook handler checks for origin tag — if present, message is dropped
3. **Dedup backup:** Content hash + sender + timestamp within 5-second window catches edge cases
4. **Bot self-filter:** Each connector ignores messages from its own bot user ID

## Error Handling & Reliability

### Queue Retry Strategy

| Attempt | Delay | Notes |
|---------|-------|-------|
| 1 | Immediate | First try |
| 2 | 5s | Transient network blip |
| 3 | 30s | Platform API hiccup |
| 4 | 2min | Rate limit cooldown |
| 5 | 10min | Platform outage |
| Dead letter | — | After 5 failures, move to DLQ |

### Typed Errors

- **RateLimitError** — backoff using platform's `Retry-After` header
- **AuthError** — mark `platform_connections.status = 'expired'`, notify tenant
- **PlatformDownError** — retry with backoff
- **MessageTooLargeError** — truncate + attach full content as file
- **UnknownError** — retry, then DLQ

### Partial Delivery

Each platform dispatch is an independent job. Failures on one platform don't block others. DLQ captures which platform/message failed.

### Webhook Verification

- **Slack:** HMAC-SHA256 with signing secret
- **Teams:** JWT validation via Bot Framework
- **Zoom:** HMAC-SHA256 with webhook secret + CRC challenge/response
- **Google Chat:** Bearer token verification against Google's public keys

### Idempotency

- `message_refs` table deduplicates — if `(connection_id, platform_message_id)` exists, skip
- Queue jobs keyed by `${connectionId}:${platformMessageId}` — BullMQ deduplicates by job ID

### Monitoring

- Health endpoint per connector (API reachability + token validity)
- Metrics: messages relayed/min, queue depth, error rate by platform, DLQ size
- Alerts via direct Slack API (not through Relay — avoid dependency loop):
  - Connector auth expired
  - DLQ depth > 10
  - Queue latency > 30s

## Phasing

### Phase 1: Heritage Fabrics MVP (Slack ↔ Teams)

- Slack connector (Events API + Web API)
- Teams connector (Bot Framework + Graph API)
- Router with BullMQ
- Postgres config + message refs
- YAML-based channel config
- Text + formatting + @mention mapping
- Thread cross-referencing
- File relay via R2
- Reaction sync
- Loop prevention
- Deploy on Railway

Heritage Fabrics is tenant #1. Start with 1-2 bridged channels, validate for a week, expand.

### Phase 2: Zoom + Google Chat + Multi-Workspace

- Zoom Chat connector
- Google Chat connector
- Multi-Slack-workspace support (instance field)
- Edit and delete sync
- Presence/status sync (online/away/DND)

### Phase 3: Multi-Tenant + Config Dashboard

- Tenant onboarding API
- Web dashboard (channel mappings, connection status, message stats)
- OAuth app install flows for each platform
- Per-tenant queue namespacing
- Usage metering

### Phase 4: Productize

- Landing page at relay.studiob.ai
- Stripe billing
- Marketplace submissions (Slack, Teams, Zoom, Google Workspace)
- Self-serve signup → OAuth install → channel mapping wizard
- Documentation + API reference
