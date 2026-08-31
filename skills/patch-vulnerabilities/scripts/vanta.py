#!/usr/bin/env python3
"""
Vanta API helper for the patch-vulnerabilities skill.

Self-contained (Python 3 stdlib only). Authenticates with the OAuth credentials
in ~/.vanta-credentials.json and exposes the read/write operations the skill needs,
so the skill no longer depends on Notion.

Subcommands
-----------
  list        List active vulnerabilities, enriched with the resolved repo/registry.
              Flags: --severity {LOW,MEDIUM,HIGH,CRITICAL}
                     --sla-before YYYY-MM-DD     (only vulns whose SLA is before date)
                     --include-deactivated       (also include already-deactivated)
                     --pretty                    (indented JSON)
  assets      Dump the resolved vulnerable-assets map (debug).
  deactivate  Deactivate (justify) one or more vulnerabilities.
              Flags: --reason "<text>"            (required, free-form)
                     --id ID  (repeatable, required)
                     --no-reactivate-when-fixable (default: reactivate when fixable)
  reactivate  Reactivate one or more vulnerabilities.  Flags: --id ID (repeatable)

Examples
--------
  python3 vanta.py list --severity HIGH --pretty
  python3 vanta.py deactivate --reason "No hay fix en Debian Trixie" --id 68b2... --id 68b3...
  python3 vanta.py reactivate --id 68b2...

Exit codes: 0 success; 1 usage/credential error; 2 if any per-item write returned ERROR.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

# An uncorrelated finding whose SLA is overdue or within this many days is flagged
# as "due soon" so the skill can warn the user about it.
SLA_SOON_DAYS = 14


def days_until(iso):
    """Whole days from now until an ISO timestamp (negative = overdue). None if absent.

    Floors, so a deadline less than a day past due still reports negative and a partial
    day remaining rounds down. Both keep the SLA warning on the conservative side.
    """
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (dt - datetime.now(timezone.utc)).days

BASE_URL = os.environ.get("VANTA_BASE_URL", "https://api.vanta.com")
SCOPES = os.environ.get("VANTA_SCOPES", "vanta-api.all:read vanta-api.all:write")
CREDENTIALS_PATH = os.environ.get(
    "VANTA_CREDENTIALS_PATH", os.path.expanduser("~/.vanta-credentials.json")
)

SOURCE_LABELS = {"github": "GitHub", "aws": "AWS", "gcp": "GCP", "azure": "Azure"}


def die(msg, code=1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def load_credentials():
    try:
        with open(CREDENTIALS_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        die(f"credentials not found at {CREDENTIALS_PATH}")
    except json.JSONDecodeError:
        die(f"credentials at {CREDENTIALS_PATH} is not valid JSON")
    if not data.get("client_id") or not data.get("client_secret"):
        die(f"credentials at {CREDENTIALS_PATH} must contain client_id and client_secret")
    return data["client_id"], data["client_secret"]


def _request(method, url, token=None, body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            parsed = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = {"message": raw}
        return exc.code, parsed
    except urllib.error.URLError as exc:
        die(f"network error contacting Vanta: {exc.reason}")


_token_cache = {"value": None}


def get_token():
    if _token_cache["value"]:
        return _token_cache["value"]
    client_id, client_secret = load_credentials()
    status, body = _request(
        "POST",
        f"{BASE_URL}/oauth/token",
        body={
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": SCOPES,
            "grant_type": "client_credentials",
        },
    )
    if status != 200 or not body or "access_token" not in body:
        die(f"token request failed ({status}): {json.dumps(body)}")
    _token_cache["value"] = body["access_token"]
    return _token_cache["value"]


def get_paginated(path, query=None):
    """Yield every item across all pages of a list endpoint."""
    token = get_token()
    cursor = None
    for _ in range(200):  # hard cap against runaway pagination
        params = dict(query or {})
        params["pageSize"] = 100
        if cursor:
            params["pageCursor"] = cursor
        qs = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
        status, body = _request("GET", f"{BASE_URL}{path}?{qs}", token=token)
        if status != 200:
            die(f"GET {path} failed ({status}): {json.dumps(body)}")
        results = (body or {}).get("results", {})
        for item in results.get("data", []):
            yield item
        page_info = results.get("pageInfo", {})
        if not page_info.get("hasNextPage") or not page_info.get("endCursor"):
            break
        cursor = page_info["endCursor"]


def build_asset_map():
    """Map assetId -> asset, for resolving a vulnerability's targetId."""
    return {a["id"]: a for a in get_paginated("/v1/vulnerable-assets")}


def resolve_location(vuln, asset_map):
    """
    Resolve where a vulnerability lives. Returns a dict with:
      source, assetType, repo (github org/repo), registry (container repo path),
      registryAccount (account/region or project), assetName, assetResolved.
    """
    source = vuln.get("integrationId") or "unknown"
    target_id = vuln.get("targetId")
    asset = asset_map.get(target_id) if target_id else None

    loc = {
        "source": source,
        "sourceLabel": SOURCE_LABELS.get(source, source.upper()),
        "assetType": None,
        "assetName": None,
        "repo": None,
        "registry": None,
        "registryAccount": None,
        "assetResolved": asset is not None,
    }
    if not asset:
        return loc

    scanners = asset.get("scanners") or []
    scanner = next((s for s in scanners if s.get("integrationId") == source), None)
    if scanner is None and scanners:
        scanner = scanners[0]
    org = scanner.get("parentAccountOrOrganization") if scanner else None

    loc["assetType"] = asset.get("assetType")
    loc["assetName"] = asset.get("name")

    if asset.get("assetType") == "CODE_REPOSITORY":
        loc["repo"] = f"{org}/{asset.get('name')}" if org else asset.get("name")
    else:  # CONTAINER_REPOSITORY or other registries
        loc["registry"] = asset.get("name")
        loc["registryAccount"] = org
    return loc


def cmd_list(args):
    asset_map = build_asset_map()
    query = {}
    if not args.include_deactivated:
        query["isDeactivated"] = "false"
    if args.severity:
        query["severity"] = args.severity
    if args.sla_before:
        # API expects an ISO timestamp; accept a bare date and pin to end of day.
        query["slaDeadlineBeforeDate"] = f"{args.sla_before}T23:59:59Z"

    out = []
    for v in get_paginated("/v1/vulnerabilities", query):
        loc = resolve_location(v, asset_map)
        sla_days = days_until(v.get("remediateByDate"))
        out.append(
            {
                "id": v.get("id"),
                "cve": v.get("name"),
                "package": v.get("packageIdentifier"),
                "severity": v.get("severity"),
                "source": loc["source"],
                "repo": loc["repo"],
                "registry": loc["registry"],
                "registryAccount": loc["registryAccount"],
                "assetType": loc["assetType"],
                "assetName": loc["assetName"],
                "assetResolved": loc["assetResolved"],
                "isFixable": v.get("isFixable"),
                "fixedVersion": v.get("fixedVersion"),
                "remediateByDate": v.get("remediateByDate"),
                "daysUntilSla": sla_days,
                "slaDueSoon": sla_days is not None and sla_days <= SLA_SOON_DAYS,
                "isDeactivated": v.get("deactivateMetadata") is not None,
                "externalURL": v.get("externalURL"),
                "relatedUrls": v.get("relatedUrls"),
            }
        )
    print(json.dumps(out, indent=2 if args.pretty else None))


def cmd_assets(args):
    asset_map = build_asset_map()
    print(json.dumps(list(asset_map.values()), indent=2 if args.pretty else None))


def _post_updates(path, updates):
    token = get_token()
    status, body = _request("POST", f"{BASE_URL}{path}", token=token, body={"updates": updates})
    print(json.dumps(body, indent=2))
    results = (body or {}).get("results", []) if isinstance(body, dict) else []
    errored = [r for r in results if r.get("status") == "ERROR"]
    if status >= 400 or errored:
        sys.exit(2)


def cmd_deactivate(args):
    if not args.id:
        die("at least one --id is required")
    if not args.reason or not args.reason.strip():
        die("--reason is required")
    updates = [
        {
            "id": vid,
            "deactivateReason": args.reason.strip(),
            "shouldReactivateWhenFixable": not args.no_reactivate_when_fixable,
        }
        for vid in args.id
    ]
    _post_updates("/v1/vulnerabilities/deactivate", updates)


def cmd_reactivate(args):
    if not args.id:
        die("at least one --id is required")
    _post_updates("/v1/vulnerabilities/reactivate", [{"id": vid} for vid in args.id])


def main():
    parser = argparse.ArgumentParser(description="Vanta API helper for patch-vulnerabilities")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="list active vulnerabilities (enriched)")
    p_list.add_argument("--severity", choices=["LOW", "MEDIUM", "HIGH", "CRITICAL"])
    p_list.add_argument("--sla-before", metavar="YYYY-MM-DD")
    p_list.add_argument("--include-deactivated", action="store_true")
    p_list.add_argument("--pretty", action="store_true")
    p_list.set_defaults(func=cmd_list)

    p_assets = sub.add_parser("assets", help="dump resolved vulnerable-assets")
    p_assets.add_argument("--pretty", action="store_true")
    p_assets.set_defaults(func=cmd_assets)

    p_deact = sub.add_parser("deactivate", help="deactivate vulnerabilities")
    p_deact.add_argument("--reason", required=True)
    p_deact.add_argument("--id", action="append", default=[])
    p_deact.add_argument("--no-reactivate-when-fixable", action="store_true")
    p_deact.set_defaults(func=cmd_deactivate)

    p_react = sub.add_parser("reactivate", help="reactivate vulnerabilities")
    p_react.add_argument("--id", action="append", default=[])
    p_react.set_defaults(func=cmd_reactivate)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
