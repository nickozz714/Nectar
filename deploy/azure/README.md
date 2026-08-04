# Nectar on Azure Container Apps

Yes, this works. Nectar is one image (Neo4j + API + local embeddings), fully
env-driven, with all state on one volume (`/data`) — exactly what Azure Container Apps
(ACA) needs. Bonus: ACA gives a real **HTTPS hostname**, which immediately solves two
things:
- the macOS private-IP MCP bug is gone (no LAN IP anymore, but a public hostname);
- it is a valid **Entra redirect URI** for SSO.

## Important choices / caveats
- **One replica.** Neo4j runs inside the container and is not horizontally shareable. Set
  `--min-replicas 1 --max-replicas 1`.
- **Persistent storage = Azure Files.** Mount a file share on `/data` (Neo4j store +
  vault key + install-zip state). **Use the NFS protocol** for the share — Neo4j's
  file locking works poorly on SMB. (Heavy production use? Consider running Neo4j separately on a
  managed disk via AKS; for normal use ACA + Azure Files NFS is enough.)
- **Ingress** on the API port **8000** (HTTPS automatic). Neo4j Browser (7474) and bolt
  (7687) you do not expose — not needed in production.
- **Secrets** via ACA secrets: `NEO4J_PASSWORD`, optionally `SECRET_MASTER_KEY` (auto-gen +
  persist on the volume if you leave it out), optionally `ADMIN_TOKEN`, and the `ENTRA_*` if you
  use SSO. Set `PUBLIC_BASE_URL` to the ACA URL.

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

## After deploy
- GUI: `https://<fqdn>/ui` — the **first-time wizard** asks for the first account (becomes
  org_admin), after which you can hand out tokens and download the install-zip.
- MCP clients: `https://<fqdn>/mcp` (real HTTPS hostname → **no** localhost tunnel needed
  on macOS). Recall hook: `https://<fqdn>`.
- Entra SSO: see `deploy/entra/README.md`; redirect URI = `https://<fqdn>/auth/entra/callback`.

## Startup note
The container starts Neo4j and then the API; `init_db` retries until bolt is ready. Give ACA a
generous startup (health `/health`); on a cold Azure Files mount the first boot may take a
bit longer.
