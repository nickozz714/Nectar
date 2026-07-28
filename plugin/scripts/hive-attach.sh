#!/usr/bin/env bash
# Attach a local artifact to a hive node, or fetch one — so files referenced in a memory
# are available on ANY machine, not just the one that added them.
#
#   hive-attach add  <node_uid> <path>        upload a local file, attach it to the node
#   hive-attach list <node_uid>               list a node's attachments (uid, name, size)
#   hive-attach get  <attachment_uid> [out]   download an attachment (default: its filename)
#
# Connection is read from ~/.hivemind/config.json (env HIVE_URL/HIVE_TOKEN override).
set -uo pipefail

CFG="$HOME/.hivemind/config.json"
if [ -z "${HIVE_URL:-}" ] || [ -z "${HIVE_TOKEN:-}" ]; then
  [ -f "$CFG" ] && eval "$(HIVE_CFG="$CFG" python3 - <<'PY'
import json, os
c = json.load(open(os.environ["HIVE_CFG"]))
for k, v in (("HIVE_URL", c.get("hive_url")), ("HIVE_TOKEN", c.get("hive_token"))):
    if not os.environ.get(k) and v:
        print(f'export {k}={json.dumps(v)}')
PY
)"
fi
URL="${HIVE_URL:-}"; TOKEN="${HIVE_TOKEN:-}"
[ -z "$URL" ] || [ -z "$TOKEN" ] && { echo "geen HIVE_URL/HIVE_TOKEN (draai hive-install-global.sh)" >&2; exit 1; }
URL="${URL%/}"
auth=(-H "Authorization: Bearer $TOKEN")

case "${1:-}" in
  add)
    node="${2:?usage: hive-attach add <node_uid> <path>}"; path="${3:?pad naar bestand}"
    [ -f "$path" ] || { echo "bestand niet gevonden: $path" >&2; exit 1; }
    name="$(basename "$path")"
    ct="$(file --mime-type -b "$path" 2>/dev/null || echo application/octet-stream)"
    curl -sf -m 60 "${auth[@]}" -H "Content-Type: $ct" --data-binary "@$path" \
      "$URL/graph/node/$node/attachments?filename=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$name")" \
      | python3 -c "import json,sys;d=json.load(sys.stdin);print('bijgevoegd:',d['filename'],f\"({d['size']} bytes)  uid={d['uid']}\")" \
      || { echo "upload mislukt" >&2; exit 1; }
    ;;
  list)
    node="${2:?usage: hive-attach list <node_uid>}"
    curl -sf -m 20 "${auth[@]}" "$URL/graph/node/$node/attachments" | python3 -c "
import json,sys
for a in json.load(sys.stdin):
    print(f\"  {a['filename']}  ({a['size']} bytes, {a['content_type']})  uid={a['uid']}\")
" || { echo "kon lijst niet ophalen" >&2; exit 1; }
    ;;
  get)
    att="${2:?usage: hive-attach get <attachment_uid> [out]}"; out="${3:-}"
    tmp="$(mktemp)"
    name="$(curl -sf -m 60 "${auth[@]}" -D - "$URL/attachments/$att" -o "$tmp" \
      | tr -d '\r' | awk -F"UTF-8''" "/[Cc]ontent-[Dd]isposition/{print \$2}")"
    [ -s "$tmp" ] || { echo "download mislukt (bestaat de bijlage / heb je toegang?)" >&2; rm -f "$tmp"; exit 1; }
    [ -z "$out" ] && out="$(python3 -c "import urllib.parse,sys;print(urllib.parse.unquote(sys.argv[1]) or 'bijlage')" "${name:-bijlage}")"
    mv -f "$tmp" "$out"; echo "opgeslagen als: $out"
    ;;
  *)
    echo "usage: hive-attach add <node_uid> <path> | list <node_uid> | get <attachment_uid> [out]" >&2
    exit 1;;
esac
