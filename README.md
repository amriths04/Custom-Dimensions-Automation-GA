# GA4 Custom Definitions Automation

Auto-register GA4 Custom Dimensions in your Google Analytics 4 property via the Admin API.

Two authentication methods are available — pick whichever fits your setup:

| Method | Folder | Use when |
|---|---|---|
| **Service Account** | `service_account/` | You have a GCP service account with GA4 property access |
| **OAuth 2.0** [TESTED - WORKING]| `oauth/` | You want to authenticate with your personal Google account via browser |

---
> [!IMPORTANT]
> **GA4 Standard Property Limits**
>
> - Event-scoped custom dimensions: **50**
> - User-scoped custom dimensions: **25**
> - Item-scoped custom dimensions: **10**
> - Custom metrics: **50**
> - Calculated metrics: **5**
>
> **Google Analytics 360** properties have significantly higher limits, including:
>
> - Event-scoped custom dimensions: **125**
> - User-scoped custom dimensions: **100**
## Quick start

Pick a method folder and install its dependencies:

```bash
# Service account method
cd service_account
pip install -r requirements.txt

# OAuth method
cd oauth
pip install -r requirements.txt
```

Then follow the README inside the method folder you choose.
