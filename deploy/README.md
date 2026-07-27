# HiveMind — uitrol & authenticatie-configuratie

Hoe je HiveMind uitrolt en daarbij bepaalt *hoe* mensen inloggen. Kern: **de image is
identiek voor iedereen; authenticatie is puur configuratie bij uitrol.** De Entra-koppeling
zit dus NIET in het image, maar geef je (of laat je weg) via environment/secrets op het
moment dat je de app deployt.

## De drie inlogmanieren (staan altijd aan, geen config nodig)
1. **First-time wizard** — een lege hive vraagt via de GUI om het eerste account; dat wordt
   org_admin en krijgt meteen een token.
2. **Wachtwoord** — gebruikersnaam + wachtwoord (scrypt); levert een token op.
3. **Token** — plak een account-token.

Deze werken zonder enige configuratie. Een organisatie die **geen** Microsoft/Entra wil
gebruikt gewoon deze drie — er is niets uit te zetten, want SSO is standaard uit.

## De vierde manier: Microsoft Entra SSO (optioneel, config bij uitrol)
Verschijnt **alleen** als je bij de uitrol deze waarden meegeeft (anders blijft de knop
verborgen en is `/auth/entra/status` → `{"enabled": false}`):

| Env-var | Wat | Verplicht voor SSO |
|---|---|---|
| `ENTRA_TENANT_ID` | Directory (tenant) ID | ✅ |
| `ENTRA_CLIENT_ID` | Application (client) ID | ✅ |
| `ENTRA_CLIENT_SECRET` | client secret (waarde) | ✅ |
| `PUBLIC_BASE_URL` | publieke URL van deze deploy, bv. `https://hive.example.com` | ✅ (voor de redirect) |
| `ENTRA_REDIRECT_URI` | expliciete callback-URL | optioneel (anders afgeleid van `PUBLIC_BASE_URL`) |
| `ENTRA_AUTO_PROVISION` | `true` (default): elke tenant-gebruiker krijgt vanzelf een member-account; `false`: invite-only-met-SSO | optioneel |

Zie **[entra/README.md](entra/README.md)** voor de app-registratie in Azure zelf.

### Zo zorg je dat de koppeling er "bij de uitrol" is (per doel-omgeving)
De koppeling = de bovenstaande vars aanwezig hebben op het moment dat de container start.
Dat regel je op de manier die bij je deploy-doel hoort:

- **Docker Compose (server, huisstijl)** — zet de vars in de `.env` naast
  `docker-compose.yml` en `docker compose up -d`. Weglaten = geen SSO.
  ```ini
  ENTRA_TENANT_ID=...
  ENTRA_CLIENT_ID=...
  ENTRA_CLIENT_SECRET=...
  PUBLIC_BASE_URL=https://hive.jouwdomein.nl
  ```
- **Azure Container Apps** — als **secrets** + `--env-vars` (zie [azure/README.md](azure/README.md)).
  `PUBLIC_BASE_URL` = de ACA-FQDN (`https://<app>.<region>.azurecontainerapps.io`); die is
  meteen je redirect-URI. Weglaat je de `ENTRA_*` secrets, dan rolt dezelfde app uit zonder SSO.
- **Kubernetes / andere** — injecteer als `env` uit een Secret. Zelfde principe.

Belangrijk: de **redirect-URI is een uitrol-waarde** — hij moet exact matchen tussen (a) wat
je in de Entra-app-registratie zet en (b) `PUBLIC_BASE_URL`/`ENTRA_REDIRECT_URI` van déze
deploy. Per omgeving (dev/test/prod, of per klant) is dat dus een andere URL en meestal een
andere app-registratie (of één multi-tenant registratie met meerdere redirect-URI's).

## Beslisboom bij uitrol
```
Wil de organisatie Microsoft-login?
├─ Nee  → deploy zonder ENTRA_* . Klaar. (wizard + wachtwoord + tokens)
└─ Ja   → 1. maak een Entra app-registratie (entra/README.md)
          2. zet redirect-URI = <PUBLIC_BASE_URL>/auth/entra/callback
          3. geef ENTRA_TENANT_ID/CLIENT_ID/CLIENT_SECRET + PUBLIC_BASE_URL mee bij de deploy
          4. herstart → knop "Inloggen met Microsoft" verschijnt
             (auto-provisioning aan tenzij ENTRA_AUTO_PROVISION=false)
```

## Overige uitrol-secrets (kort)
- `NEO4J_PASSWORD` — zet 'm als je de DB-poorten exposeert; anders default.
- `SECRET_MASTER_KEY` — vault-sleutel; laat leeg → auto-gegenereerd + gepersisteerd op `/data`.
- `ADMIN_TOKEN` — optioneel infra-break-glass; leeg = `/admin` uit, alles via org_admin.
- Alles staat in [`../.env.example`](../.env.example); volledige walkthrough in
  [`../INSTALL.md`](../INSTALL.md).

## Samengevat
De image kent geen enkele klant-specifieke koppeling. Auth is een **uitrol-keuze**: laat de
`ENTRA_*` weg voor een zelfstandige hive (wizard/wachtwoord/token), of geef ze mee om
Microsoft-SSO aan te zetten. Zo rol je dezelfde HiveMind uit voor een organisatie mét of
zónder Entra, zonder de app te wijzigen.
