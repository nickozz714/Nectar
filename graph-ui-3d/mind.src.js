/* NECTAR // MIND — MIX: galaxy-structuur + netwerk-modus + cockpit-drilldown.
   Overzicht in twee smaken (galaxy = alleen topics; netwerk = het hele organisme),
   klik een ster voor z'n stelsel, en drill een kennis-node met de cockpit-overlay
   (rechtsklik of de ⌕-knop in het paneel). */
import ForceGraph3D from "3d-force-graph";
import SpriteText from "three-spritetext";
import * as THREE from "three";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";

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
/* nooit uids tonen — een enkel topic draagt z'n uid als titel */
const UID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const titleOf = n => UID_RE.test(n.title) ? "(naamloos topic)" : n.title;
const trunc = (s, max) => s.length > max ? s.slice(0, max - 1).trimEnd() + "…" : s;

/* server-modus: geserveerd op /ui/mind draait deze pagina tegen de echte API met de
   GUI-login (Bearer uit localStorage); standalone (dev) valt hij terug op serve.py */
const SERVER = location.pathname.startsWith("/ui/");
const TOKEN = SERVER ? (localStorage.getItem("hive_token") || "") : "";
if (SERVER && !TOKEN) location.replace("/ui");
const AUTH = SERVER ? { headers: { Authorization: "Bearer " + TOKEN } } : undefined;
const NODE_URL = id => SERVER ? `/graph/node/${id}` : `/api/node/${id}`;

const res = await fetch(SERVER ? "/graph/full" : "./data.json", AUTH);
if (SERVER && (res.status === 401 || res.status === 403)) location.replace("/ui");
const data = await res.json();
if (data.error) {
  el("splash").innerHTML = `<div class="t" style="color:#ff7847">hive onbereikbaar: ${esc(data.error)}</div>`;
  throw new Error(data.error);
}

/* ---- indexen over de ruwe graaf ---- */
const nodeById = new Map(data.nodes.map(n => [n.id, n]));
const linkSrc = l => (typeof l.source === "object" ? l.source.id : l.source);
const linkTgt = l => (typeof l.target === "object" ? l.target.id : l.target);

const topicChildren = new Map();   // topic id -> [kennis-kind ids]
const parentTopic = new Map();     // kennisnode id -> topic id
const topicLinks = [];             // links tussen twee topics (voor niveau 1)
for (const l of data.links) {
  const s = linkSrc(l), t = linkTgt(l);
  const sn = nodeById.get(s), tn = nodeById.get(t);
  if (!sn || !tn) continue;
  if (sn.type === "topic" && tn.type === "topic") { topicLinks.push({ source: s, target: t, __kind: "tt" }); continue; }
  if (l.rel === "CONTAINS" && sn.type === "topic" && tn.type !== "topic") {
    (topicChildren.get(s) || topicChildren.set(s, []).get(s)).push(t);
    parentTopic.set(t, s);
  }
}
const degree = new Map();
for (const l of data.links) {
  degree.set(linkSrc(l), (degree.get(linkSrc(l)) || 0) + 1);
  degree.set(linkTgt(l), (degree.get(linkTgt(l)) || 0) + 1);
}
const topics = data.nodes.filter(n => n.type === "topic");
const knowledgeCount = data.nodes.length - topics.length;

/* ---- state ---- */
const state = {
  level: 1,          // 1 = overzicht (galaxy of netwerk), 2 = stelsel
  overview: "galaxy",// welke overzichtsmodus actief is
  topicId: null,     // actief stelsel
  selected: null,
  traveling: false,
};

/* niveau 1: de sterren houden hun posities vast over reizen heen */
const galaxyData = {
  nodes: topics.map(n => ({ ...n, __role: "star" })),
  links: topicLinks.map(l => ({ ...l })),
};

/* netwerk-modus: het hele organisme, posities blijven bewaard over wissels heen */
const organismData = {
  nodes: data.nodes.map(n => n.type === "topic"
    ? { ...n, __role: "star" } : { ...n, __role: "dot" }),
  links: data.links.map(l => {
    const s = linkSrc(l), t = linkTgt(l);
    const kind = l.rel === "RELATES" ? "rel"
      : (nodeById.get(s)?.type === "topic" && nodeById.get(t)?.type === "topic") ? "tt" : "sun";
    return { source: s, target: t, __kind: kind };
  }),
};

/* niveau 2: bouw het stelsel van één topic, vers (eigen posities) */
function systemData(topicId) {
  const topic = nodeById.get(topicId);
  const kidIds = topicChildren.get(topicId) || [];
  const inside = new Set([topicId, ...kidIds]);
  const nodes = [{ ...topic, __role: "sun", fx: 0, fy: 0, fz: 0 }];
  for (const id of kidIds) nodes.push({ ...nodeById.get(id), __role: "kid" });
  const links = kidIds.map(id => ({ source: topicId, target: id, __kind: "sun" }));
  const portals = new Map();       // externe node id -> portaal-node
  for (const l of data.links) {
    if (l.rel !== "RELATES") continue;
    const s = linkSrc(l), t = linkTgt(l);
    const sIn = inside.has(s), tIn = inside.has(t);
    if (sIn && tIn) { links.push({ source: s, target: t, __kind: "rel" }); continue; }
    if (!sIn && !tIn) continue;
    const inId = sIn ? s : t, outId = sIn ? t : s;
    const ext = nodeById.get(outId);
    if (!ext) continue;
    if (!portals.has(outId)) {
      portals.set(outId, { ...ext, __role: "portal" });
      nodes.push(portals.get(outId));
    }
    links.push({ source: inId, target: outId, __kind: "portal" });
  }
  return { nodes, links };
}

/* ---- rendering: donkere kern + emissive typekleur + additive halo ---- */
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

const starR = n => 2.4 + Math.min(6.5, (n.children || 0) * 0.3);
const kidR = n => Math.min(3.4, 1.5 + (n.use_count || 0) * 0.05 + (n.pagerank || 0) * 10);

function makeNode(n) {
  const role = n.__role;
  const col = new THREE.Color(colorOf(n));
  const r = role === "sun" ? 8.5 : role === "star" ? starR(n)
    : role === "portal" ? 1.0 : role === "dot" ? kidR(n) * 0.85 : kidR(n);
  const group = new THREE.Group();
  const dimmed = role === "portal";
  const mat = new THREE.MeshStandardMaterial({
    color: col.clone().multiplyScalar(dimmed ? 0.12 : 0.22),
    emissive: col,
    emissiveIntensity: dimmed ? 0.3 : role === "sun" ? 1.15 : 0.85,
    roughness: 0.35, metalness: 0.15,
  });
  group.add(new THREE.Mesh(new THREE.SphereGeometry(r, 20, 20), mat));
  const halo = new THREE.Sprite(new THREE.SpriteMaterial({
    map: haloTex, color: col, transparent: true,
    opacity: role === "sun" ? 0.22 : dimmed ? 0.04 : 0.11,
    blending: THREE.AdditiveBlending, depthWrite: false,
  }));
  halo.scale.set(r * (role === "sun" ? 4.4 : 3.6), r * (role === "sun" ? 4.4 : 3.6), 1);
  group.add(halo);
  n.__mat = mat;
  if (role === "dot") return group;   // netwerk-modus: kennis als stille lichtpunt, tooltip volstaat
  /* labels: op beide niveaus altijd zichtbaar — dat is het hele punt van weinig tonen */
  const size = role === "sun" ? 4.2
    : role === "star" ? (state.overview === "organism" && state.level === 1 ? 4.2 : 5.6)
    : role === "portal" ? 1.8 : 2.2;
  const color = role === "sun" || role === "star" ? "#ffe2b8" : role === "portal" ? "#748ba1" : "#b9d2e4";
  /* zonnen en sterren dragen hun volle naam; kennislabels kort — het paneel toont de rest */
  const text = role === "portal" ? `⇢ ${trunc(titleOf(n), 34)}`
    : role === "kid" ? trunc(titleOf(n), 44) : titleOf(n);
  const label = new SpriteText(text, size, color);
  label.fontFace = "Menlo, monospace";
  label.backgroundColor = false;
  label.strokeColor = "#02040a";
  label.strokeWidth = 1.5;
  label.material.depthWrite = false;
  label.material.transparent = true;
  label.position.y = r + (role === "sun" ? 6 : role === "star" ? 5 : 2.6);
  group.add(label);
  return group;
}

const LINK_COLORS = { tt: "#8a6a30", sun: "#8a6a30", rel: "#2a7a90", portal: "#3a4a5c" };

const Graph = new ForceGraph3D(el("graph"), { controlType: "orbit" })
  .backgroundColor("#020409")
  .showNavInfo(false)
  .nodeId("id")
  .nodeLabel(n => n.__role === "portal"
    ? `<span style="color:${colorOf(n)}">◈ ${esc(n.type)}</span> &nbsp;spring naar dit stelsel`
    : n.__role === "star" ? `<b>${esc(titleOf(n))}</b> · ${n.children || 0} kenniszaden`
    : `<span style="color:${colorOf(n)}">◈ ${esc(n.type)}</span> &nbsp;${esc(titleOf(n))}`)
  .onNodeRightClick(n => {
    if (n && n.__role !== "portal" && n.type !== "topic") openDrill(n.id);
  })
  .nodeThreeObjectExtend(false)
  .nodeThreeObject(makeNode)
  .linkColor(l => LINK_COLORS[l.__kind] || "#2a7a90")
  .linkOpacity(0.35)
  .linkWidth(0)
  .linkDirectionalParticles(0)
  .linkDirectionalParticleSpeed(0.006)
  .linkDirectionalParticleWidth(1.6)
  .linkDirectionalParticleColor(l => l.__kind === "rel" ? "#2fb8d8" : "#e8a13d")
  .onNodeHover(n => { el("graph").style.cursor = n ? "pointer" : "default"; })
  .onNodeClick(n => {
    if (state.traveling) return;
    if (state.level === 1) {
      if (n.type === "topic") { enterSystem(n.id); return; }
      select(n, true); return;   // netwerk-modus: kennis-node → paneel
    }
    if (n.__role === "portal") {
      const tid = n.type === "topic" ? n.id : parentTopic.get(n.id);
      if (tid) enterSystem(tid, { selectId: n.type === "topic" ? null : n.id, fromSystem: true });
      else select(n, false);
      return;
    }
    select(n, n.__role !== "sun");
  })
  .onBackgroundClick(() => closePanel());

/* krachten per niveau: galaxy ruim uit elkaar, stelsel compact rond de zon */
function tuneForces(mode) {
  const organism = mode === "organism";
  Graph.d3Force("charge").strength(organism ? -32 : mode === 1 ? -190 : -80);
  Graph.d3Force("link").distance(l => organism
    ? ({ tt: 62, sun: 20, rel: 46 }[l.__kind] || 46)
    : ({ tt: 110, sun: 62, rel: 48, portal: 30 }[l.__kind] || 60));
  /* zachte trek naar het centrum: losse sterren blijven deel van ÉÉN geheel */
  Graph.d3Force("cohere", (() => {
    const k = organism ? 0.018 : mode === 1 ? 0.03 : 0.015;
    let nodes = [];
    const f = alpha => {
      for (const n of nodes) {
        if (n.fx !== undefined) continue;
        n.vx -= n.x * k * alpha;
        n.vy -= n.y * k * alpha;
        n.vz -= (n.z || 0) * k * alpha;
      }
    };
    f.initialize = ns => { nodes = ns; };
    return f;
  })());
}

/* ---- cinematics: bloom + fog + sterrenhemel in twee lagen ---- */
const bloom = new UnrealBloomPass(new THREE.Vector2(innerWidth, innerHeight), 0.55, 0.4, 0.2);
Graph.postProcessingComposer().addPass(bloom);
Graph.scene().fog = new THREE.FogExp2(0x020409, 0.0009);

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
  Graph.scene().add(new THREE.Points(g, new THREE.PointsMaterial({
    color: 0x8fa8c0, size, transparent: true, opacity, sizeAttenuation: false, fog: false })));
}

/* ademende kernen */
(function frameLoop() {
  const t = performance.now();
  for (const n of Graph.graphData().nodes)
    if (n.__mat && n.__role !== "portal")
      n.__mat.emissiveIntensity =
        (n.__role === "sun" ? 1.15 : 0.85) + 0.14 * Math.sin(t * 0.0016 + (n.__phase ??= Math.random() * 6.28));
  // dot-rol ademt mee via dezelfde lus (geen aparte basis nodig)
  requestAnimationFrame(frameLoop);
})();

/* af en toe vuurt een link een deeltje af — de mind leeft */
setInterval(() => {
  const { links } = Graph.graphData();
  if (!links.length || state.traveling) return;
  const n = 1 + Math.floor(Math.random() * 2);
  for (let i = 0; i < n; i++)
    Graph.emitParticle(links[Math.floor(Math.random() * links.length)]);
}, 520);

/* rustige idle-autorotate; elke interactie pauzeert 'm even */
const controls = Graph.controls();
controls.autoRotate = true;
controls.autoRotateSpeed = 0.3;
let idleTimer;
const wake = () => {
  controls.autoRotate = false;
  clearTimeout(idleTimer);
  idleTimer = setTimeout(() => { controls.autoRotate = true; }, 15000);
};
el("graph").addEventListener("pointerdown", wake);
el("graph").addEventListener("wheel", wake, { passive: true });

/* ---- reizen tussen de niveaus ---- */
const veil = on => el("veil").classList.toggle("on", on);

function enterSystem(topicId, opts = {}) {
  const topic = nodeById.get(topicId);
  if (!topic) return;
  state.traveling = true;
  wake();
  const swap = () => {
    veil(true);
    setTimeout(() => {
      state.level = 2; state.topicId = topicId;
      closePanel();
      tuneForces(2);
      Graph.graphData(systemData(topicId));
      Graph.cameraPosition({ x: 0, y: 50, z: 235 }, { x: 0, y: 0, z: 0 }, 0);
      history.replaceState(null, "", `#t=${topicId}`);
      updateHud();
      veil(false);
      state.traveling = false;
      if (opts.drill === false) {
        // expliciet "toon in stelsel": de 3D is hier het doel, geen overlay erover
        if (opts.selectId) setTimeout(() => {
          const n = Graph.graphData().nodes.find(m => m.id === opts.selectId);
          if (n) select(n, true);
        }, 900);
      } else {
        // aankomst in een stelsel opent de cockpit — eerst even het stelsel zien landen
        setTimeout(() => openDrill(opts.selectId || topicId), 700);
      }
    }, 360);
  };
  /* vanaf de galaxy eerst richting de ster vliegen, zodat het als reizen voelt */
  const star = !opts.fromSystem && Graph.graphData().nodes.find(n => n.id === topicId);
  if (star && star.x !== undefined) {
    const d = 30, hyp = Math.hypot(star.x, star.y, star.z) || 1, k = 1 + d / hyp;
    Graph.cameraPosition({ x: star.x * k, y: star.y * k, z: star.z * k }, star, 750);
    setTimeout(swap, 700);
  } else swap();
}

function backToGalaxy() {
  if (state.level === 1 || state.traveling) return;
  state.traveling = true;
  wake();
  /* uitzoomen uit het stelsel, dan door de veil terug de galaxy in */
  const cam = Graph.camera().position;
  const k = 2.4 / (Math.hypot(cam.x, cam.y, cam.z) > 1 ? 1 : 1);
  Graph.cameraPosition({ x: cam.x * 2.4, y: cam.y * 2.4, z: cam.z * 2.4 || 500 }, { x: 0, y: 0, z: 0 }, 620);
  setTimeout(() => {
    veil(true);
    setTimeout(() => {
      state.level = 1; state.topicId = null;
      closePanel();
      tuneForces(state.overview === "organism" ? "organism" : 1);
      Graph.graphData(state.overview === "organism" ? organismData : galaxyData);
      Graph.cameraPosition({ x: 0, y: 0, z: state.overview === "organism" ? 1400 : 860 }, { x: 0, y: 0, z: 0 }, 0);
      setTimeout(() => Graph.zoomToFit(900, state.overview === "organism" ? 140 : 70), 500);
      history.replaceState(null, "", location.pathname);
      updateHud();
      veil(false);
      state.traveling = false;
    }, 360);
  }, 560);
}

el("btnBack").onclick = backToGalaxy;

/* ---- HUD: stats + breadcrumb ---- */
function updateHud() {
  el("btnMode").style.display = state.level === 1 ? "inline-flex" : "none";
  el("btnMode").textContent = state.overview === "organism" ? "⊚ modus: galaxy" : "⊚ modus: netwerk";
  if (state.level === 1) {
    el("crumbPath").innerHTML = state.overview === "organism" ? "NETWERK" : "GALAXY";
    el("btnBack").style.display = "none";
    el("stats").innerHTML = state.overview === "organism"
      ? `<div><b>${data.nodes.length}</b> nodes · <b>${data.links.length}</b> links — het hele organisme</div>
         <div>verbinding <span class="ok">● live</span> · klik een topic voor z'n stelsel · rechtsklik = drilldown</div>`
      : `<div><b>${topics.length}</b> topics als sterren · <b>${knowledgeCount}</b> kenniszaden aan boord</div>
       <div>verbinding <span class="ok">● live</span> · klik een ster om z'n stelsel binnen te vliegen</div>`;
  } else {
    const topic = nodeById.get(state.topicId);
    const g = Graph.graphData();
    const kids = g.nodes.filter(n => n.__role === "kid").length;
    const ports = g.nodes.filter(n => n.__role === "portal").length;
    el("crumbPath").innerHTML = `${state.overview === "organism" ? "NETWERK" : "GALAXY"} <span class="sep">▸</span> <span class="here">${esc(titleOf(topic))}</span>`;
    el("btnBack").style.display = "inline-flex";
    el("stats").innerHTML =
      `<div><b>${kids}</b> kenniszaden in dit stelsel · <b>${ports}</b> portalen naar buiten</div>
       <div>verbinding <span class="ok">● live</span> · klik een node voor detail · ⇢ portaal springt door</div>`;
  }
}

/* ---- selectie + detailpaneel ---- */
function flyTo(n) {
  const d = 60, hyp = Math.hypot(n.x, n.y, n.z) || 1, k = 1 + d / hyp;
  Graph.cameraPosition({ x: n.x * k, y: n.y * k, z: n.z * k }, n, 1200);
}

async function select(n, fly) {
  state.selected = n;
  if (fly && n.x !== undefined) { wake(); flyTo(n); }
  el("pTitle").textContent = titleOf(n);
  el("pChips").innerHTML =
    `<span class="pchip amber">${esc(n.type)}</span>` +
    (n.scope ? `<span class="pchip">${esc(n.scope)}</span>` : "") +
    (n.lifecycle ? `<span class="pchip">${esc(n.lifecycle)}</span>` : "") +
    `<span class="pchip">${degree.get(n.id) || 0} links</span>` +
    (n.use_count ? `<span class="pchip">${n.use_count}× gebruikt</span>` : "");
  el("pBody").textContent = "…";
  el("panel").classList.add("open");
  el("btnDrill").style.display = n.type === "topic" ? "none" : "block";
  if (n.type === "topic") {
    const kids = (topicChildren.get(n.id) || []).map(id => nodeById.get(id)).filter(Boolean);
    el("pBody").innerHTML = kids.map(k =>
      `<div style="margin:2px 0"><span style="color:${colorOf(k)}">◈</span> ${esc(titleOf(k))}</div>`).join("")
      || "leeg topic";
    return;
  }
  try {
    const full = await (await fetch(NODE_URL(n.id), AUTH)).json();
    let html = esc(full.content || "");
    if (full.tags?.length) html += `\n\n<span style="color:var(--dim)">tags: ${esc(full.tags.join(", "))}</span>`;
    el("pBody").innerHTML = html || "(geen inhoud)";
  } catch { el("pBody").textContent = "(inhoud niet op te halen)"; }
}

function closePanel() {
  el("panel").classList.remove("open");
  state.selected = null;
}
el("btnClose").onclick = closePanel;

/* ---- zoeken: typeahead over alle titels ---- */
const searchEl = el("search"), resultsEl = el("results");
const searchable = data.nodes.filter(n => !UID_RE.test(n.title));
searchEl.addEventListener("input", () => {
  const q = searchEl.value.trim().toLowerCase();
  if (q.length < 2) { resultsEl.style.display = "none"; return; }
  const hits = searchable.filter(n => n.title.toLowerCase().includes(q)).slice(0, 12);
  resultsEl.innerHTML = hits.map(n => {
    const t = n.type === "topic" ? null : nodeById.get(parentTopic.get(n.id));
    return `<div data-id="${n.id}"><span class="dot" style="background:${colorOf(n)}"></span>${esc(n.title)}` +
      (t ? `<span class="topicTag">${esc(titleOf(t))}</span>` : "") + `</div>`;
  }).join("") || `<div style="color:var(--dim)">geen hits</div>`;
  resultsEl.style.display = "block";
});
resultsEl.addEventListener("click", e => {
  const id = e.target.closest("[data-id]")?.dataset.id;
  if (!id) return;
  resultsEl.style.display = "none"; searchEl.value = ""; searchEl.blur();
  const n = nodeById.get(id);
  if (!n) return;
  if (n.type === "topic") { state.level === 2 ? enterSystem(n.id, { fromSystem: true }) : enterSystem(n.id); return; }
  const tid = parentTopic.get(n.id);
  if (!tid) { select(n, false); return; }
  if (state.level === 2 && state.topicId === tid) {
    openDrill(id);          // al in het juiste stelsel: direct de cockpit erop
  } else enterSystem(tid, { selectId: id, fromSystem: state.level === 2 });
});
document.addEventListener("keydown", e => {
  if (e.key === "/" && document.activeElement !== searchEl) { e.preventDefault(); searchEl.focus(); return; }
  if (e.key !== "Escape") return;
  if (drill.classList.contains("on")) { closeDrill(); return; }
  if (resultsEl.style.display === "block") { resultsEl.style.display = "none"; searchEl.blur(); return; }
  if (state.level === 2) backToGalaxy();
  else closePanel();
});

/* ---- modus-schakelaar: galaxy ⇄ netwerk (alleen op niveau 1) ---- */
el("btnMode").onclick = () => {
  if (state.level !== 1 || state.traveling) return;
  state.traveling = true;
  veil(true);
  setTimeout(() => {
    state.overview = state.overview === "organism" ? "galaxy" : "organism";
    closePanel();
    tuneForces(state.overview === "organism" ? "organism" : 1);
    Graph.graphData(state.overview === "organism" ? organismData : galaxyData);
    Graph.cameraPosition({ x: 0, y: 0, z: state.overview === "organism" ? 1400 : 900 }, { x: 0, y: 0, z: 0 }, 0);
    setTimeout(() => Graph.zoomToFit(1200, state.overview === "organism" ? 140 : 70), 1100);
    updateHud();
    veil(false);
    state.traveling = false;
  }, 340);
};

/* ---- cockpit-drilldown: overlay met de cockpit-variant, focus op deze node ---- */
const drill = el("drill"), drillFrame = el("drillFrame");
function openDrill(id) {
  const base = SERVER ? "/ui/cockpit" : "./cockpit.html";
  drillFrame.src = `${base}?embed=1&focus=${encodeURIComponent(id)}`;
  drill.classList.add("on");
}
function closeDrill() {
  drill.classList.remove("on");
  setTimeout(() => { if (!drill.classList.contains("on")) drillFrame.src = "about:blank"; }, 320);
}
window.addEventListener("message", e => {
  const msg = e.data || {};
  if (msg.type === "close") closeDrill();
  if (msg.type === "showInSystem" && msg.id) {
    closeDrill();
    const n = nodeById.get(msg.id);
    if (!n) return;
    if (n.type === "topic") enterSystem(n.id, { fromSystem: true, drill: false });
    else {
      const tid = parentTopic.get(n.id);
      if (tid) enterSystem(tid, { selectId: n.id, fromSystem: true, drill: false });
    }
  }
});
el("btnDrill").onclick = () => { if (state.selected && state.selected.type !== "topic") openDrill(state.selected.id); };
drill.addEventListener("click", e => { if (e.target === drill) closeDrill(); });

/* ---- server-modus: variant-switcher wordt navigatie naar de rest van Nectar ---- */
if (SERVER) {
  const v = el("variants");
  v.innerHTML =
    `<a class="chip" href="/ui#focus">◎ focus</a>
     <a class="chip" href="/ui#chores">🌼 pollen<span id="navBadge"></span></a>
     <a class="chip" href="/ui#governance">⚖ governance</a>
     <a class="chip" href="/ui#beheer">⚙ beheer</a>
     <a class="chip" href="/ui#legacy" onclick="location.href='/ui#legacy'">⌂ legacy</a>`;
  fetch("/graph/me", AUTH).then(r => r.json()).then(me => {
    if (me.ready_chores) {
      const b = document.getElementById("navBadge");
      if (b) { b.textContent = ` ${me.ready_chores}`; b.style.color = "var(--amber)"; b.style.fontWeight = "700"; }
    }
    if (me.can_review) {
      const r = document.createElement("a");
      r.className = "chip"; r.href = "/ui#review"; r.textContent = "☑ review";
      v.insertBefore(r, v.children[3]);
    }
  }).catch(() => {});
}

/* ---- boot: de galaxy, camera trekt in en komt tot rust ---- */
tuneForces(1);
Graph.graphData(galaxyData);
Graph.cameraPosition({ x: 0, y: 0, z: 1100 });
setTimeout(() => Graph.zoomToFit(1600, 70), 1200);
/* de layout kan na de eerste fit nog uitdijen — fit nogmaals zodra hij tot rust is */
setTimeout(() => { if (state.level === 1 && !state.traveling && !drill.classList.contains("on")) Graph.zoomToFit(900, 80); }, 4800);
updateHud();

/* deep-link: #t=<topic-id> opent direct dat stelsel */
const deepLink = location.hash.match(/^#t=([\w-]+)$/)?.[1];
if (deepLink && nodeById.get(deepLink)?.type === "topic")
  setTimeout(() => enterSystem(deepLink, { fromSystem: true }), 400);

el("splash").remove();
