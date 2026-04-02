"""GI health check for post-publish verification.

Probes known Generic Inquiries via the Acumatica REST API to detect
GI subsystem corruption (e.g. orphaned GIDesign rows that crash
PXGenericInqGrph+Definition on app pool restart).

404 = GI not configured in this environment (skip — not corruption)
500 = GI corrupted or app pool crash (fail — systemic issue)
"""

PROBE_GIS = [
    "InventoryAllocationDetail",
    "LotAvailability",
]

RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
RESET = "\033[0m"


def check_gi_health(session, base_url: str) -> bool:
    """Probe the GI subsystem by querying known GIs via REST API.

    Accepts either a requests.Session or an AcumaticaSession (from
    validate-publish.py). For AcumaticaSession, uses query_entity();
    for requests.Session, uses session.get() directly.

    Returns True if:
      - At least one GI responds with HTTP 200 (healthy), OR
      - All GIs return HTTP 404 (not configured in this env — not corruption)
    Returns False only if at least one GI returns 500+ (corruption signal).
    """
    base_url = base_url.rstrip("/")
    any_success = False
    any_server_error = False

    for gi_name in PROBE_GIS:
        try:
            # Support both AcumaticaSession (query_entity) and requests.Session (.get)
            if hasattr(session, "query_entity"):
                code, _body = session.query_entity(gi_name, top=1)
            else:
                resp = session.get(
                    f"{base_url}/entity/Default/24.200.001/{gi_name}",
                    params={"$top": "1"},
                    timeout=30,
                )
                code = resp.status_code

            if code == 200:
                print(f"{GREEN}[  OK  ]{RESET} GI probe: {gi_name} responded (HTTP 200)")
                any_success = True
            elif code == 404:
                # GI not configured in this environment — not a corruption signal
                print(f"{YELLOW}[ SKIP ]{RESET} GI probe: {gi_name} not found (HTTP 404) — GI not configured in this environment")
            elif code >= 500:
                print(f"{RED}[FAIL  ]{RESET} GI probe: {gi_name} server error (HTTP {code}) — possible GI corruption")
                any_server_error = True
            else:
                print(f"{RED}[FAIL  ]{RESET} GI probe: {gi_name} returned HTTP {code}")
                any_server_error = True
        except Exception as exc:
            print(f"{RED}[FAIL  ]{RESET} GI probe: {gi_name} error: {exc}")
            any_server_error = True

    if any_server_error:
        print(f"{RED}[FAIL  ]{RESET} GI SUBSYSTEM UNHEALTHY — server errors detected (possible PXGenericInqGrph corruption)")
        return False

    if any_success:
        print(f"{GREEN}[  OK  ]{RESET} GI subsystem healthy")
    else:
        print(f"{YELLOW}[ SKIP ]{RESET} GI subsystem — no GIs configured in this environment (all 404, not a corruption signal)")

    return True
