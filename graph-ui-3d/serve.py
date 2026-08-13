#!/usr/bin/env python3
"""Local dev server for the 3D HUD graph prototype.

Serves the static prototype AND assembles the full mind-graph from a running Nectar
server using the EXISTING endpoints (topics + nodes-brief + neighbors per node), so no
server changes are needed to try it. The hive token is read from the workspace's
.claude/settings.json and only ever travels server-side — never to the browser.

Usage:  python3 serve.py [port]        (default 8090)
        GET /data.json?refresh=1       re-assembles instead of using .cache.json
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, ".cache.json")
SETTINGS = os.path.expanduser("~/Repositories/Claude/.claude/settings.json")


def _conn() -> tuple[str, str]:
    env = json.load(open(SETTINGS))["env"]
    url = os.environ.get("HIVE_URL") or env["HIVE_URL"]
    token = os.environ.get("HIVE_TOKEN") or env["HIVE_TOKEN"]
    return url.rstrip("/"), token


def _get(base: str, token: str, path: str):
    req = urllib.request.Request(base + path, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def assemble() -> dict:
    base, token = _conn()
    topics = _get(base, token, "/graph/topics")
    briefs = _get(base, token, "/graph/nodes-brief")

    nodes: dict[str, dict] = {}
    for t in topics.get("topics", []):
        nodes[t["uid"]] = {"id": t["uid"], "title": t["title"], "type": "topic",
                           "children": t.get("children", 0)}
    for b in briefs:
        nodes[b["uid"]] = {"id": b["uid"], "title": b["title"], "type": b["type"],
                           "tags": b.get("tags", []), "topics": b.get("topics", [])}

    links: dict[tuple, dict] = {}

    def add_link(src: str, dst: str, rel: str):
        if src not in nodes or dst not in nodes:
            return
        key = (src, dst, rel) if rel == "CONTAINS" else (min(src, dst), max(src, dst), rel)
        links.setdefault(key, {"source": key[0] if rel != "CONTAINS" else src,
                               "target": key[1] if rel != "CONTAINS" else dst, "rel": rel})

    for e in topics.get("edges", []):
        add_link(e["parent"], e["child"], "CONTAINS")

    total = len(briefs)
    for i, b in enumerate(briefs):
        try:
            data = _get(base, token, f"/graph/neighbors/{b['uid']}")
        except Exception as exc:  # a single missing node must not kill the assembly
            print(f"  ! neighbors({b['uid'][:8]}…) failed: {exc}", file=sys.stderr)
            continue
        node = nodes[b["uid"]]
        node["use_count"] = data.get("use_count", 0)
        node["pagerank"] = data.get("pagerank", 0)
        node["lifecycle"] = data.get("lifecycle", "")
        node["scope"] = data.get("scope", "")
        for nb in data.get("neighbors", []):
            if not nb.get("uid"):
                continue
            if nb["direction"] == "out":
                add_link(b["uid"], nb["uid"], nb["relation"])
            else:
                add_link(nb["uid"], b["uid"], nb["relation"])
        if (i + 1) % 25 == 0:
            print(f"  … {i + 1}/{total} nodes", file=sys.stderr)

    graph = {"nodes": list(nodes.values()), "links": list(links.values())}
    json.dump(graph, open(CACHE, "w"))
    print(f"assembled: {len(graph['nodes'])} nodes, {len(graph['links'])} links", file=sys.stderr)
    return graph


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=HERE, **kw)

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/data.json"):
            refresh = "refresh=1" in self.path
            if not refresh and os.path.exists(CACHE):
                return self._json(json.load(open(CACHE)))
            try:
                return self._json(assemble())
            except Exception as exc:
                return self._json({"error": str(exc)}, 502)
        if self.path.startswith("/meta.json"):
            try:
                base, _ = _conn()
                return self._json({"hive_url": base})
            except Exception as exc:
                return self._json({"error": str(exc)}, 502)
        if self.path.startswith("/api/node/"):
            uid = self.path.split("/api/node/", 1)[1].split("?")[0]
            try:
                base, token = _conn()
                return self._json(_get(base, token, f"/graph/node/{uid}"))
            except Exception as exc:
                return self._json({"error": str(exc)}, 502)
        return super().do_GET()

    def log_message(self, fmt, *args):  # quiet static noise, keep errors
        if "data.json" in (args[0] if args else ""):
            super().log_message(fmt, *args)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8090
    print(f"3D HUD prototype on http://localhost:{port}  (data: live hive via proxy)")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
