# HiveMind op Azure Container Apps

Ja, dit kan. HiveMind is één image (Neo4j + API + lokale embeddings), volledig
env-gestuurd, met alle state op één volume (`/data`) — precies wat Azure Container Apps
(ACA) nodig heeft. Bonus: ACA geeft een echte **HTTPS-hostname**, wat meteen twee dingen
oplost:
- de macOS-privé-IP-MCP-bug is weg (geen LAN-IP meer, maar een publieke hostname);
- het is een geldige **Entra redirect-URI** voor SSO.

## Belangrijke keuzes / caveats
- **Eén replica.** Neo4j draait ín de container en is niet horizontaal deelbaar. Zet
  `--min-replicas 1 --max-replicas 1`.
- **Persistente opslag = Azure Files.** Mount een file share op `/data` (Neo4j-store +
  vault-key + install-zip-state). **Gebruik NFS-protocol** voor de share — Neo4j's
  file-locking werkt slecht op SMB. (Zwaar productiegebruik? Overweeg Neo4j los op een
  managed disk via AKS; voor normaal gebruik volstaat ACA + Azure Files NFS.)
- **Ingress** op de API-poort **8000** (HTTPS automatisch). Neo4j Browser (7474) en bolt
  (7687) exposeer je niet — niet nodig in productie.
- **Secrets** via ACA secrets: `NEO4J_PASSWORD`, optioneel `SECRET_MASTER_KEY` (auto-gen +
  persist op het volume als je 'm weglaat), optioneel `ADMIN_TOKEN`, en de `ENTRA_*` als je
  SSO gebruikt. Zet `PUBLIC_BASE_URL` op de ACA-URL.

## Deploy (az CLI)

```bash
RG=hivemind-rg
LOC=westeurope
ACR=hivemindacr$RANDOM          # globally unique
ENV=hivemind-env
APP=hivemind
SA=hivemindstore$RANDOM         # globally unique storage account
SHARE=hive-data

az group create -n $RG -l $LOC

# 1. Registry + build & push the image (uses the repo Dockerfile)
az acr create -n $ACR -g $RG --sku Basic --admin-enabled true
az acr build -r $ACR -t hivemind:latest .        # run from the repo root

# 2. Storage: Azure Files NFS share for /data (Neo4j-safe)
az storage account create -n $SA -g $RG -l $LOC --sku Premium_LRS \
  --kind FileStorage --https-only false --default-action Allow
az storage share-rma create ... 2>/dev/null || \
az storage share create --account-name $SA -n $SHARE --quota 64 \
  --enabled-protocols NFS 2>/dev/null || true

# 3. Container Apps environment + attach the share
az containerapp env create -n $ENV -g $RG -l $LOC
az containerapp env storage set -g $RG -n $ENV --storage-name hivedata \
  --azure-file-account-name $SA --azure-file-share-name $SHARE \
  --azure-file-account-key "$(az storage account keys list -n $SA -g $RG --query '[0].value' -o tsv)" \
  --access-mode ReadWrite

# 4. The app: single replica, ingress on 8000, /data mounted, secrets
ACR_PW=$(az acr credential show -n $ACR --query 'passwords[0].value' -o tsv)
az containerapp create -n $APP -g $RG --environment $ENV \
  --image $ACR.azurecr.io/hivemind:latest \
  --registry-server $ACR.azurecr.io --registry-username $ACR --registry-password "$ACR_PW" \
  --target-port 8000 --ingress external \
  --min-replicas 1 --max-replicas 1 \
  --cpu 2 --memory 4Gi \
  --secrets neo4jpw="$(openssl rand -hex 16)" \
  --env-vars NEO4J_PASSWORD=secretref:neo4jpw NEO4J_URI=bolt://localhost:7687 NEO4J_USER=neo4j

# 5. Mount the share at /data (via YAML patch — the CLI needs the volume in the template)
az containerapp show -n $APP -g $RG -o yaml > app.yaml
#   edit app.yaml: under template add
#     volumes: [{ name: hivedata, storageType: AzureFile, storageName: hivedata }]
#   and in the container add
#     volumeMounts: [{ volumeName: hivedata, mountPath: /data }]
az containerapp update -n $APP -g $RG --yaml app.yaml

# URL:
az containerapp show -n $APP -g $RG --query properties.configuration.ingress.fqdn -o tsv
```

Set `PUBLIC_BASE_URL=https://<fqdn>` (env var) so redirects/Entra use the real URL.

## Na deploy
- GUI: `https://<fqdn>/ui` — de **first-time wizard** vraagt om het eerste account (wordt
  org_admin), daarna kun je tokens uitdelen en de install-zip downloaden.
- MCP-clients: `https://<fqdn>/mcp` (echte HTTPS-hostname → **geen** localhost-tunnel meer
  nodig op macOS). Recall-hook: `https://<fqdn>`.
- Entra SSO: zie `deploy/entra/README.md`; redirect-URI = `https://<fqdn>/auth/entra/callback`.

## Startup-noot
De container start Neo4j en dan de API; `init_db` retryt tot bolt klaar is. Geef ACA een
ruime startup (health `/health`); bij een koude Azure-Files-mount kan de eerste boot wat
langer duren.
