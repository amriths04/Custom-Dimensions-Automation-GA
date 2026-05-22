"""
register_ga4_definitions.py
Auto-register GA4 Custom Dimensions + Custom Metrics via the GA4 Admin API.

WHAT THIS DOES:
  1. Reads a definitions file describing your event parameters.
  2. Resolves each parameter into a Custom Dimension or Custom Metric.
  3. Checks GA4 for what is already registered (idempotent — never double-registers).
  4. Creates the missing definitions via the Admin API.
  5. Saves a manifest so re-runs stay clean.
  6. Tracks the 50-dimension / 50-metric quota and warns near the cap.

TWO WAYS TO PROVIDE DEFINITIONS (developer's choice):

  A) MANUAL  — explicit template (recommended for full control)
     Edit definitions.template.json and list each dimension/metric directly:
       {
         "custom_dimensions": [
           {"parameter_name": "difficulty", "display_name": "Difficulty",
            "description": "Board difficulty", "scope": "EVENT"}
         ],
         "custom_metrics": [
           {"parameter_name": "score", "display_name": "Score",
            "description": "Final score", "unit": "STANDARD", "scope": "EVENT"}
         ]
       }
     Run:  python register_ga4_definitions.py --input definitions.json --apply

  B) SCAN  — feed the output of a source-code scanner
     If you produced a discovered_events.json (event -> {param: type}) from a
     scanner, point --input at it. String/boolean params become dimensions,
     numeric params become metrics. Coordinate/debug params in SKIP_PARAMS are
     ignored so they don't burn quota.
     Run:  python register_ga4_definitions.py --input discovered_events.json --apply

SETUP (one-time):
  1. pip install -r requirements.txt
  2. Google Cloud Console -> select your Firebase/GA4 project
  3. Enable "Google Analytics Admin API"
  4. Create a Service Account -> grant "Editor" role on the GA4 property
  5. Download the JSON key
  6. Set env vars (or pass --key / --property):
       set GA4_KEY_PATH=C:\\path\\to\\service-account-key.json
       set GA4_PROPERTY_ID=properties/123456789

QUOTA LIMITS (hard caps per GA4 property):
  - Custom Dimensions: 50
  - Custom Metrics:    50

Usage:
  python register_ga4_definitions.py --input definitions.json            # dry run
  python register_ga4_definitions.py --input definitions.json --apply    # create
  python register_ga4_definitions.py --list                              # show registered
"""

import argparse
import json
import os
import sys
from pathlib import Path

# --- Params that are low-value coordinates / debug values (SCAN mode only) ----
# These would burn quota without adding analytical value.
SKIP_PARAMS = {
    "row", "column", "number",   # cell coordinates / raw input values
}

# --- Type mappings (SCAN mode only) -------------------------------------------
#   "string"  -> Custom Dimension  (categorical breakdown)
#   "boolean" -> Custom Dimension  (treated as "true"/"false")
#   "dynamic" -> Custom Dimension  (unknown -> safer as a dimension)
#   "int"/"float"/"number" -> Custom Metric (aggregatable number)
DIMENSION_TYPES = {"string", "boolean", "dynamic"}
METRIC_TYPES = {"int", "float", "number"}

VALID_SCOPES = {"EVENT", "USER"}
MANIFEST_FILE = Path(__file__).parent / "ga4_definitions_manifest.json"
QUOTA_CAP = 50
QUOTA_WARNING_THRESHOLD = 0.8  # warn at 80% of the cap


def _display_name(param: str) -> str:
    """Convert snake_case param to Title Case display name."""
    return param.replace("_", " ").title()


# --- Loading ------------------------------------------------------------------

def _load_manual(data: dict) -> tuple[list, list]:
    """
    Explicit manual format:
      {
        "custom_dimensions": [{"parameter_name", "display_name"?, "description"?, "scope"?}],
        "custom_metrics":    [{"parameter_name", "display_name"?, "description"?, "unit"?, "scope"?}]
      }
    """
    dims, metrics = [], []
    seen_dims, seen_metrics = set(), set()

    for entry in data.get("custom_dimensions", []):
        param = entry.get("parameter_name") or entry.get("param")
        if not param or param in seen_dims:
            continue
        seen_dims.add(param)
        scope = (entry.get("scope") or "EVENT").upper()
        if scope not in VALID_SCOPES:
            scope = "EVENT"
        dims.append((
            param,
            entry.get("display_name") or _display_name(param),
            entry.get("description") or f"Custom dimension for '{param}'",
            scope,
        ))

    for entry in data.get("custom_metrics", []):
        param = entry.get("parameter_name") or entry.get("param")
        if not param or param in seen_metrics:
            continue
        seen_metrics.add(param)
        scope = (entry.get("scope") or "EVENT").upper()
        if scope not in VALID_SCOPES:
            scope = "EVENT"
        metrics.append((
            param,
            entry.get("display_name") or _display_name(param),
            entry.get("description") or f"Custom metric for '{param}'",
            (entry.get("unit") or "STANDARD").upper(),
            scope,
        ))

    return dims, metrics


def _extract_scan_params(data: dict) -> dict:
    """
    Normalise scanner output into {event_name: {param: type}}.

    Format A (scanner): {"events": {"name": {"params": {"k": "type"}, ...}}}
    Format B (flat):    {"event_name": {"param": "type"}}
    """
    if "events" in data and isinstance(data["events"], dict):
        return {e: info.get("params", {}) for e, info in data["events"].items()}
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def _load_scan(data: dict) -> tuple[list, list]:
    """Infer dimensions/metrics from scanner output by param type."""
    events_params = _extract_scan_params(data)
    seen_dims, seen_metrics = set(), set()
    dims, metrics = [], []

    for event_name, params in events_params.items():
        for param, ptype in params.items():
            if param in SKIP_PARAMS:
                continue
            if ptype in DIMENSION_TYPES and param not in seen_dims:
                seen_dims.add(param)
                dims.append((
                    param, _display_name(param),
                    f"Param '{param}' — first seen in '{event_name}'", "EVENT",
                ))
            elif ptype in METRIC_TYPES and param not in seen_metrics:
                seen_metrics.add(param)
                metrics.append((
                    param, _display_name(param),
                    f"Param '{param}' — first seen in '{event_name}'",
                    "STANDARD", "EVENT",
                ))
    return dims, metrics


def load_definitions(path: Path) -> tuple[list, list, str]:
    """
    Auto-detect input format and return (dimensions, metrics, mode).
      dimension entry : (param, display, desc, scope)
      metric entry    : (param, display, desc, unit, scope)
    """
    if not path.exists():
        print(f"  ERROR: Input file not found: {path}")
        print(f"  Copy definitions.template.json to definitions.json and edit it,")
        print(f"  or point --input at a scanner's discovered_events.json.")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if "custom_dimensions" in data or "custom_metrics" in data:
        dims, metrics = _load_manual(data)
        return dims, metrics, "manual"

    dims, metrics = _load_scan(data)
    return dims, metrics, "scan"


# --- Manifest helpers ---------------------------------------------------------

def load_manifest() -> dict:
    if MANIFEST_FILE.exists():
        with open(MANIFEST_FILE) as f:
            return json.load(f)
    return {"dimensions": [], "metrics": []}


def save_manifest(manifest: dict) -> None:
    with open(MANIFEST_FILE, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"  Manifest saved: {MANIFEST_FILE.name}")


# --- GA4 Admin API helpers ----------------------------------------------------

def get_client(key_path: str | None):
    from google.analytics.admin import AnalyticsAdminServiceClient
    if key_path:
        return AnalyticsAdminServiceClient.from_service_account_file(key_path)
    return AnalyticsAdminServiceClient()  # uses GOOGLE_APPLICATION_CREDENTIALS


def list_existing(client, property_id: str) -> tuple[set, set]:
    """Returns (existing_dimension_param_names, existing_metric_param_names)."""
    existing_dims = {d.parameter_name for d in client.list_custom_dimensions(parent=property_id)}
    existing_metrics = {m.parameter_name for m in client.list_custom_metrics(parent=property_id)}
    return existing_dims, existing_metrics


def create_dimension(client, property_id, param, display, desc, scope) -> bool:
    from google.analytics.admin_v1alpha.types import CustomDimension
    scope_enum = getattr(CustomDimension.DimensionScope, scope, CustomDimension.DimensionScope.EVENT)
    try:
        client.create_custom_dimension(
            parent=property_id,
            custom_dimension=CustomDimension(
                parameter_name=param, display_name=display,
                description=desc, scope=scope_enum,
            ),
        )
        return True
    except Exception as e:
        print(f"    ERROR creating dimension '{param}': {e}")
        return False


def create_metric(client, property_id, param, display, desc, unit, scope) -> bool:
    from google.analytics.admin_v1alpha.types import CustomMetric
    unit_enum = getattr(CustomMetric.MeasurementUnit, unit, CustomMetric.MeasurementUnit.STANDARD)
    scope_enum = getattr(CustomMetric.MetricScope, scope, CustomMetric.MetricScope.EVENT)
    try:
        client.create_custom_metric(
            parent=property_id,
            custom_metric=CustomMetric(
                parameter_name=param, display_name=display, description=desc,
                measurement_unit=unit_enum, scope=scope_enum,
            ),
        )
        return True
    except Exception as e:
        print(f"    ERROR creating metric '{param}': {e}")
        return False


# --- Core logic ---------------------------------------------------------------

def check_deps() -> bool:
    try:
        import google.analytics.admin  # noqa
        return True
    except ImportError:
        print("\n  ERROR: google-analytics-admin not installed.")
        print("  Run:  pip install -r requirements.txt\n")
        return False


def run_dry(dims, metrics, manifest) -> None:
    print("\n  DRY RUN — nothing will be created (pass --apply to create)\n")
    already_dims = set(manifest["dimensions"])
    already_metrics = set(manifest["metrics"])

    print(f"  Custom Dimensions defined: {len(dims)}")
    for param, display, desc, scope in dims:
        status = "SKIP (in manifest)" if param in already_dims else "CREATE"
        print(f"    [{status:18}] {param}  ({scope})")

    print(f"\n  Custom Metrics defined: {len(metrics)}")
    for param, display, desc, unit, scope in metrics:
        status = "SKIP (in manifest)" if param in already_metrics else "CREATE"
        print(f"    [{status:18}] {param}  ({unit}, {scope})")

    to_dims = sum(1 for p, *_ in dims if p not in already_dims)
    to_mets = sum(1 for p, *_ in metrics if p not in already_metrics)
    print(f"\n  Would create: {to_dims} dimension(s), {to_mets} metric(s)")
    print(f"  Manifest quota: {to_dims + len(already_dims)}/{QUOTA_CAP} dims, "
          f"{to_mets + len(already_metrics)}/{QUOTA_CAP} metrics")
    print("\n  Run with --apply (and --key/--property) to create them.\n")


def run_list(client, property_id, dims, metrics) -> None:
    print(f"\n  Registered in GA4 property: {property_id}\n")
    existing_dims, existing_metrics = list_existing(client, property_id)
    schema_dims = {p for p, *_ in dims}
    schema_metrics = {p for p, *_ in metrics}

    print(f"  Custom Dimensions ({len(existing_dims)}/{QUOTA_CAP}):")
    for d in sorted(existing_dims) or []:
        tag = "" if d in schema_dims else "  <- not in local input"
        print(f"    {d}{tag}")
    if not existing_dims:
        print("    (none)")

    print(f"\n  Custom Metrics ({len(existing_metrics)}/{QUOTA_CAP}):")
    for m in sorted(existing_metrics) or []:
        tag = "" if m in schema_metrics else "  <- not in local input"
        print(f"    {m}{tag}")
    if not existing_metrics:
        print("    (none)")
    print()


def run_apply(client, property_id, dims, metrics, manifest) -> None:
    existing_dims, existing_metrics = list_existing(client, property_id)

    need_dims = sum(1 for p, *_ in dims if p not in existing_dims)
    need_mets = sum(1 for p, *_ in metrics if p not in existing_metrics)
    if (len(existing_dims) + need_dims) > QUOTA_CAP * QUOTA_WARNING_THRESHOLD:
        print(f"  WARNING: would bring dimensions to {len(existing_dims) + need_dims}/{QUOTA_CAP}")
    if (len(existing_metrics) + need_mets) > QUOTA_CAP * QUOTA_WARNING_THRESHOLD:
        print(f"  WARNING: would bring metrics to {len(existing_metrics) + need_mets}/{QUOTA_CAP}")

    print("\n  Creating Custom Dimensions...")
    dims_created = []
    for param, display, desc, scope in dims:
        if param in existing_dims:
            print(f"    SKIP  {param}  (already exists)")
            if param not in manifest["dimensions"]:
                manifest["dimensions"].append(param)
        elif create_dimension(client, property_id, param, display, desc, scope):
            print(f"    OK    {param}")
            dims_created.append(param)
            manifest["dimensions"].append(param)

    print("\n  Creating Custom Metrics...")
    mets_created = []
    for param, display, desc, unit, scope in metrics:
        if param in existing_metrics:
            print(f"    SKIP  {param}  (already exists)")
            if param not in manifest["metrics"]:
                manifest["metrics"].append(param)
        elif create_metric(client, property_id, param, display, desc, unit, scope):
            print(f"    OK    {param}")
            mets_created.append(param)
            manifest["metrics"].append(param)

    save_manifest(manifest)

    print("\n" + "=" * 56)
    print(f"  Created: {len(dims_created)} dimension(s), {len(mets_created)} metric(s)")
    for d in dims_created:
        print(f"    + dimension: {d}")
    for m in mets_created:
        print(f"    + metric:    {m}")
    print("\n  Next steps:")
    print("  1. Wait 24-48h for data to flow into the new definitions.")
    print("  2. Build an Exploration in GA4/Firebase using these dimensions/metrics.")
    print("=" * 56 + "\n")


# --- Main ---------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description="Register GA4 Custom Dimensions + Metrics from a definitions file."
    )
    p.add_argument("--input", default="definitions.json",
                   help="Manual definitions.json OR a scanner's discovered_events.json "
                        "(default: definitions.json)")
    p.add_argument("--apply", action="store_true",
                   help="Actually create definitions (default: dry run)")
    p.add_argument("--list", action="store_true",
                   help="List what's currently registered in GA4")
    p.add_argument("--key", default=os.environ.get("GA4_KEY_PATH"),
                   help="Service account JSON key path (env: GA4_KEY_PATH)")
    p.add_argument("--property", default=os.environ.get("GA4_PROPERTY_ID"),
                   help="GA4 property ID, e.g. properties/123456789 (env: GA4_PROPERTY_ID)")
    return p.parse_args()


def main():
    args = parse_args()

    dims, metrics, mode = load_definitions(Path(args.input))

    print()
    print("  GA4 Custom Definitions Registrar")
    print("  ================================")
    print(f"  Input      : {args.input}  (detected mode: {mode})")
    print(f"  Dimensions : {len(dims)}")
    print(f"  Metrics    : {len(metrics)}")
    if mode == "scan":
        print(f"  Skipped    : {', '.join(sorted(SKIP_PARAMS))} (low-value coords)")
    print(f"  Quota      : {QUOTA_CAP} dimensions / {QUOTA_CAP} metrics per property")
    print()

    manifest = load_manifest()

    if not args.apply and not args.list:
        run_dry(dims, metrics, manifest)
        return

    if not check_deps():
        sys.exit(1)

    if not args.property:
        print("  ERROR: GA4 property ID required.")
        print("  Set GA4_PROPERTY_ID env var or pass --property properties/123456\n")
        sys.exit(1)
    if not args.property.startswith("properties/"):
        args.property = f"properties/{args.property}"

    client = get_client(args.key)

    if args.list:
        run_list(client, args.property, dims, metrics)
        return
    if args.apply:
        run_apply(client, args.property, dims, metrics, manifest)


if __name__ == "__main__":
    main()
