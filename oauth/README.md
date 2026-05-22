# OAuth 2.0 Method

Register GA4 Custom Dimensions by authenticating with your personal Google account via browser.

Use this method when the GA4 UI rejects your service account email with
"This email doesn't match a Google Account" — a known GA4 limitation with service accounts.

## How it works

The script opens your browser, asks you to log in with your Google account (the one
that has GA4 property access), saves a token locally, then registers all custom
dimensions from your `definitions.json` via the GA4 Admin API.

## Setup (one-time)

### 1. Enable the Google Analytics Admin API

1. Go to [Google Cloud Console](https://console.cloud.google.com) and select your project.
2. Search for **Google Analytics Admin API** → click **Enable**.

### 2. Configure OAuth consent screen

1. Go to **APIs & Services → OAuth consent screen** (or **Google Auth Platform → Overview**).
2. Click **Get started** → fill in app name (e.g. `ga4-automation`) → save.
3. Under **Audience** → add your Google account email as a test user.

### 3. Create OAuth 2.0 credentials

1. Go to **Google Auth Platform → Clients** → click **Create Client**.
2. Application type: **Desktop app** → click **Create**.
3. Download the JSON file (named `client_secret_....json`).

### 4. Install dependencies

```bash
pip install -r ../requirements.txt
```

### 5. Prepare your definitions file

Copy the template and fill it in:

```bash
cp ../definitions.template.json ../definitions.json
```

Edit `definitions.json` to list your event parameters:

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
cd oauth

python oauth_apply.py \
  --client-secret path/to/client_secret.json \
  --property properties/123456789 \
  --input ../definitions.json
```

Or use environment variables:

```bash
# Windows
set GA4_CLIENT_SECRET=C:\path\to\client_secret.json
set GA4_PROPERTY_ID=properties/123456789

# macOS/Linux
export GA4_CLIENT_SECRET=/path/to/client_secret.json
export GA4_PROPERTY_ID=properties/123456789

python oauth_apply.py --input ../definitions.json
```

### What happens when you run it

1. A browser window opens asking you to log in with your Google account.
2. Click **Allow** to grant access.
3. The script connects to GA4, checks what's already registered, and creates the missing dimensions.
4. A `token.json` is saved locally so you don't need to log in again on the next run.

## Output example

```
  Authenticating with your Google account...
  Authenticated!

  Already registered: 0 dimensions

  OK    is_first_install
  OK    referral_source
  OK    language_code
  ...
  SKIP  score  (already exists)

  Done — Created: 48, Skipped: 2
```

## Notes

- `token.json` and `client_secret*.json` are gitignored — never commit them.
- New dimensions take **24–48 hours** to start collecting data in GA4.
- Re-running is safe — already registered dimensions are always skipped.
- GA4 hard cap: **50 custom dimensions** per property.
