# Nectar — deployment & authentication configuration

How you deploy Nectar and, in doing so, decide *how* people log in. Core idea: **the image is
identical for everyone; authentication is purely configuration at deploy time.** The Entra
integration is therefore NOT in the image — you supply it (or leave it out) via environment/secrets at
the moment you deploy the app.

## The three login methods (always on, no config needed)
1. **First-time wizard** — an empty hive asks via the GUI for the first account; that becomes
   org_admin and immediately gets a token.
2. **Password** — username + password (scrypt); yields a token.
3. **Token** — paste an account token.

These work without any configuration. An organisation that does **not** want Microsoft/Entra
simply uses these three — there is nothing to turn off, because SSO is off by default.

## The fourth method: Microsoft Entra SSO (optional, config at deploy time)
Appears **only** if you supply these values at deploy time (otherwise the button stays
hidden and `/auth/entra/status` → `{"enabled": false}`):

| Env var | What | Required for SSO |
|---|---|---|
| `ENTRA_TENANT_ID` | Directory (tenant) ID | ✅ |
| `ENTRA_CLIENT_ID` | Application (client) ID | ✅ |
| `ENTRA_CLIENT_SECRET` | client secret (value) | ✅ |
| `PUBLIC_BASE_URL` | public URL of this deploy, e.g. `https://hive.example.com` | ✅ (for the redirect) |
| `ENTRA_REDIRECT_URI` | explicit callback URL | optional (otherwise derived from `PUBLIC_BASE_URL`) |
| `ENTRA_AUTO_PROVISION` | `true` (default): every tenant user automatically gets a member account; `false`: invite-only-with-SSO | optional |

See **[entra/README.md](entra/README.md)** for the app registration in Azure itself.

### How to make sure the integration is present "at deploy time" (per target environment)
The integration = having the vars above present at the moment the container starts.
You arrange that in the way that fits your deploy target:

- **Docker Compose (server, house style)** — put the vars in the `.env` next to
  `docker-compose.yml` and `docker compose up -d`. Leaving them out = no SSO.
  ```ini
  ENTRA_TENANT_ID=...
  ENTRA_CLIENT_ID=...
  ENTRA_CLIENT_SECRET=...
  PUBLIC_BASE_URL=https://hive.yourdomain.com
  ```
- **Azure Container Apps** — as **secrets** + `--env-vars` (see [azure/README.md](azure/README.md)).
  `PUBLIC_BASE_URL` = the ACA FQDN (`https://<app>.<region>.azurecontainerapps.io`); that is
  immediately your redirect URI. Leave out the `ENTRA_*` secrets and the same app deploys without SSO.
- **Kubernetes / other** — inject as `env` from a Secret. Same principle.

Important: the **redirect URI is a deploy-time value** — it must match exactly between (a) what
you set in the Entra app registration and (b) `PUBLIC_BASE_URL`/`ENTRA_REDIRECT_URI` of this
deploy. Per environment (dev/test/prod, or per customer) that is therefore a different URL and usually a
different app registration (or one multi-tenant registration with multiple redirect URIs).

## Decision tree at deploy time
```
Does the organisation want Microsoft login?
├─ No   → deploy without ENTRA_* . Done. (wizard + password + tokens)
└─ Yes  → 1. create an Entra app registration (entra/README.md)
          2. set redirect URI = <PUBLIC_BASE_URL>/auth/entra/callback
          3. supply ENTRA_TENANT_ID/CLIENT_ID/CLIENT_SECRET + PUBLIC_BASE_URL at deploy time
          4. restart → the "Sign in with Microsoft" button appears
             (auto-provisioning on unless ENTRA_AUTO_PROVISION=false)
```

## Other deploy secrets (briefly)
- `NEO4J_PASSWORD` — set it if you expose the DB ports; otherwise default.
- `SECRET_MASTER_KEY` — vault key; leave empty → auto-generated + persisted on `/data`.
- `ADMIN_TOKEN` — optional infra break-glass; empty = `/admin` off, everything via org_admin.
- Everything is in [`../.env.example`](../.env.example); full walkthrough in
  [`../INSTALL.md`](../INSTALL.md).

## In summary
The image carries no customer-specific integration at all. Auth is a **deploy-time choice**: leave the
`ENTRA_*` out for a standalone hive (wizard/password/token), or supply them to turn on
Microsoft SSO. This is how you deploy the same Nectar for an organisation with or
without Entra, without changing the app.
