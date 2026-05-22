"""
OAuth login + GA4 custom definitions registration.
Opens browser to authenticate with your Google account, then applies definitions.

Usage:
  python oauth_apply.py --client-secret path/to/client_secret.json --property properties/123456789
  python oauth_apply.py --client-secret path/to/client_secret.json --property properties/123456789 --input definitions.json

Env vars (alternative to flags):
  GA4_CLIENT_SECRET  — path to OAuth client secret JSON
  GA4_PROPERTY_ID    — e.g. properties/538490825
"""
import argparse
import json
import os
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.analytics.admin import AnalyticsAdminServiceClient
from google.analytics.admin_v1alpha.types import CustomDimension
from google.api_core.exceptions import AlreadyExists

SCOPES     = ["https://www.googleapis.com/auth/analytics.edit"]
TOKEN_FILE = Path("token.json")


def parse_args():
    p = argparse.ArgumentParser(description="OAuth-based GA4 custom dimensions registrar.")
    p.add_argument("--client-secret", default=os.environ.get("GA4_CLIENT_SECRET"),
                   help="Path to OAuth client secret JSON (env: GA4_CLIENT_SECRET)")
    p.add_argument("--property", default=os.environ.get("GA4_PROPERTY_ID"),
                   help="GA4 property ID, e.g. properties/123456789 (env: GA4_PROPERTY_ID)")
    p.add_argument("--input", default="definitions.json",
                   help="Definitions file (default: definitions.json)")
    return p.parse_args()


def get_credentials(client_secret_path: str) -> Credentials:
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        if creds and creds.valid:
            return creds
    flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
    creds = flow.run_local_server(port=0)
    TOKEN_FILE.write_text(creds.to_json())
    return creds


def main():
    args = parse_args()

    if not args.client_secret:
        print("ERROR: --client-secret or GA4_CLIENT_SECRET required.")
        raise SystemExit(1)
    if not args.property:
        print("ERROR: --property or GA4_PROPERTY_ID required.")
        raise SystemExit(1)

    property_id = args.property if args.property.startswith("properties/") else f"properties/{args.property}"

    print("\n  Authenticating with your Google account...")
    creds = get_credentials(args.client_secret)
    print("  Authenticated!\n")

    client = AnalyticsAdminServiceClient(credentials=creds)

    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)

    dims = data.get("custom_dimensions", [])

    existing = {d.parameter_name for d in client.list_custom_dimensions(parent=property_id)}
    print(f"  Already registered: {len(existing)} dimensions\n")

    created, skipped = [], []
    for entry in dims:
        param = entry["parameter_name"]
        if param in existing:
            print(f"  SKIP  {param}")
            skipped.append(param)
            continue
        try:
            client.create_custom_dimension(
                parent=property_id,
                custom_dimension=CustomDimension(
                    parameter_name=param,
                    display_name=entry.get("display_name", param),
                    description=entry.get("description", ""),
                    scope=CustomDimension.DimensionScope.EVENT,
                ),
            )
            print(f"  OK    {param}")
            created.append(param)
        except AlreadyExists:
            print(f"  SKIP  {param}  (already exists)")
            skipped.append(param)
        except Exception as e:
            print(f"  ERROR {param}: {e}")

    print(f"\n  Done — Created: {len(created)}, Skipped: {len(skipped)}\n")


if __name__ == "__main__":
    main()
