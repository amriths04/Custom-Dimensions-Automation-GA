# Service Account Method

Register GA4 Custom Dimensions using a GCP service account key.

## How it works

The script reads your `definitions.json`, checks what's already registered in GA4,
and creates only the missing custom dimensions. It is fully idempotent — re-running
is always safe, existing definitions are never duplicated.

## Setup (one-time)

### 1. Enable the Google Analytics Admin API

1. Go to [Google Cloud Console](https://console.cloud.google.com) and select your project.
2. Search for **Google Analytics Admin API** → click **Enable**.

### 2. Create a Service Account

1. Go to **IAM & Admin → Service Accounts**.
2. Click **+ Create Service Account** → give it a name (e.g. `ga4-automation`) → click **Done**.
3. Click on the service account → **Keys** tab → **Add Key → Create new key → JSON** → Download.

### 3. Grant the service account GA4 property access

1. Go to [Google Analytics](https://analytics.google.com) → **Admin**.
2. Under **Property** → **Property Access Management** → click **+**.
3. Enter the service account email (e.g. `ga4-automation@your-project.iam.gserviceaccount.com`).
4. Set role to **Editor** → click **Add**.

> Note: GA4's UI may reject service account emails saying "This email doesn't match a Google Account."
> If that happens, use the **OAuth method** instead (`oauth/`).

### 4. Prepare your definitions file

Copy the template and fill it in:

```bash
cp ../definitions.template.json definitions.json
```

Edit `definitions.json` to list your event parameters as custom dimensions:

```json
{
  "custom_dimensions": [
    { "parameter_name": "level_number", "display_name": "Level Number", "description": "Level identifier", "scope": "EVENT" }
  ],
  "custom_metrics": []
}
```

## Running the script

```bash
cd service_account
```

**Dry run** (preview only, no credentials needed):
```bash
python register_ga4_definitions.py --input ../definitions.json
```

**Apply** (registers definitions in GA4):
```bash
# Windows
set GA4_KEY_PATH=C:\path\to\service-account-key.json
set GA4_PROPERTY_ID=properties/123456789

# macOS/Linux
export GA4_KEY_PATH=/path/to/service-account-key.json
export GA4_PROPERTY_ID=properties/123456789

python register_ga4_definitions.py --input ../definitions.json --apply
```

Or pass flags directly:
```bash
python register_ga4_definitions.py --input ../definitions.json --apply --key path/to/key.json --property properties/123456789
```

**List what's currently registered:**
```bash
python register_ga4_definitions.py --list
```

## Quota

GA4 enforces a hard cap of **50 custom dimensions** and **50 custom metrics** per property.
The script warns you when you cross 80% of the limit.

## Notes

- New definitions take **24–48 hours** to start collecting data.
- After each `--apply`, a `ga4_definitions_manifest.json` is written to track what was registered.
- Never commit your service account key — `.gitignore` blocks all `*.json` keys by default.
