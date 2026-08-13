/* NECTAR // MIND — 3D HUD prototype.
   3d-force-graph (three.js/WebGL) over the live hive graph served by serve.py.
   Single deliberate theme: deep-space dark with honey/cyan HUD chrome. */
import ForceGraph3D from "3d-force-graph";
import SpriteText from "three-spritetext";
import * as THREE from "three";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";

/* mid-bright saturated hues: dark cores EMIT these colors and a soft additive halo
   carries the aura — the glow lives in the material, not in an overdriven bloom pass */
const COLORS = {
  topic: "#f0a63a",
  memory: "#2fc4e8",
  decision: "#ff6a45",
  learning: "#43d98a",
  process: "#5fa4e6",
  workflow: "#8f76e8",
  skill: "#a06ae8",
  convention: "#e6c05c",
  glossary: "#6d87a0",
};
const colorOf = n => COLORS[n.type] || "#8fa3b8";

const el = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const res = await fetch("./data.json");
const data = await res.json();
if (data.error) {
  el("splash").innerHTML = `<div class="t" style="color:#ff7847">hive onbereikbaar: ${esc(data.error)}</div>`;
  throw new Error(data.error);
}

/* degree for sizing + neighbor lookup for highlight/isolate */
const nbrs = new Map(data.nodes.map(n => [n.id, new Set()]));
const degree = new Map(data.nodes.map(n => [n.id, 0]));
for (const l of data.links) {
  const s = typeof l.source === "object" ? l.source.id : l.source;
  const t = typeof l.target === "object" ? l.target.id : l.target;
  nbrs.get(s)?.add(t); nbrs.get(t)?.add(s);
  degree.set(s, (degree.get(s) || 0) + 1);
  degree.set(t, (degree.get(t) || 0) + 1);
}

const state = {
  selected: null,           // node object
  hovered: null,
  isolated: null,           // Set of visible ids when isolating
  hiddenTypes: new Set(),
  expanded: new Set(),      // topic ids whose children are shown (cortex mode)
  showAll: true,            // default: the whole organism; cortex mode is the option
};

const litNodes = [];
const linkSrc = l => (typeof l.source === "object" ? l.source.id : l.source);
const linkTgt = l => (typeof l.target === "object" ? l.target.id : l.target);

const nodeVisible = n =>
  !state.hiddenTypes.has(n.type) && (!state.isolated || state.isolated.has(n.id));

/* soft radial halo texture, tinted per node via sprite material color */
const haloTex = (() => {
  const c = document.createElement("canvas"); c.width = c.height = 128;
  const ctx = c.getContext("2d");
  const g = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
  g.addColorStop(0, "rgba(255,255,255,.8)");
  g.addColorStop(0.3, "rgba(255,255,255,.22)");
  g.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = g; ctx.fillRect(0, 0, 128, 128);
  return new THREE.CanvasTexture(c);
})();

const sizeOf = n => n.type === "topic"
  ? Math.min(16, 6 + (n.children || 0) * 0.4)
  : Math.min(5, 1.2 + (n.use_count || 0) * 0.06 + (n.pagerank || 0) * 14);

const Graph = new ForceGraph3D(el("graph"), { controlType: "orbit" })
  .backgroundColor("#020409")
  .showNavInfo(false)
  .nodeId("id")
  .nodeVal(sizeOf)
  .nodeLabel(n => n.type === "topic" ? "" :
    `<span style="color:${colorOf(n)}">◈ ${esc(n.type)}</span> &nbsp;${esc(n.title)}`)
  .nodeThreeObjectExtend(false)
  .nodeThreeObject(n => {
    /* neural look: SMALL bright points, the network reads through its links */
    const r = 1.3 * Math.cbrt(sizeOf(n)) * (n.type === "topic" ? 1.25 : 1.12);
    const col = new THREE.Color(colorOf(n));
    const group = new THREE.Group();
    const mat = new THREE.MeshStandardMaterial({
      color: col.clone().multiplyScalar(0.22),          // dark body…
      emissive: col, emissiveIntensity: 0.85,           // …that radiates its own hue
      roughness: 0.35, metalness: 0.15,
    });
    group.add(new THREE.Mesh(new THREE.SphereGeometry(r, 20, 20), mat));
    const halo = new THREE.Sprite(new THREE.SpriteMaterial({
      map: haloTex, color: col, transparent: true,
      opacity: n.type === "topic" ? 0.11 : 0.09,
      blending: THREE.AdditiveBlending, depthWrite: false,
    }));
    halo.scale.set(r * 3.6, r * 3.6, 1);
    group.add(halo);
    n.__mat = mat; n.__halo = halo.material; n.__haloBase = halo.material.opacity;
    if (n.type === "topic" && (n.children || 0) >= 6) {   // labels only where they earn it
      const s = new SpriteText(n.title, 2.9, "#ffe2b8");
      s.fontFace = "Menlo, monospace";
      s.backgroundColor = false;
      s.strokeColor = "#02040a";
      s.strokeWidth = 1.4;
      s.material.depthWrite = false;
      s.position.y = r + 4;
      group.add(s);
    }
    return group;
  })
  .nodeVisibility(nodeVisible)
  .linkVisibility(l => {
    const s = linkSrc(l), t = linkTgt(l);
    const sn = nodeById.get(s), tn = nodeById.get(t);
    return sn && tn && nodeVisible(sn) && nodeVisible(tn);
  })
  .linkColor(l => {
    const s = linkSrc(l), t = linkTgt(l);
    if (state.hovered && (s === state.hovered.id || t === state.hovered.id)) return "#bfeaff";
    if (state.selected) {                    // focus mode: only the selection's wiring lights up
      if (s === state.selected.id || t === state.selected.id) return "#9fd8ea";
      return "#0d1826";
    }
    return l.rel === "CONTAINS" ? "#8a6a30" : "#2a7a90";
  })
  .linkOpacity(0.32)
  .linkWidth(l => (state.hovered && (linkSrc(l) === state.hovered.id || linkTgt(l) === state.hovered.id)) ? 1.2 : 0)
  .linkDirectionalParticles(0)              // no constant traffic — synapses FIRE (see pulse loop)
  .linkDirectionalParticleSpeed(0.006)
  .linkDirectionalParticleWidth(1.6)
  .linkDirectionalParticleColor(l => l.rel === "CONTAINS" ? "#e8a13d" : "#2fb8d8")
  .onNodeHover(n => {
    litNodes.length = 0;
    applyDim();                              // restore the selection-aware baseline
    state.hovered = n || null;
    el("graph").style.cursor = n ? "pointer" : "default";
    if (n) {
      const set = [n, ...[...(nbrs.get(n.id) || [])].map(id => nodeById.get(id))];
      for (const m of set) {
        if (!m?.__mat) continue;
        m.__base = 1.4; m.__halo.opacity = 0.3;
        litNodes.push(m);
      }
    }
    Graph.linkColor(Graph.linkColor());
    Graph.linkWidth(Graph.linkWidth());
  })
  .onNodeClick(n => {
    if (n.type === "topic") {                       // topics open/close their cluster
      state.expanded.has(n.id) ? state.expanded.delete(n.id) : state.expanded.add(n.id);
      applyGraph();
      select(n, false);
    } else select(n, true);
  })
  .onBackgroundClick(() => { closePanel(); });

const nodeById = new Map(data.nodes.map(n => [n.id, n]));

/* ---- progressive disclosure: cortex (topics) first, knowledge on demand ---- */
const topicChildren = new Map();                    // topic id -> [leaf ids]
for (const l of data.links) {
  if (l.rel !== "CONTAINS") continue;
  const s = linkSrc(l), t = linkTgt(l);
  if (nodeById.get(s)?.type === "topic" && nodeById.get(t)?.type !== "topic")
    (topicChildren.get(s) || topicChildren.set(s, []).get(s)).push(t);
}

function currentGraph() {
  const vis = new Set();
  for (const n of data.nodes) if (n.type === "topic" || state.showAll) vis.add(n.id);
  if (!state.showAll)
    for (const t of state.expanded) for (const c of topicChildren.get(t) || []) vis.add(c);
  return {
    nodes: data.nodes.filter(n => vis.has(n.id)),
    links: data.links.filter(l => vis.has(linkSrc(l)) && vis.has(linkTgt(l))),
  };
}

function applyGraph() {
  Graph.graphData(currentGraph());
  updateStats();
}

/* ---- cinematics: bloom + fog + starfield + idle auto-rotate ---- */
// middle ground: enough bloom to make the emissive cores sing, threshold high
// enough that nothing blows out to white
const bloom = new UnrealBloomPass(new THREE.Vector2(innerWidth, innerHeight), 0.55, 0.4, 0.2);
Graph.postProcessingComposer().addPass(bloom);
Graph.scene().fog = new THREE.FogExp2(0x020409, 0.0009);   // depth cue: distance fades out

/* hive anatomy: knowledge orbits tight around its topic, topics keep some distance,
   and a gentle pull toward the origin keeps loose pieces part of ONE organism */
Graph.d3Force("charge").strength(-32);
Graph.d3Force("link").distance(l => {
  if (l.rel === "RELATES") return 46;
  const tgt = nodeById.get(linkTgt(l));
  return tgt?.type === "topic" ? 62 : 20;   // topic↔topic wide, topic↔leaf tight
});
Graph.d3Force("cohere", (() => {
  let nodes = [];
  const f = alpha => {
    for (const n of nodes) {
      n.vx -= n.x * 0.018 * alpha;
      n.vy -= n.y * 0.018 * alpha;
      n.vz -= (n.z || 0) * 0.018 * alpha;
    }
  };
  f.initialize = ns => { nodes = ns; };
  return f;
})());

/* synapse firing: a few random visible links pulse a particle every beat */
setInterval(() => {
  const { links } = Graph.graphData();
  if (!links.length) return;
  const n = 1 + Math.floor(Math.random() * 2);
  for (let i = 0; i < n; i++)
    Graph.emitParticle(links[Math.floor(Math.random() * links.length)]);
}, 480);

/* breathing: every node's emissive core oscillates gently around its base level */
(function breathe() {
  const t = performance.now();
  for (const n of data.nodes)
    if (n.__mat)
      n.__mat.emissiveIntensity =
        (n.__base ?? 0.7) + 0.14 * Math.sin(t * 0.0016 + (n.__phase ??= Math.random() * 6.28));
  requestAnimationFrame(breathe);
})();

/* starry sky, two layers: faint dust + a sparser bright layer that twinkles past the fog */
for (const [count, size, opacity] of [[2000, 1.0, 0.4], [350, 1.7, 0.6]]) {
  const g = new THREE.BufferGeometry();
  const pos = new Float32Array(count * 3);
  for (let i = 0; i < count; i++) {
    const r = 900 + Math.random() * 1700, th = Math.random() * Math.PI * 2, ph = Math.acos(2 * Math.random() - 1);
    pos[i * 3] = r * Math.sin(ph) * Math.cos(th);
    pos[i * 3 + 1] = r * Math.sin(ph) * Math.sin(th);
    pos[i * 3 + 2] = r * Math.cos(ph);
  }
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  const stars = new THREE.Points(g, new THREE.PointsMaterial({
    color: 0x8fa8c0, size, transparent: true, opacity, sizeAttenuation: false, fog: false }));
  Graph.scene().add(stars);
}

const controls = Graph.controls();
controls.autoRotate = true;
controls.autoRotateSpeed = 0.35;
let idleTimer;
const wake = () => {
  controls.autoRotate = false;
  clearTimeout(idleTimer);
  idleTimer = setTimeout(() => { controls.autoRotate = true; }, 15000);
};
el("graph").addEventListener("pointerdown", wake);
el("graph").addEventListener("wheel", wake, { passive: true });

/* ---- selection, fly-to & detail panel ---- */
/* focus dimming: with a selection, everything outside it + its direct wiring recedes */
function applyDim() {
  const focus = state.selected
    ? new Set([state.selected.id, ...(nbrs.get(state.selected.id) || [])])
    : null;
  for (const n of data.nodes) {
    if (!n.__mat) continue;
    if (!focus) { n.__base = 0.7; n.__halo.opacity = n.__haloBase; }
    else if (n.id === state.selected.id) { n.__base = 1.6; n.__halo.opacity = 0.35; }
    else if (focus.has(n.id)) { n.__base = 1.0; n.__halo.opacity = 0.2; }
    else { n.__base = 0.1; n.__halo.opacity = 0.015; }
  }
  Graph.linkColor(Graph.linkColor());
}

function flyTo(n) {
  const d = 130, hyp = Math.hypot(n.x, n.y, n.z) || 1, k = 1 + d / hyp;
  Graph.cameraPosition({ x: n.x * k, y: n.y * k, z: n.z * k }, n, 1400);
}

async function select(n, fly) {
  state.selected = n;
  applyDim();
  if (fly) { wake(); flyTo(n); }
  el("pTitle").textContent = n.title;
  el("pChips").innerHTML =
    `<span class="pchip amber">${esc(n.type)}</span>` +
    (n.scope ? `<span class="pchip">${esc(n.scope)}</span>` : "") +
    (n.lifecycle ? `<span class="pchip">${esc(n.lifecycle)}</span>` : "") +
    `<span class="pchip">${degree.get(n.id) || 0} links</span>` +
    (n.use_count ? `<span class="pchip">${n.use_count}× gebruikt</span>` : "");
  el("pBody").textContent = "…";
  el("panel").classList.add("open");
  el("btnIsolate").textContent = state.isolated ? "toon alles" : "isolate";
  if (n.type === "topic") {
    const kids = [...(nbrs.get(n.id) || [])].map(id => nodeById.get(id)).filter(Boolean);
    el("pBody").innerHTML = kids.slice(0, 40).map(k =>
      `<div style="margin:2px 0"><span style="color:${colorOf(k)}">◈</span> ${esc(k.title)}</div>`).join("")
      || "leeg topic";
    return;
  }
  try {
    const full = await (await fetch(`/api/node/${n.id}`)).json();
    let html = esc(full.content || "");
    if (full.tags?.length) html += `\n\n<span style="color:var(--dim)">tags: ${esc(full.tags.join(", "))}</span>`;
    el("pBody").innerHTML = html;
  } catch { el("pBody").textContent = "(inhoud niet op te halen)"; }
}

function closePanel() {
  el("panel").classList.remove("open");
  state.selected = null;
  applyDim();
  if (state.isolated) { state.isolated = null; refreshVisibility(); }
}

function refreshVisibility() {
  Graph.nodeVisibility(Graph.nodeVisibility());
  Graph.linkVisibility(Graph.linkVisibility());
  buildFilters();
}

el("btnClose").onclick = closePanel;
el("btnIsolate").onclick = () => {
  if (!state.selected) return;
  if (state.isolated) { state.isolated = null; }
  else {
    const keep = new Set([state.selected.id]);
    for (const a of nbrs.get(state.selected.id) || []) {
      keep.add(a);
      for (const b of nbrs.get(a) || []) keep.add(b);   // 2 hops
    }
    state.isolated = keep;
  }
  el("btnIsolate").textContent = state.isolated ? "toon alles" : "isolate";
  refreshVisibility();
};

/* ---- search ---- */
const searchEl = el("search"), resultsEl = el("results");
searchEl.addEventListener("input", () => {
  const q = searchEl.value.trim().toLowerCase();
  if (q.length < 2) { resultsEl.style.display = "none"; return; }
  const hits = data.nodes.filter(n => n.title.toLowerCase().includes(q)).slice(0, 12);
  resultsEl.innerHTML = hits.map(n =>
    `<div data-id="${n.id}"><span class="dot" style="background:${colorOf(n)}"></span>${esc(n.title)}</div>`).join("")
    || `<div style="color:var(--dim)">geen hits</div>`;
  resultsEl.style.display = "block";
});
resultsEl.addEventListener("click", e => {
  const id = e.target.closest("[data-id]")?.dataset.id;
  if (!id) return;
  resultsEl.style.display = "none"; searchEl.value = "";
  const n = nodeById.get(id);
  if (!n) return;
  const onScreen = Graph.graphData().nodes.includes(n);
  if (!onScreen) {                       // hidden leaf: open its topic cluster first
    for (const [t, kids] of topicChildren) if (kids.includes(n.id)) { state.expanded.add(t); break; }
    applyGraph();
    setTimeout(() => select(n, true), 900);   // let the cluster settle, then fly in
  } else select(n, true);
});
document.addEventListener("keydown", e => {
  if (e.key === "/" && document.activeElement !== searchEl) { e.preventDefault(); searchEl.focus(); }
  if (e.key === "Escape") { resultsEl.style.display = "none"; closePanel(); }
});

/* ---- type filter chips + stats ---- */
function buildFilters() {
  const counts = {};
  for (const n of data.nodes) counts[n.type] = (counts[n.type] || 0) + 1;
  el("filters").innerHTML =
    `<span class="chip" data-mode="1" style="border-color:rgba(255,181,71,.4);color:var(--amber)">
       ${state.showAll ? "⊖ alleen cortex" : "⊕ alles tonen"}</span>` +
    Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([t, c]) =>
      `<span class="chip ${state.hiddenTypes.has(t) ? "off" : ""}" data-t="${t}">
         <span class="dot" style="background:${COLORS[t] || "#8fa3b8"}"></span>${esc(t)} <b>${c}</b></span>`).join("");
}
el("filters").addEventListener("click", e => {
  const chip = e.target.closest(".chip");
  if (!chip) return;
  if (chip.dataset.mode) {
    state.showAll = !state.showAll;
    if (!state.showAll) state.expanded.clear();
    applyGraph();
    setTimeout(() => Graph.zoomToFit(1200, 60), 900);
    return;
  }
  const t = chip.dataset.t;
  state.hiddenTypes.has(t) ? state.hiddenTypes.delete(t) : state.hiddenTypes.add(t);
  refreshVisibility();
});

function updateStats() {
  const g = currentGraph();
  buildFilters();
  el("stats").innerHTML =
    `<div><b>${g.nodes.length}</b>/<b>${data.nodes.length}</b> nodes zichtbaar · <b>${g.links.length}</b> links</div>
     <div>verbinding <span class="ok">● live</span> · klik een topic om z'n cluster te openen · <b>/</b> zoekt</div>`;
}

el("refresh").onclick = async () => {
  el("refresh").textContent = "⟳ herladen…";
  const fresh = await (await fetch("./data.json?refresh=1")).json();
  if (!fresh.error) location.reload();
};

/* the rest of the hive lives in the existing GUI — deep-link the HUD into it */
fetch("./meta.json").then(r => r.json()).then(meta => {
  if (!meta.hive_url) return;
  for (const a of document.querySelectorAll("#nav a")) {
    a.href = `${meta.hive_url}/ui#${a.dataset.tab}`;
    a.target = "_blank";
  }
}).catch(() => {});

/* boot: full organism, camera pulls in and settles */
applyGraph();
Graph.cameraPosition({ x: 0, y: 0, z: 900 });
setTimeout(() => Graph.zoomToFit(1600, 60), 1200);

el("splash").remove();
