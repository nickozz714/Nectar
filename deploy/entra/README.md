# Microsoft Entra (Azure AD) SSO voor HiveMind

Laat mensen inloggen met hun **Microsoft organisatie-account**. Optioneel — HiveMind werkt
zonder; is het niet geconfigureerd, dan is de Microsoft-knop simpelweg verborgen.

## Hoe het werkt
- GUI toont "Inloggen met Microsoft" → `/auth/entra/login` → Microsoft-login →
  `/auth/entra/callback` → HiveMind wisselt de code in, leest **e-mail/naam** uit het
  id-token, en logt de gebruiker in — **het Microsoft-account IS de identiteit**:
  - bestaat er al een account met die e-mail → inloggen (token, 30 dagen);
  - is de hive nog leeg (first run) → die persoon wordt org_admin;
  - anders → **automatisch een member-account aangemaakt** (auto-provisioning). Omdat je
    app single-tenant is, is de Microsoft-tenant de toegangsgrens: alleen jouw org-leden
    kunnen inloggen, en iedereen die inlogt krijgt vanzelf een account.
- Het HiveMind-token gaat via de URL-fragment terug naar de GUI (nooit server-side gelogd).
- Auto-provisioning uitzetten (invite-only-met-SSO)? Zet `ENTRA_AUTO_PROVISION=false`.

## 1. App-registratie in Entra
In het Azure-portaal → **Microsoft Entra ID → App registrations → New registration**:
- Naam: `HiveMind`.
- Supported account types: *Accounts in this organizational directory only* (single tenant)
  — of multi-tenant als je dat wilt.
- Redirect URI (type **Web**): `https://<jouw-host>/auth/entra/callback`
  (bijv. de ACA-FQDN of je eigen domein; voor lokaal testen `http://localhost:8642/auth/entra/callback`).
- Na aanmaken: noteer **Application (client) ID** en **Directory (tenant) ID**.
- **Certificates & secrets → New client secret** → noteer de secret-**waarde**.

Scopes: de standaard `User.Read` (delegated) volstaat — geen admin-consent nodig voor
alleen e-mail/naam.

## 2. HiveMind configureren
Zet deze env-vars (server-`.env` of ACA-secrets):
```ini
ENTRA_TENANT_ID=<Directory (tenant) ID>
ENTRA_CLIENT_ID=<Application (client) ID>
ENTRA_CLIENT_SECRET=<client secret value>
PUBLIC_BASE_URL=https://<jouw-host>          # voor de redirect-URI
# optioneel expliciet: ENTRA_REDIRECT_URI=https://<jouw-host>/auth/entra/callback
```
Herstart de container. Check: `GET /auth/entra/status` → `{"enabled": true}`, en de
Microsoft-knop verschijnt in de GUI.

## 3. Gebruikers toelaten
- **Eerste keer**: de allereerste Microsoft-login op een lege hive wordt org_admin.
- **Daarna, standaard (auto-provisioning aan)**: iedereen uit je Microsoft-tenant kan
  inloggen en krijgt automatisch een **member**-account. Wil je iemand meer rechten geven,
  promoveer dan met `hive_set_role`. De tenant zelf is de toegangsgrens.
- **Invite-only-met-SSO** (`ENTRA_AUTO_PROVISION=false`): dan moet de e-mail vooraf een
  account hebben (admin-API/`/manage`/Beheer-tab); onbekende e-mails worden geweigerd.

## Noten
- De redirect-URI in Entra moet **exact** matchen met wat HiveMind gebruikt (schema, host,
  pad). Achter een reverse proxy: zet `PUBLIC_BASE_URL` op de publieke URL.
- Wachtwoord-login en token-login blijven gewoon werken naast SSO.
