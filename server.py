#!/usr/bin/env python3
"""Heritage Fabrics Acumatica MCP Server"""
import os
import json
import asyncio
import threading
import base64
import time
import httpx
from typing import Any
from dotenv import load_dotenv
from mcp.server import Server
from mcp import types

load_dotenv()

BASE_URL = os.getenv("ACUMATICA_BASE_URL", "https://heritagefabrics.acumatica.com")
USERNAME = os.getenv("ACUMATICA_USERNAME")
PASSWORD = os.getenv("ACUMATICA_PASSWORD")
COMPANY  = os.getenv("ACUMATICA_COMPANY", "Heritage Fabrics")
ENDPOINT = os.getenv("ACUMATICA_ENDPOINT", "default")
VERSION  = os.getenv("ACUMATICA_ENDPOINT_VERSION", "24.200.001")
MCP_AUTH_TOKEN = os.getenv("MCP_AUTH_TOKEN")
TRANSPORT = os.getenv("MCP_TRANSPORT", "sse")
API_BASE = f"{BASE_URL}/entity/{ENDPOINT}/{VERSION}"
CUSTOMIZATION_BASE = f"{BASE_URL}/CustomizationApi"

app = Server("acumatica-mcp")
_session = None
_session_lock = threading.Lock()

def get_session() -> httpx.Client:
    global _session
    with _session_lock:
        if _session is not None:
            return _session
        client = httpx.Client(timeout=60, follow_redirects=True)
        login_payload = {"name": USERNAME, "password": PASSWORD, "company": COMPANY}
        r = client.post(f"{BASE_URL}/entity/auth/login", json=login_payload)
        r.raise_for_status()
        _session = client
        return _session

def acumatica_get(path: str, params: dict = None) -> Any:
    s = get_session()
    url = path if path.startswith("http") else f"{API_BASE}/{path.lstrip('/')}"
    r = s.get(url, params=params)
    r.raise_for_status()
    if not r.content:
        return {}
    return r.json()

def acumatica_put(path: str, body: dict) -> Any:
    s = get_session()
    url = path if path.startswith("http") else f"{API_BASE}/{path.lstrip('/')}"
    r = s.put(url, json=body)
    r.raise_for_status()
    if not r.content:
        return {}
    return r.json()

def acumatica_post(path: str, body: dict) -> Any:
    s = get_session()
    url = path if path.startswith("http") else f"{API_BASE}/{path.lstrip('/')}"
    r = s.post(url, json=body)
    r.raise_for_status()
    if not r.content:
        return {}
    return r.json()

def acumatica_delete(path: str) -> Any:
    s = get_session()
    url = path if path.startswith("http") else f"{API_BASE}/{path.lstrip('/')}"
    r = s.delete(url)
    r.raise_for_status()
    if not r.content:
        return {}
    return r.json()

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="acumatica_list_entities",
            description="List all available REST API entities.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="acumatica_get_schema",
            description="Get schema for an entity.",
            inputSchema={"type": "object", "properties": {"entity": {"type": "string"}}, "required": ["entity"]},
        ),
        types.Tool(
            name="acumatica_current_user",
            description="Get current user info.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="acumatica_query",
            description="Query records.",
            inputSchema={"type": "object", "properties": {"entity": {"type": "string"}}, "required": ["entity"]},
        ),
        types.Tool(
            name="acumatica_get_record",
            description="Get a single record.",
            inputSchema={"type": "object", "properties": {"entity": {"type": "string"}, "key": {"type": "string"}}, "required": ["entity", "key"]},
        ),
        types.Tool(
            name="acumatica_create_record",
            description="Create a record.",
            inputSchema={"type": "object", "properties": {"entity": {"type": "string"}, "fields": {"type": "object"}}, "required": ["entity", "fields"]},
        ),
        types.Tool(
            name="acumatica_update_record",
            description="Update a record.",
            inputSchema={"type": "object", "properties": {"entity": {"type": "string"}, "key": {"type": "string"}, "fields": {"type": "object"}}, "required": ["entity", "key", "fields"]},
        ),
        types.Tool(
            name="acumatica_create_sales_order",
            description=(
                "Create a Sales Order in Acumatica. Builds a well-typed SO payload including "
                "customer, line items, and an optional Note (visible in the Sales Order Notes "
                "panel) sourced from a customer comments field on the samples request form."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "customer_id": {
                        "type": "string",
                        "description": "Acumatica customer account ID (e.g., 'C000123')",
                    },
                    "order_type": {
                        "type": "string",
                        "description": "Sales order type code (default: 'SO')",
                    },
                    "description": {
                        "type": "string",
                        "description": "Short order description / external reference",
                    },
                    "line_items": {
                        "type": "array",
                        "description": "Line items for the order",
                        "items": {
                            "type": "object",
                            "properties": {
                                "inventory_id": {"type": "string"},
                                "quantity":     {"type": "number"},
                                "warehouse_id": {"type": "string"},
                            },
                            "required": ["inventory_id", "quantity"],
                        },
                    },
                    "comments": {
                        "type": "string",
                        "description": (
                            "Optional free-text customer comment from the samples request form. "
                            "When present this is written to the Note field on the Sales Order "
                            "so warehouse staff can see it without opening a custom field."
                        ),
                    },
                },
                "required": ["customer_id", "line_items"],
            },
        ),

        # ─── Customization API Tools ──────────────────────────────────────
        types.Tool(
            name="acumatica_customization_export",
            description="Export (download) an existing Acumatica customization project as a base64-encoded .zip package. Returns the project content that can be saved or used for CI/CD.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_name": {
                        "type": "string",
                        "description": "The exact name of the customization project as it appears in Acumatica Customization Projects list"
                    }
                },
                "required": ["project_name"]
            },
        ),
        types.Tool(
            name="acumatica_customization_import",
            description="Import (upload) a customization project package into Acumatica. Accepts a base64-encoded .zip file. This uploads but does NOT publish — call acumatica_customization_publish separately to activate.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_name": {
                        "type": "string",
                        "description": "Name for the customization project in Acumatica"
                    },
                    "project_content_base64": {
                        "type": "string",
                        "description": "Base64-encoded .zip package content"
                    },
                    "project_description": {
                        "type": "string",
                        "description": "Optional description for the project (default: auto-generated with timestamp)"
                    },
                    "replace_if_exists": {
                        "type": "boolean",
                        "description": "Whether to overwrite if project already exists (default: true)"
                    }
                },
                "required": ["project_name", "project_content_base64"]
            },
        ),
        types.Tool(
            name="acumatica_customization_publish",
            description="Publish one or more customization projects in Acumatica. WARNING: Publishing restarts the Acumatica app pool and terminates all active user sessions. Always include ALL active customization project names to enable conflict detection. Returns immediately — use acumatica_customization_publish_status to poll for completion.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of ALL customization project names to publish together. MUST include every active project for proper conflict detection."
                    },
                    "validation_only": {
                        "type": "boolean",
                        "description": "If true, only validates without actually publishing (default: false)"
                    },
                    "merge_with_existing": {
                        "type": "boolean",
                        "description": "Merge with existing published packages (default: false)"
                    }
                },
                "required": ["project_names"]
            },
        ),
        types.Tool(
            name="acumatica_customization_publish_status",
            description="Check the status of an ongoing customization publish operation. Call this after acumatica_customization_publish to poll until completion. Returns isCompleted, isFailed, or inProgress.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            },
        ),
        types.Tool(
            name="acumatica_customization_list",
            description="List all customization projects currently in the Acumatica instance with their publish status.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        result = await asyncio.to_thread(_dispatch, name, arguments)
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    except Exception as e:
        return [types.TextContent(type="text", text=json.dumps({"error": str(e)}, indent=2))]


def _build_sales_order_payload(args: dict) -> dict:
    """
    Construct the Acumatica contract-based REST API payload for a Sales Order.

    Key fields
    ----------
    Note
        Written from the ``comments`` arg when truthy. Acumatica's Default
        endpoint (24.200.001) exposes the entity-level note as ``Note`` at the
        top level of the SalesOrder entity — the same field visible in the
        Notes panel (📎) on SO301000.  We prefix the raw comment with a
        human-readable label so warehouse staff immediately know the source.

    If a ``description`` is also supplied we leave it in ``Description``
    (the short header field) and do *not* overwrite it with the comment —
    both fields coexist independently on the order.
    """
    order_type = args.get("order_type", "SO")

    payload: dict = {
        "OrderType":  {"value": order_type},
        "CustomerID": {"value": args["customer_id"]},
    }

    if args.get("description"):
        payload["Description"] = {"value": args["description"]}

    # ── Note / customer comments ──────────────────────────────────────────
    # Only include the Note field when the caller supplied a non-empty comment.
    # Prefix makes the provenance clear to anyone reading the order in Acumatica.
    comments: str = (args.get("comments") or "").strip()
    if comments:
        payload["Note"] = {"value": f"Customer comment from samples form: {comments}"}

    # ── Line items ────────────────────────────────────────────────────────
    details = []
    for item in args.get("line_items", []):
        line: dict = {
            "InventoryID": {"value": item["inventory_id"]},
            "Quantity":    {"value": item["quantity"]},
        }
        if item.get("warehouse_id"):
            line["WarehouseID"] = {"value": item["warehouse_id"]}
        details.append(line)

    if details:
        payload["Details"] = details

    return payload


def _create_sales_order(args: dict) -> Any:
    """Create a Sales Order via the Acumatica contract-based REST endpoint."""
    payload = _build_sales_order_payload(args)
    return acumatica_put("SalesOrder", payload)


def _dispatch(name: str, args: dict) -> Any:

    if name == "acumatica_current_user":
        return {"status": "connected"}

    if name == "acumatica_list_entities":
        return acumatica_get("")

    if name == "acumatica_get_schema":
        return acumatica_get(args["entity"])

    if name == "acumatica_query":
        entity = args["entity"]
        params = {}
        if args.get("filter"):
            params["$filter"] = args["filter"]
        return acumatica_get(entity, params)

    if name == "acumatica_get_record":
        return acumatica_get(f"{args['entity']}/{args['key']}")

    if name == "acumatica_create_record":
        return acumatica_put(args["entity"], args["fields"])

    if name == "acumatica_update_record":
        return acumatica_put(f"{args['entity']}/{args['key']}", args["fields"])

    if name == "acumatica_create_sales_order":
        return _create_sales_order(args)

    # --- CUSTOMIZATION API: EXPORT ---
    if name == "acumatica_customization_export":
        project_name = args["project_name"]
        s = get_session()
        r = s.get(f"{CUSTOMIZATION_BASE}/export", params={"projectName": project_name})
        r.raise_for_status()
        return {
            "project_name": project_name,
            "content_base64": r.text.strip('"'),
            "size_bytes": len(r.content),
            "status": "exported"
        }

    # --- CUSTOMIZATION API: IMPORT ---
    if name == "acumatica_customization_import":
        project_name = args["project_name"]
        project_content = args["project_content_base64"]
        description = args.get("project_description", f"Imported via MCP at {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
        replace = args.get("replace_if_exists", True)
        s = get_session()
        payload = {
            "projectName": project_name,
            "projectDescription": description,
            "projectLevel": 0,
            "isReplaceIfExists": replace,
            "projectContent": project_content,
        }
        r = s.put(f"{CUSTOMIZATION_BASE}/import", json=payload)
        r.raise_for_status()
        return {
            "project_name": project_name,
            "description": description,
            "replaced": replace,
            "status": "imported (not yet published)"
        }

    # --- CUSTOMIZATION API: PUBLISH ---
    if name == "acumatica_customization_publish":
        project_names = args["project_names"]
        validation_only = args.get("validation_only", False)
        merge = args.get("merge_with_existing", False)
        s = get_session()
        payload = {
            "isMergeWithExistingPackages": merge,
            "isOnlyValidation": validation_only,
            "isOnlyDbUpdates": False,
            "projectNames": project_names,
        }
        r = s.post(f"{CUSTOMIZATION_BASE}/publishBegin", json=payload)
        r.raise_for_status()
        return {
            "project_names": project_names,
            "validation_only": validation_only,
            "status": "publish_started",
            "message": "Publish initiated. Use acumatica_customization_publish_status to poll for completion. WARNING: App pool will restart when publish completes."
        }

    # --- CUSTOMIZATION API: PUBLISH STATUS ---
    if name == "acumatica_customization_publish_status":
        s = get_session()
        r = s.get(f"{CUSTOMIZATION_BASE}/publishEnd")
        r.raise_for_status()
        body = r.text.strip()
        # Response varies by Acumatica version:
        #   plain "true"/"false" or JSON {isCompleted, isFailed, log}
        if body == '"true"' or body == 'true':
            return {"status": "completed", "isCompleted": True, "isFailed": False}
        elif body == '"false"' or body == 'false':
            return {"status": "in_progress", "isCompleted": False, "isFailed": False}
        else:
            try:
                data = r.json()
                if isinstance(data, dict):
                    return {
                        "status": "completed" if data.get("isCompleted") else ("failed" if data.get("isFailed") else "in_progress"),
                        "isCompleted": data.get("isCompleted", False),
                        "isFailed": data.get("isFailed", False),
                        "log": data.get("log", ""),
                    }
            except Exception:
                pass
            return {"status": "unknown", "raw_response": body}

    # --- CUSTOMIZATION API: LIST PROJECTS ---
    if name == "acumatica_customization_list":
        s = get_session()
        r = s.get(f"{CUSTOMIZATION_BASE}/getPublishedProjectList")
        r.raise_for_status()
        projects = r.json() if r.content else []
        return {"projects": projects, "count": len(projects)}

    raise ValueError(f"Unknown tool: {name}")


if __name__ == "__main__":
    print("Server ready")
