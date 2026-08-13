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
  .graphData(data)
  .showNavInfo(false)
  .nodeId("id")
  .nodeVal(sizeOf)
  .nodeLabel(n => n.type === "topic" ? "" :
    `<span style="color:${colorOf(n)}">◈ ${esc(n.type)}</span> &nbsp;${esc(n.title)}`)
  .nodeThreeObjectExtend(false)
  .nodeThreeObject(n => {
    const r = 2.4 * Math.cbrt(sizeOf(n)) * (n.type === "topic" ? 1.35 : 1);
    const col = new THREE.Color(colorOf(n));
    const group = new THREE.Group();
    const mat = new THREE.MeshStandardMaterial({
      color: col.clone().multiplyScalar(0.22),          // dark body…
      emissive: col, emissiveIntensity: 0.7,            // …that radiates its own hue
      roughness: 0.35, metalness: 0.15,
    });
    group.add(new THREE.Mesh(new THREE.SphereGeometry(r, 24, 24), mat));
    const halo = new THREE.Sprite(new THREE.SpriteMaterial({
      map: haloTex, color: col, transparent: true, opacity: 0.22,
      blending: THREE.AdditiveBlending, depthWrite: false,
    }));
    halo.scale.set(r * 6.5, r * 6.5, 1);
    group.add(halo);
    n.__mat = mat; n.__halo = halo.material;
    if (n.type === "topic") {
      const s = new SpriteText(n.title, 4.2, "#ffcf8a");
      s.fontFace = "Menlo, monospace";
      s.backgroundColor = false;
      s.strokeColor = "#02040a";
      s.strokeWidth = 1.6;
      s.material.depthWrite = false;
      s.position.y = r + 5;
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
    const active = state.hovered && (linkSrc(l) === state.hovered.id || linkTgt(l) === state.hovered.id);
    if (active) return "#bfeaff";
    return l.rel === "CONTAINS" ? "#6b4d1e" : "#1c5a6b";
  })
  .linkOpacity(0.2)
  .linkWidth(l => (state.hovered && (linkSrc(l) === state.hovered.id || linkTgt(l) === state.hovered.id)) ? 1.2 : 0)
  .linkDirectionalParticles(l => l.rel === "CONTAINS" ? 1 : 0)
  .linkDirectionalParticleSpeed(0.0028)
  .linkDirectionalParticleWidth(1.0)
  .linkDirectionalParticleColor(l => l.rel === "CONTAINS" ? "#e8a13d" : "#2fb8d8")
  .onNodeHover(n => {
    for (const m of litNodes) { if (m.__mat) { m.__mat.emissiveIntensity = 0.7; m.__halo.opacity = 0.22; } }
    litNodes.length = 0;
    state.hovered = n || null;
    el("graph").style.cursor = n ? "pointer" : "default";
    if (n) {
      const set = [n, ...[...(nbrs.get(n.id) || [])].map(id => nodeById.get(id))];
      for (const m of set) {
        if (!m?.__mat) continue;
        m.__mat.emissiveIntensity = 1.5; m.__halo.opacity = 0.45;
        litNodes.push(m);
      }
    }
    Graph.linkColor(Graph.linkColor());
    Graph.linkWidth(Graph.linkWidth());
  })
  .onNodeClick(n => select(n, true))
  .onBackgroundClick(() => { closePanel(); });

const nodeById = new Map(data.nodes.map(n => [n.id, n]));

/* ---- cinematics: bloom + fog + starfield + idle auto-rotate ---- */
// middle ground: enough bloom to make the emissive cores sing, threshold high
// enough that nothing blows out to white
const bloom = new UnrealBloomPass(new THREE.Vector2(innerWidth, innerHeight), 0.75, 0.45, 0.18);
Graph.postProcessingComposer().addPass(bloom);
Graph.scene().fog = new THREE.FogExp2(0x020409, 0.0009);   // depth cue: distance fades out

/* more air between clusters — clarity over density */
Graph.d3Force("charge").strength(-95);
Graph.d3Force("link").distance(l => (l.rel === "CONTAINS" ? 34 : 58));

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
    color: 0x6f8398, size: 1.0, transparent: true, opacity: 0.3, sizeAttenuation: false })));
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
