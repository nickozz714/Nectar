# Microsoft Entra (Azure AD) SSO for Nectar

Let people log in with their **Microsoft organisation account**. Optional — Nectar works
without it; if it's not configured, the Microsoft button is simply hidden.

## How it works
- The GUI shows "Sign in with Microsoft" → `/auth/entra/login` → Microsoft login →
  `/auth/entra/callback` → Nectar exchanges the code, reads the **email/name** from the
  id token, and logs the user in — **the Microsoft account IS the identity**:
  - an account with that email already exists → log in (token, 30 days);
  - the hive is still empty (first run) → that person becomes org_admin;
  - otherwise → **a member account is created automatically** (auto-provisioning). Because your
    app is single-tenant, the Microsoft tenant is the access boundary: only your org members
    can log in, and everyone who logs in automatically gets an account.
- The Nectar token is returned to the GUI via the URL fragment (never logged server-side).
- Turn off auto-provisioning (invite-only-with-SSO)? Set `ENTRA_AUTO_PROVISION=false`.

## 1. App registration in Entra
In the Azure portal → **Microsoft Entra ID → App registrations → New registration**:
- Name: `Nectar`.
- Supported account types: *Accounts in this organizational directory only* (single tenant)
  — or multi-tenant if you want that.
- Redirect URI (type **Web**): `https://<your-host>/auth/entra/callback`
  (e.g. the ACA FQDN or your own domain; for local testing `http://localhost:8642/auth/entra/callback`).
- After creating: note the **Application (client) ID** and **Directory (tenant) ID**.
- **Certificates & secrets → New client secret** → note the secret **value**.

Scopes: the default `User.Read` (delegated) is enough — no admin consent needed for
just email/name.

## 2. Configure Nectar
Set these env vars (server `.env` or ACA secrets):
```ini
ENTRA_TENANT_ID=<Directory (tenant) ID>
ENTRA_CLIENT_ID=<Application (client) ID>
ENTRA_CLIENT_SECRET=<client secret value>
PUBLIC_BASE_URL=https://<your-host>          # for the redirect URI
# optionally explicit: ENTRA_REDIRECT_URI=https://<your-host>/auth/entra/callback
```
Restart the container. Check: `GET /auth/entra/status` → `{"enabled": true}`, and the
Microsoft button appears in the GUI.

## 3. Admitting users
- **First time**: the very first Microsoft login on an empty hive becomes org_admin.
- **After that, by default (auto-provisioning on)**: anyone from your Microsoft tenant can
  log in and automatically gets a **member** account. To give someone more rights,
  promote them with `hive_set_role`. The tenant itself is the access boundary.
- **Invite-only-with-SSO** (`ENTRA_AUTO_PROVISION=false`): then the email must have an
  account beforehand (admin API/`/manage`/Beheer tab); unknown emails are rejected.

## Notes
- The redirect URI in Entra must match **exactly** what Nectar uses (scheme, host,
  path). Behind a reverse proxy: set `PUBLIC_BASE_URL` to the public URL.
- Password login and token login keep working alongside SSO.
