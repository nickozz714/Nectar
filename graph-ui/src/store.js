/**
 * Graph model + d3-force layout for the Nectar mind graph.
 *
 * The model (nodes/links/selection/filters) lives OUTSIDE React in this mutable store;
 * the React Flow component subscribes via useSyncExternalStore. The vanilla index.html
 * talks to it through the imperative API in main.jsx. The d3 simulation only runs while
 * the layout is settling (alpha decays to 0) — there is no permanent render loop.
 */
import {
  forceSimulation, forceLink, forceManyBody, forceCollide, forceX, forceY,
} from "d3-force";

const listeners = new Set();

export const store = {
  bridge: null,          // { api, colors, hiveColor, attColor, hiveUid, hiveTitle,
                         //   onShowNode, onAttachmentOpen, onSelectionCleared }
  rf: null,              // ReactFlow instance (zoom / fitView)
  nodes: [],             // mutable sim nodes: {id,title,type,x,y,vx,vy,fx,fy,attUid,filename}
  byId: new Map(),
  links: [],             // {a,b,rel} — a is the parent/source side (directed)
  linkKeys: new Set(),
  expanded: new Set(),
  selectedUid: null,
  projectRoot: null,     // pinned project-topic centre (project filter), or null
  sciFi: false,
  visibleTypes: null,    // Set of visible types; null = everything visible
  version: 0,
  detail: new Map(),     // uid -> {loading:true} | {data} — tooltip detail cache
};

function notify() { store.version++; listeners.forEach((l) => l()); }
export const subscribe = (l) => { listeners.add(l); return () => listeners.delete(l); };
export const getVersion = () => store.version;

export function typeVisible(t) {
  return t === "hive" || t === "attachment" || !store.visibleTypes || store.visibleTypes.has(t);
}

const RADIUS = { hive: 26, topic: 16, attachment: 7 };
export const nodeRadius = (t) => RADIUS[t] ?? 10;

export function nodeColor(n) {
  const b = store.bridge;
  if (n.type === "hive") return b.hiveColor;
  if (n.type === "attachment") return b.attColor;
  return b.colors[n.type] || "#8d99ae";
}

// Collision radius covers the circle AND the label hanging under it, so labels can't overlap.
function collideRadius(n) {
  const label = Math.min((n.title || "").length, 28);
  return Math.max(nodeRadius(n.type) + 16, label * 2.9);
}

/* ---------- simulation ---------- */
let sim = null;
function ensureSim() {
  if (sim) return sim;
  sim = forceSimulation([])
    .force("charge", forceManyBody().strength(-320).distanceMax(1200))
    .force("collide", forceCollide().radius(collideRadius).strength(0.85))
    .force("x", forceX(0).strength(0.025))
    .force("y", forceY(0).strength(0.025))
    .alphaDecay(0.035)
    .velocityDecay(0.35)
    .on("tick", notify);
  return sim;
}

function reheat(alpha = 0.6) {
  const s = ensureSim();
  s.nodes(store.nodes);
  s.force("link", forceLink(store.links.map((l) => ({ source: l.a, target: l.b })))
    .id((n) => n.id)
    .distance((l) => (l.source.type === "hive" || l.target.type === "hive" ? 250
      : l.source.type === "attachment" || l.target.type === "attachment" ? 90 : 190))
    .strength(0.5));
  s.alpha(alpha).restart();
  notify();
}

/* ---------- model mutations ---------- */
function addNodeRaw(n, seed) {
  if (store.byId.has(n.uid)) return store.byId.get(n.uid);
  const node = {
    id: n.uid, title: n.title || "", type: n.type || "memory",
    attUid: n.attUid, filename: n.filename,
    x: seed ? seed.x : (Math.random() - 0.5) * 400,
    y: seed ? seed.y : (Math.random() - 0.5) * 300,
    vx: 0, vy: 0, fx: null, fy: null,
  };
  store.nodes.push(node);
  store.byId.set(n.uid, node);
  return node;
}

function addLinkRaw(a, b, rel) {
  const k = a < b ? a + "|" + b : b + "|" + a;
  if (store.linkKeys.has(k) || a === b) return;
  store.linkKeys.add(k);
  store.links.push({ a, b, rel: rel || "contains" });
}

function resetModel() {
  store.nodes = [];
  store.byId.clear();
  store.links = [];
  store.linkKeys.clear();
  store.expanded.clear();
  store.selectedUid = null;
  store.projectRoot = null;
}

/* The node this one hangs off (first parent via a directed link), so we know which way
   is "inward" and can fan new children outward like a branch. */
function parentAnchor(uid) {
  for (const l of store.links)
    if (l.b === uid && l.a !== uid && store.byId.has(l.a)) return store.byId.get(l.a);
  return { x: 0, y: 0 };
}
function parentUidOf(uid) {
  for (const l of store.links)
    if (l.b === uid && l.a !== uid && store.byId.has(l.a)) return l.a;
  return null;
}

// Fan freshly-shown children into an OUTWARD arc, away from the parent's own parent —
// the collide force then relaxes them without hairballs.
function placeRadially(parentUid, childUids) {
  const p = store.byId.get(parentUid);
  if (!p || !childUids.length) return;
  const n = childUids.length;
  const radius = Math.max(230, 120 + n * 26);
  const anchor = parentAnchor(parentUid);
  let dx = p.x - anchor.x, dy = p.y - anchor.y, len = Math.hypot(dx, dy);
  if (len < 1) { dx = p.x; dy = p.y; len = Math.hypot(dx, dy); }
  const base = len < 1 ? 0 : Math.atan2(dy, dx);
  const span = Math.min(Math.PI, 0.6 + n * 0.3);
  const step = n > 1 ? span / (n - 1) : 0;
  childUids.forEach((k, i) => {
    const node = store.byId.get(k);
    if (!node) return;
    const ang = base + (i - (n - 1) / 2) * step;
    node.x = p.x + radius * Math.cos(ang);
    node.y = p.y + radius * Math.sin(ang);
    node.vx = node.vy = 0;
  });
}

/* ---------- collapse (ported from the old SVG graph) ---------- */
function adjacency() {
  const m = new Map();
  const add = (a, b) => { (m.get(a) || m.set(a, new Set()).get(a)).add(b); };
  for (const l of store.links) { add(l.a, l.b); add(l.b, l.a); }
  return m;
}
// nodes reachable from `start` without ever passing THROUGH `block`
function reach(start, block) {
  const adj = adjacency(), seen = new Set([start]), q = [start];
  while (q.length) {
    const u = q.shift();
    if (u === block) continue;
    for (const v of adj.get(u) || []) if (!seen.has(v)) { seen.add(v); q.push(v); }
  }
  return seen;
}

export function collapseNode(uid) {
  const childAdj = new Map();
  for (const l of store.links)
    (childAdj.get(l.a) || childAdj.set(l.a, []).get(l.a)).push(l.b);
  const desc = new Set(); const q = [uid];
  while (q.length) {
    const u = q.shift();
    for (const c of childAdj.get(u) || [])
      if (c !== uid && !desc.has(c)) { desc.add(c); q.push(c); }
  }
  // keep descendants still anchored elsewhere (reachable from the hub without passing uid)
  const hubUid = store.projectRoot || store.bridge.hiveUid;
  const blocked = reach(hubUid, uid);
  const gone = new Set([...desc].filter((d) => !blocked.has(d)));
  store.expanded.delete(uid);
  if (!gone.size) { notify(); return; }
  store.nodes = store.nodes.filter((n) => !gone.has(n.id));
  for (const k of gone) {
    store.byId.delete(k);
    store.expanded.delete(k);
    if (store.selectedUid === k) store.selectedUid = null;
  }
  store.links = store.links.filter((l) => !gone.has(l.a) && !gone.has(l.b));
  store.linkKeys.clear();
  for (const l of store.links)
    store.linkKeys.add(l.a < l.b ? l.a + "|" + l.b : l.b + "|" + l.a);
  reheat(0.3);
}

export function hasVisibleChildren(uid) {
  return store.links.some((l) =>
    l.a === uid && store.byId.has(l.b) && typeVisible(store.byId.get(l.b).type));
}

/* ---------- public operations (called from main.jsx and the component) ---------- */
export function init(bridge) { store.bridge = bridge; }

export function setRoot(topLevelTopics) {
  resetModel();
  const hub = addNodeRaw({ uid: store.bridge.hiveUid, title: store.bridge.hiveTitle || "Nectar", type: "hive" });
  hub.fx = 0; hub.fy = 0;
  const n = topLevelTopics.length || 1;
  topLevelTopics.forEach((t, i) => {
    const ang = (i / n) * 2 * Math.PI;
    addNodeRaw({ uid: t.uid, title: t.title, type: "topic" },
      { x: 260 * Math.cos(ang), y: 260 * Math.sin(ang) });
    addLinkRaw(store.bridge.hiveUid, t.uid, "bevat");
  });
  reheat(0.9);
}

export function clearAll() { resetModel(); reheat(0); }

export async function expand(uid) {
  if (uid === store.bridge.hiveUid || uid.startsWith("att:")) return;
  const data = await store.bridge.api("/graph/neighbors/" + uid);
  const seedNear = store.byId.get(uid);
  addNodeRaw(data, seedNear ? null : { x: 0, y: 0 });
  const fresh = [];
  for (const nb of data.neighbors) {
    const existed = store.byId.has(nb.uid);
    addNodeRaw(nb);
    const rel = (nb.relation || "CONTAINS").toLowerCase();
    if (nb.direction === "out") addLinkRaw(uid, nb.uid, rel);
    else addLinkRaw(nb.uid, uid, rel);
    if (!existed) fresh.push(nb.uid);
  }
  try {
    for (const a of await store.bridge.api("/graph/node/" + uid + "/attachments")) {
      const nid = "att:" + a.uid;
      const existed = store.byId.has(nid);
      addNodeRaw({ uid: nid, title: a.filename, type: "attachment", attUid: a.uid, filename: a.filename });
      addLinkRaw(uid, nid, "bijlage");
      if (!existed) fresh.push(nid);
    }
  } catch (e) { /* attachments optional */ }
  if (store.projectRoot === uid) {
    const root = store.byId.get(uid);
    if (root) { root.fx = 0; root.fy = 0; }
  }
  placeRadially(uid, fresh);
  store.expanded.add(uid);
  reheat(0.5);
}

export async function select(uid) {
  const b = store.bridge;
  if (uid.startsWith("att:")) {
    const a = store.byId.get(uid);
    if (a) b.onAttachmentOpen(a.attUid, a.filename);
    return;
  }
  if (uid === b.hiveUid) { store.selectedUid = uid; notify(); return; }
  store.selectedUid = uid;
  notify();
  await b.onShowNode(uid);
}

export function deselect() {
  store.selectedUid = null;
  notify();
}

// Single click: attachment → preview; hive → soft focus; anything else → panel + expand.
export async function clickNode(uid) {
  if (uid.startsWith("att:") || uid === store.bridge.hiveUid) { await select(uid); return; }
  await select(uid);
  await expand(uid);
}

export async function jumpTo(uid) {
  await expand(uid);
  await select(uid);
}

// Collapse a subtree and walk the focus back up to its parent.
export function collapseAndFocusParent(uid) {
  const b = store.bridge;
  if (uid === b.hiveUid || uid.startsWith("att:")) return;
  const parent = parentUidOf(uid);
  collapseNode(uid);
  if (parent && parent !== b.hiveUid && store.byId.has(parent)) { select(parent); return; }
  store.selectedUid = parent === b.hiveUid ? b.hiveUid : null;
  b.onSelectionCleared();
  notify();
}

export function removeNode(uid) {
  if (!store.byId.has(uid)) return;
  store.nodes = store.nodes.filter((n) => n.id !== uid);
  store.byId.delete(uid);
  store.links = store.links.filter((l) => l.a !== uid && l.b !== uid);
  store.linkKeys.clear();
  for (const l of store.links)
    store.linkKeys.add(l.a < l.b ? l.a + "|" + l.b : l.b + "|" + l.a);
  store.expanded.delete(uid);
  if (store.selectedUid === uid) store.selectedUid = null;
  reheat(0.3);
}

export async function setProject(uid, title) {
  resetModel();
  if (!uid) return;   // caller reloads topics for the full-hub view
  store.projectRoot = uid;
  const root = addNodeRaw({ uid, title: title || "project", type: "topic" }, { x: 0, y: 0 });
  root.fx = 0; root.fy = 0;
  await expand(uid);
}

export function setTypeFilter(types) {
  store.visibleTypes = new Set(types);
  notify();
}

export function setSciFi(on) {
  store.sciFi = !!on;
  notify();
}

/* ---------- tooltip detail (lazy, cached) ---------- */
export function fetchDetail(uid) {
  const cached = store.detail.get(uid);
  if (cached) return cached.data || null;
  store.detail.set(uid, { loading: true });
  store.bridge.api("/graph/node/" + uid)
    .then((data) => { store.detail.set(uid, { data }); notify(); })
    .catch(() => { store.detail.set(uid, { data: null }); });
  return null;
}

/* ---------- dragging (React Flow drives, the sim follows) ---------- */
export function dragStart(uid) {
  const n = store.byId.get(uid);
  if (!n) return;
  n.fx = n.x; n.fy = n.y;
}
export function drag(uid, pos) {
  const n = store.byId.get(uid);
  if (!n) return;
  n.x = n.fx = pos.x;
  n.y = n.fy = pos.y;
  ensureSim().alphaTarget(0.15).restart();
}
export function dragStop(uid) {
  const n = store.byId.get(uid);
  ensureSim().alphaTarget(0);
  if (!n) return;
  const pinned = uid === store.bridge.hiveUid || uid === store.projectRoot;
  if (!pinned) { n.fx = null; n.fy = null; }
}

/* ---------- viewport ---------- */
export function zoomIn() { store.rf?.zoomIn({ duration: 180 }); }
export function zoomOut() { store.rf?.zoomOut({ duration: 180 }); }
export function fit() { store.rf?.fitView({ padding: 0.18, duration: 300 }); }
export function getSelected() { return store.selectedUid; }
