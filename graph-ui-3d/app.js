/* NECTAR // MIND — 3D HUD prototype.
   3d-force-graph (three.js/WebGL) over the live hive graph served by serve.py.
   Single deliberate theme: deep-space dark with honey/cyan HUD chrome. */
import ForceGraph3D from "3d-force-graph";
import SpriteText from "three-spritetext";
import * as THREE from "three";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";

const COLORS = {
  topic: "#ffb547",
  memory: "#3ee0ff",
  decision: "#ff7847",
  learning: "#55ffa1",
  process: "#9fd0ff",
  workflow: "#b39bff",
  skill: "#b39bff",
  convention: "#ffd66e",
  glossary: "#7f96b3",
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
};

const linkSrc = l => (typeof l.source === "object" ? l.source.id : l.source);
const linkTgt = l => (typeof l.target === "object" ? l.target.id : l.target);

const nodeVisible = n =>
  !state.hiddenTypes.has(n.type) && (!state.isolated || state.isolated.has(n.id));

const Graph = new ForceGraph3D(el("graph"), { controlType: "orbit" })
  .backgroundColor("#020409")
  .graphData(data)
  .showNavInfo(false)
  .nodeId("id")
  .nodeVal(n => n.type === "topic"
    ? Math.min(14, 5 + (n.children || 0) * 0.35)
    : Math.min(9, 1.6 + (n.use_count || 0) * 0.12 + (n.pagerank || 0) * 26))
  .nodeColor(n => {
    if (state.hovered && (n === state.hovered || nbrs.get(state.hovered.id)?.has(n.id))) return "#ffffff";
    return colorOf(n);
  })
  .nodeOpacity(0.92)
  .nodeResolution(14)
  .nodeLabel(n => n.type === "topic" ? "" :
    `<span style="color:${colorOf(n)}">◈ ${esc(n.type)}</span> &nbsp;${esc(n.title)}`)
  .nodeThreeObjectExtend(true)
  .nodeThreeObject(n => {
    if (n.type !== "topic") return undefined;
    const s = new SpriteText(n.title, 3.4, "#ffd9a0");
    s.fontFace = "Menlo, monospace";
    s.backgroundColor = false;
    s.material.depthWrite = false;
    s.center.y = -0.9;
    return s;
  })
  .nodeVisibility(nodeVisible)
  .linkVisibility(l => {
    const s = linkSrc(l), t = linkTgt(l);
    const sn = nodeById.get(s), tn = nodeById.get(t);
    return sn && tn && nodeVisible(sn) && nodeVisible(tn);
  })
  .linkColor(l => {
    const active = state.hovered && (linkSrc(l) === state.hovered.id || linkTgt(l) === state.hovered.id);
    if (active) return "#ffffff";
    return l.rel === "CONTAINS" ? "#8a6220" : "#1f6f82";
  })
  .linkOpacity(0.35)
  .linkWidth(l => (state.hovered && (linkSrc(l) === state.hovered.id || linkTgt(l) === state.hovered.id)) ? 1.2 : 0)
  .linkDirectionalParticles(l => l.rel === "CONTAINS" ? 1 : 0)
  .linkDirectionalParticleSpeed(0.0038)
  .linkDirectionalParticleWidth(1.5)
  .linkDirectionalParticleColor(l => l.rel === "CONTAINS" ? "#ffb547" : "#3ee0ff")
  .onNodeHover(n => {
    state.hovered = n || null;
    el("graph").style.cursor = n ? "pointer" : "default";
    Graph.nodeColor(Graph.nodeColor());   // re-evaluate accessors
    Graph.linkColor(Graph.linkColor());
    Graph.linkWidth(Graph.linkWidth());
  })
  .onNodeClick(n => select(n, true))
  .onBackgroundClick(() => { closePanel(); });

const nodeById = new Map(data.nodes.map(n => [n.id, n]));

/* ---- cinematics: bloom + starfield + idle auto-rotate ---- */
const bloom = new UnrealBloomPass(new THREE.Vector2(innerWidth, innerHeight), 1.15, 0.6, 0.05);
Graph.postProcessingComposer().addPass(bloom);

{
  const g = new THREE.BufferGeometry();
  const pos = new Float32Array(1400 * 3);
  for (let i = 0; i < 1400; i++) {
    const r = 900 + Math.random() * 1600, th = Math.random() * Math.PI * 2, ph = Math.acos(2 * Math.random() - 1);
    pos[i * 3] = r * Math.sin(ph) * Math.cos(th);
    pos[i * 3 + 1] = r * Math.sin(ph) * Math.sin(th);
    pos[i * 3 + 2] = r * Math.cos(ph);
  }
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  Graph.scene().add(new THREE.Points(g, new THREE.PointsMaterial({
    color: 0x8fa8c0, size: 1.1, transparent: true, opacity: 0.45, sizeAttenuation: false })));
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
function flyTo(n) {
  const d = 130, hyp = Math.hypot(n.x, n.y, n.z) || 1, k = 1 + d / hyp;
  Graph.cameraPosition({ x: n.x * k, y: n.y * k, z: n.z * k }, n, 1400);
}

async function select(n, fly) {
  state.selected = n;
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
  if (n) select(n, true);
});
document.addEventListener("keydown", e => {
  if (e.key === "/" && document.activeElement !== searchEl) { e.preventDefault(); searchEl.focus(); }
  if (e.key === "Escape") { resultsEl.style.display = "none"; closePanel(); }
});

/* ---- type filter chips + stats ---- */
function buildFilters() {
  const counts = {};
  for (const n of data.nodes) counts[n.type] = (counts[n.type] || 0) + 1;
  el("filters").innerHTML = Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([t, c]) =>
    `<span class="chip ${state.hiddenTypes.has(t) ? "off" : ""}" data-t="${t}">
       <span class="dot" style="background:${COLORS[t] || "#8fa3b8"}"></span>${esc(t)} <b>${c}</b></span>`).join("");
}
el("filters").addEventListener("click", e => {
  const t = e.target.closest(".chip")?.dataset.t;
  if (!t) return;
  state.hiddenTypes.has(t) ? state.hiddenTypes.delete(t) : state.hiddenTypes.add(t);
  refreshVisibility();
});
buildFilters();

el("stats").innerHTML =
  `<div><b>${data.nodes.length}</b> nodes · <b>${data.links.length}</b> links</div>
   <div>verbinding <span class="ok">● live</span> · druk <b>/</b> om te zoeken</div>`;

el("refresh").onclick = async () => {
  el("refresh").textContent = "⟳ herladen…";
  const fresh = await (await fetch("./data.json?refresh=1")).json();
  if (!fresh.error) location.reload();
};

/* camera intro: pull back then settle */
Graph.cameraPosition({ x: 0, y: 0, z: 900 });
setTimeout(() => Graph.zoomToFit(1600, 60), 1200);

el("splash").remove();
