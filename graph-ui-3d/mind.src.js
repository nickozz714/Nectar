/* NECTAR // MIND — MIX: galaxy-structuur + netwerk-modus + cockpit-drilldown.
   Overzicht in twee smaken (galaxy = alleen topics; netwerk = het hele organisme),
   klik een ster voor z'n stelsel, en drill een kennis-node met de cockpit-overlay
   (rechtsklik of de ⌕-knop in het paneel). */
import ForceGraph3D from "3d-force-graph";
import { Decks } from "./decks.src.js";
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
  .nodeLabel(n => {
    if (n.__role === "portal")
      return `<div class="tt-t">⇢ ${esc(titleOf(n))}</div><div class="tt-m">${esc(n.type)} · klik om naar dit stelsel te springen</div>`;
    if (n.type === "topic")
      return `<div class="tt-t">${esc(titleOf(n))}</div><div class="tt-m">topic · ${n.children || 0} kenniszaden · klik om binnen te vliegen</div>`;
    const t = nodeById.get(parentTopic.get(n.id));
    return `<div class="tt-t">${esc(titleOf(n))}</div>
      <div class="tt-m" style="color:${colorOf(n)}">◈ ${esc(n.type)}${n.lifecycle ? " · " + esc(n.lifecycle) : ""}</div>
      <div class="tt-m">${t ? esc(titleOf(t)) + " · " : ""}${n.use_count || 0}× gebruikt${(n.tags || []).length ? " · #" + n.tags.slice(0, 3).join(" #") : ""}</div>`;
  })
  .onNodeRightClick(n => {
    if (n && n.__role !== "portal" && n.type !== "topic") openDrill(n.id);
  })
  .nodeThreeObjectExtend(false)
  .nodeThreeObject(makeNode)
  .linkColor(l => {
    if (focusSet && state.selected) {
      const a = linkSrc(l), b = linkTgt(l), id = state.selected.id;
      if (a !== id && b !== id) return "#0d1826";
      return "#9fd8ea";
    }
    return LINK_COLORS[l.__kind] || "#2a7a90";
  })
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
        (n.__base ?? (n.__role === "sun" ? 1.15 : 0.85)) + 0.14 * Math.sin(t * 0.0016 + (n.__phase ??= Math.random() * 6.28));
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

/* ---- focus-dimmen: met een selectie wijkt al het andere terug ---- */
let focusSet = null;
function applyDim() {
  const g = Graph.graphData();
  if (!state.selected) {
    focusSet = null;
    for (const n of g.nodes) n.__base = undefined;
  } else {
    const id = state.selected.id;
    focusSet = new Set([id]);
    for (const l of g.links) {
      const a = linkSrc(l), b = linkTgt(l);
      if (a === id) focusSet.add(b);
      if (b === id) focusSet.add(a);
    }
    for (const n of g.nodes)
      n.__base = focusSet.has(n.id) ? (n.id === id ? 1.6 : (n.__role === "sun" ? 1.15 : 0.95)) : 0.12;
  }
  Graph.linkColor(Graph.linkColor());
}

/* ---- selectie + detailpaneel ---- */
function flyTo(n) {
  const d = 60, hyp = Math.hypot(n.x, n.y, n.z) || 1, k = 1 + d / hyp;
  Graph.cameraPosition({ x: n.x * k, y: n.y * k, z: n.z * k }, n, 1200);
}

let MEg = null;            // /graph/me — voor rol-gating in het paneel
let TOPICS = [];           // topictitels voor verplaats/samenvoeg-selects
async function loadTopicTitles() {
  if (!SERVER || TOPICS.length) return;
  try {
    const t = await (await fetch("/graph/topics", AUTH)).json();
    TOPICS = (t.topics || []).map(x => x.title).filter(x => !UID_RE.test(x)).sort((a, b) => a.localeCompare(b, "nl"));
  } catch {}
}
async function apiJ(p, opts = {}) {
  const r = await fetch(p, { ...opts, headers: { ...(AUTH?.headers || {}), "Content-Type": "application/json", ...(opts.headers || {}) } });
  if (!r.ok) { let d = ""; try { d = (await r.json()).detail || ""; } catch {} throw new Error(d || `HTTP ${r.status}`); }
  try { return await r.json(); } catch { return null; }
}
/* mini-markdown voor memory-inhoud: vet, koppen, code — meer niet */
function mdLite(t) {
  let h = esc(t || "");
  h = h.replace(/^#{1,3} (.+)$/gm, '<span class="mdh">$1</span>');
  h = h.replace(/\*\*([^*\n]+)\*\*/g, "<b>$1</b>");
  h = h.replace(/`([^`\n]+)`/g, "<code>$1</code>");
  return h;
}
const BLOOM_C = { captured: "#8d99ae", validated: "#5aa9e6", mature: "#6cc551", deprecated: "#e4572e" };

async function select(n, fly) {
  state.selected = n;
  applyDim();
  if (fly && n.x !== undefined) { wake(); flyTo(n); }
  el("pTitle").textContent = titleOf(n);
  el("pBody").textContent = "…";
  el("panel").classList.add("open");
  el("btnDrill").style.display = n.type === "topic" ? "none" : "block";
  for (const b of ["btnLineage", "btnSuggest", "btnArchive"])
    el(b).style.display = SERVER && n.type !== "topic" ? "block" : "none";
  el("btnDelete").style.display = SERVER && MEg?.can_review ? "block" : "none";

  if (!SERVER) {   // prototype-modus: alleen inhoud
    el("pChips").innerHTML = `<span class="pchip amber">${esc(n.type)}</span>`;
    if (n.type === "topic") {
      const kids = (topicChildren.get(n.id) || []).map(id => nodeById.get(id)).filter(Boolean);
      el("pBody").innerHTML = kids.map(k => `<div>◈ ${esc(titleOf(k))}</div>`).join("") || "leeg topic";
    } else {
      try { const f = await (await fetch(NODE_URL(n.id))).json(); el("pBody").innerHTML = esc(f.content || ""); }
      catch { el("pBody").textContent = "(inhoud niet op te halen)"; }
    }
    return;
  }

  await loadTopicTitles();
  let full;
  try { full = await apiJ(`/graph/node/${n.id}`); }
  catch { el("pBody").textContent = "(niet op te halen)"; return; }
  if (state.selected?.id !== n.id) return;
  renderNodePanel(n, full);
}

function renderNodePanel(n, f) {
  const isTopic = n.type === "topic";
  const maintain = !!MEg?.can_maintain;
  const bloom = f.lifecycle || "captured";
  el("pChips").innerHTML =
    `<span class="pchip amber" title="kennistype">${esc(n.type)}</span>` +
    (f.scope ? `<span class="pchip" title="zichtbaarheid: org / team / account">${esc(f.scope)}</span>` : "") +
    (!isTopic ? `<span class="pchip" title="bloom-status: captured → validated → mature; deprecated zakt weg" style="color:${BLOOM_C[bloom]};border-color:${BLOOM_C[bloom]}55">${esc(bloom)}</span>` : "") +
    (f.sensitivity === "gevoelig" ? `<span class="pchip" style="color:#ff6a45;border-color:#ff6a4555" title="door de classifier als gevoelig gemarkeerd">🔒 gevoelig</span>` : "") +
    `<span class="pchip" title="hoe vaak deze kennis is opgehaald">${f.use_count ?? 0}× gebruikt</span>` +
    ((f.pos || f.neg) ? `<span class="pchip" title="memory worth: hielp het echt? (feedback van agents)">👍${f.pos || 0} 👎${f.neg || 0}</span>` : "");

  const relChips = (arr, label, tip) => (arr || []).length
    ? `<div class="sec"><h4 title="${tip}">${label}</h4>${arr.map(x =>
        `<span class="pchip navchip" data-jump="${esc(x.uid)}" title="spring naar deze node">${esc(x.title)}</span>`).join(" ")}</div>` : "";

  const html = `
    <div class="md">${mdLite(f.content)}</div>
    ${isTopic && f.summary ? `<div class="sec"><h4>samenvatting</h4><div style="color:var(--dim)">${esc(f.summary)}</div></div>` : ""}
    ${f.superseded_by ? `<div class="sec"><span class="pchip navchip" style="color:#ff6a45;border-color:#ff6a4555" data-jump="${esc(f.superseded_by)}">⤳ vervangen — toon nieuwste</span></div>` : ""}
    ${relChips(f.parents, "valt onder", "de topics/nodes waar dit onder hangt")}
    ${relChips(f.children, "bevat", "wat hieronder hangt")}
    ${relChips(f.related, "gerelateerd", "vrije kruisverbanden (RELATES)")}
    ${(f.files || []).map(x => `<div class="sec"><h4>📄 ${esc(x.path)}</h4><div style="white-space:pre-wrap;color:var(--dim);max-height:140px;overflow-y:auto">${esc(x.content)}</div></div>`).join("")}
    ${!isTopic ? `<div class="sec"><h4 title="tags tellen mee in zoeken en ranking">tags</h4>
      <input type="text" id="pTags" style="width:100%" value="${esc((f.tags || []).join(", "))}" placeholder="komma-gescheiden">
      <div style="margin-top:6px"><span class="mini" id="pTagSave" title="vervangt de volledige tagset">tags opslaan</span><span class="ok" id="pTagOut" style="color:#55ffa1;font-size:10px"></span></div></div>` : ""}
    <div class="sec"><h4 title="artefacten (exports, scripts, screenshots) centraal in de hive">📎 bijlagen</h4>
      <div id="pAtts" style="color:var(--dim)">laden…</div>
      <input type="file" id="pAttFile" style="margin-top:6px;font-size:10px">
      <div style="margin-top:4px"><span class="mini" id="pAttUp">bijlage toevoegen</span></div></div>
    ${maintain && !isTopic ? `<div class="sec"><h4 title="alleen maintainers">beheer</h4>
      <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:6px">
        <select id="pLife" title="bloom-status handmatig zetten">${["captured", "validated", "mature", "deprecated"].map(x => `<option${x === bloom ? " selected" : ""}>${x}</option>`).join("")}</select>
        <span class="mini" id="pLifeSave">status</span>
        <select id="pImp" title="belang: schuift de recall-ranking">${[["0.2", "belang: laag"], ["0.5", "belang: normaal"], ["0.9", "belang: hoog"]].map(([v, l]) => `<option value="${v}"${((f.importance ?? 0.5) >= 0.75 ? "0.9" : (f.importance ?? 0.5) <= 0.35 ? "0.2" : "0.5") === v ? " selected" : ""}>${l}</option>`).join("")}</select>
        <span class="mini" id="pImpSave">belang</span>
        <input type="number" id="pDecay" min="1" style="width:86px" placeholder="decay (dgn)" value="${f.half_life_days || ""}" title="eigen half-life in dagen (leeg = standaard)">
        <span class="mini" id="pDecaySave">decay</span></div>
      <input type="text" id="pSup" style="width:100%" placeholder="vervangen door… zoek de nieuwere node" title="het oude feit blijft vindbaar maar zakt; het nieuwste wint">
      <div id="pSupPick" class="picker" style="border:1px solid var(--line);display:none;max-height:120px;overflow-y:auto"></div>
      <div style="margin-top:4px"><span class="mini" id="pSupSave">markeer als vervangen</span><span id="pSupSel" style="color:#55ffa1;font-size:10px;margin-left:6px"></span></div>
      <div style="display:flex;gap:6px;align-items:center;margin-top:8px;flex-wrap:wrap">
        <select id="pMove" title="verplaats naar een ander topic">${TOPICS.map(t => `<option>${esc(t)}</option>`).join("")}</select>
        <label style="font-size:10px;color:var(--dim)" title="multi-parent: huidige topics ook behouden"><input type="checkbox" id="pMoveKeep"> behoud huidige</label>
        <span class="mini" id="pMoveSave">verplaats</span></div></div>` : ""}
    ${maintain && isTopic ? `<div class="sec"><h4>samenvoegen in ander topic</h4>
      <div style="display:flex;gap:6px;align-items:center"><select id="pMerge">${TOPICS.filter(t => t !== f.title).map(t => `<option>${esc(t)}</option>`).join("")}</select>
      <span class="mini" id="pMergeSave" style="color:#ff6a45" title="alle inhoud verhuist; dit topic wordt daarna verwijderd">samenvoegen</span></div></div>` : ""}
    <div class="sec" style="color:var(--dim);font-size:10.5px">door ${esc(f.created_by_model || "onbekend model")}</div>`;
  el("pBody").innerHTML = html;
  const $ = id => el("pBody").querySelector("#" + id) || document.getElementById(id);
  const refresh = () => select(n, false);

  el("pBody").querySelectorAll("[data-jump]").forEach(c => c.onclick = () => {
    const m = nodeById.get(c.dataset.jump);
    if (!m) return;
    if (m.type === "topic") { enterSystem(m.id, { fromSystem: state.level === 2, drill: false }); return; }
    const tid = parentTopic.get(m.id);
    if (state.level === 2 && state.topicId === tid) { const live = Graph.graphData().nodes.find(x => x.id === m.id); select(live || m, !!live); }
    else if (tid) enterSystem(tid, { selectId: m.id, fromSystem: state.level === 2, drill: false });
    else select(m, false);
  });
  apiJ(`/graph/node/${n.id}/attachments`).then(list => {
    const box = $("pAtts"); if (!box) return;
    box.innerHTML = (list || []).map(a => `<div>📎 <a href="#" data-att="${esc(a.uid)}" data-fn="${esc(a.filename)}" style="color:var(--cyan)">${esc(a.filename)}</a>
      <span style="color:var(--dim)">(${(a.size / 1024).toFixed(1)} kB)</span></div>`).join("") || "geen bijlagen";
    box.querySelectorAll("[data-att]").forEach(a => a.onclick = async e => {
      e.preventDefault();
      const r = await fetch(`/attachments/${a.dataset.att}`, AUTH);
      if (!r.ok) { alert("download mislukt"); return; }
      const el2 = document.createElement("a");
      el2.href = URL.createObjectURL(await r.blob()); el2.download = a.dataset.fn; el2.click();
    });
  }).catch(() => { const b = $("pAtts"); if (b) b.textContent = ""; });
  const on = (id, fn) => { const x = $(id); if (x) x.onclick = () => fn().then(refresh).catch(e => alert(e.message)); };
  on("pTagSave", () => apiJ(`/graph/node/${n.id}/tags`, { method: "POST", body: JSON.stringify({ replace: $("pTags").value.split(",").map(x => x.trim()).filter(Boolean) }) }));
  on("pLifeSave", () => apiJ("/graph/lifecycle", { method: "POST", body: JSON.stringify({ uid: n.id, state: $("pLife").value }) }));
  on("pImpSave", () => apiJ("/graph/importance", { method: "POST", body: JSON.stringify({ uid: n.id, value: +$("pImp").value }) }));
  on("pDecaySave", () => apiJ("/graph/decay", { method: "POST", body: JSON.stringify({ uid: n.id, half_life_days: $("pDecay").value ? +$("pDecay").value : null }) }));
  on("pMoveSave", () => apiJ(`/graph/node/${n.id}/move`, { method: "POST", body: JSON.stringify({ to_topic: $("pMove").value, keep_others: $("pMoveKeep").checked }) }));
  const mrg = $("pMergeSave");
  if (mrg) mrg.onclick = async () => {
    const into = $("pMerge").value;
    if (!confirm(`"${f.title}" samenvoegen in "${into}"? Dit topic wordt daarna verwijderd.`)) return;
    try { await apiJ("/graph/topics/merge", { method: "POST", body: JSON.stringify({ from_topic: f.title, into_topic: into }) });
      alert("samengevoegd — herlaad de mind voor de nieuwe indeling"); closePanel(); } catch (e) { alert(e.message); }
  };
  const sup = $("pSup");
  if (sup) {
    let chosen = null, tmr;
    sup.oninput = () => { clearTimeout(tmr); tmr = setTimeout(async () => {
      const q = sup.value.trim(); const box = $("pSupPick");
      if (q.length < 2) { box.style.display = "none"; return; }
      const rs = (await apiJ(`/graph/search?q=${encodeURIComponent(q)}`)).slice(0, 8);
      box.innerHTML = rs.map((r, i) => `<div data-i="${i}">${esc(r.title)} <span style="color:var(--dim)">· ${esc(r.type)}</span></div>`).join("");
      box.style.display = "block";
      box.querySelectorAll("[data-i]").forEach(d => d.onclick = () => {
        chosen = rs[+d.dataset.i]; sup.value = chosen.title; box.style.display = "none";
        $("pSupSel").textContent = "✓ " + chosen.title; });
    }, 250); };
    $("pSupSave").onclick = async () => {
      if (!chosen) { alert("Zoek en kies eerst de nieuwere node"); return; }
      try { await apiJ("/graph/supersede", { method: "POST", body: JSON.stringify({ old_uid: n.id, new_uid: chosen.uid }) }); refresh(); }
      catch (e) { alert(e.message); }
    };
  }
  const up = $("pAttUp");
  if (up) up.onclick = async () => {
    const file = $("pAttFile").files[0];
    if (!file) { alert("Kies eerst een bestand"); return; }
    const r = await fetch(`/graph/node/${n.id}/attachments?filename=${encodeURIComponent(file.name)}`, {
      method: "POST", body: file, headers: { ...(AUTH?.headers || {}), "Content-Type": file.type || "application/octet-stream" } });
    if (!r.ok) { alert("upload mislukt"); return; }
    refresh();
  };
}

function closePanel() {
  el("panel").classList.remove("open");
  state.selected = null;
  applyDim();
}
el("btnClose").onclick = closePanel;

/* ---- zoeken: typeahead over alle titels ---- */
const searchEl = el("search"), resultsEl = el("results");
const searchable = data.nodes.filter(n => !UID_RE.test(n.title));
function renderResults(list) {
  resultsEl.innerHTML = list.map(n => {
    const t = n.type === "topic" ? null : nodeById.get(parentTopic.get(n.id));
    const tag = n.__sem
      ? `<span class="topicTag" title="semantische hit — matcht op inhoud, niet (alleen) op titel">≈ inhoud</span>`
      : (t ? `<span class="topicTag">${esc(titleOf(t))}</span>` : "");
    return `<div data-id="${n.id}"><span class="dot" style="background:${colorOf(n)}"></span>${esc(titleOf(n))}${tag}</div>`;
  }).join("") || `<div style="color:var(--dim)">geen hits</div>`;
  resultsEl.style.display = "block";
}
let searchSeq = 0, searchTimer;
searchEl.addEventListener("input", () => {
  const q = searchEl.value.trim().toLowerCase();
  if (q.length < 2) { resultsEl.style.display = "none"; return; }
  const local = searchable.filter(n => n.title.toLowerCase().includes(q)).slice(0, 12);
  renderResults(local);
  if (!SERVER) return;
  /* de semantische hive-zoek denkt even na (embeddings + reranker) — toon dat */
  resultsEl.insertAdjacentHTML("beforeend",
    `<div id="semBusy" style="color:var(--dim);letter-spacing:.1em">≈ de hive zoekt op inhoud…</div>`);
  clearTimeout(searchTimer);
  searchTimer = setTimeout(async () => {
    const mySeq = ++searchSeq;
    try {
      const sem = await apiJ(`/graph/search?q=${encodeURIComponent(searchEl.value.trim())}`);
      if (mySeq !== searchSeq || searchEl.value.trim().toLowerCase() !== q) return;
      const seen = new Set(local.map(n => n.id));
      const extra = (sem || []).map(r => {
        const live = nodeById.get(r.uid);
        return live && !seen.has(live.id) ? { ...live, __sem: true } : null;
      }).filter(Boolean);
      renderResults([...local, ...extra].slice(0, 14));
    } catch (err) {
      if (mySeq === searchSeq) {
        resultsEl.innerHTML = `<div style="color:#ff7847">zoekfout: ${esc(String(err))}</div>`;
        resultsEl.style.display = "block";
      }
    }
  }, 320);
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
  if (Decks.isOpen()) { Decks.close(); return; }
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

/* ---- node-acties uit de legacy Mind-tab: lineage, wijziging voorstellen, archiveren ---- */
el("btnLineage").onclick = async () => {
  const n = state.selected;
  if (!n || !SERVER) return;
  el("pBody").textContent = "…";
  try {
    const L = await (await fetch(`/graph/lineage/${n.id}`, AUTH)).json();
    const rows = [
      ["persoon", L.created_by_person], ["account", L.created_by_account],
      ["model", L.created_by_model], ["gevoeligheid", L.sensitivity],
      ["aangemaakt", L.created_at ? new Date(L.created_at).toLocaleString("nl-NL") : null],
    ].filter(([, v]) => v);
    const events = (L.events || L.audit || []).slice(0, 20).map(e =>
      `<div style="margin:3px 0;color:var(--dim)">▸ ${esc(e.action || e.event || "?")} — ${esc(e.account || "")} ${e.at ? "· " + new Date(e.at).toLocaleString("nl-NL") : ""}</div>`).join("");
    el("pBody").innerHTML =
      `<div style="color:var(--cyan);letter-spacing:.18em;font-size:10px;text-transform:uppercase;margin-bottom:8px">🧬 lineage</div>` +
      rows.map(([k, v]) => `<div><span style="color:var(--dim)">${k}:</span> ${esc(String(v))}</div>`).join("") +
      (events ? `<div style="margin-top:10px">${events}</div>` : "") +
      `<div style="margin-top:12px"><span class="pchip" style="cursor:pointer" id="backToContent">◂ terug naar inhoud</span></div>`;
    el("pBody").querySelector("#backToContent").onclick = () => select(n, false);
  } catch { el("pBody").textContent = "(lineage niet op te halen)"; }
};
el("btnSuggest").onclick = async () => {
  const n = state.selected;
  if (!n || !SERVER) return;
  const content = prompt("Voorgestelde nieuwe inhoud (consensus beslist):");
  if (!content) return;
  const rationale = prompt("Waarom? (korte motivatie)") || "via mind";
  try {
    await fetch("/graph/suggest", { method: "POST",
      headers: { ...AUTH.headers, "Content-Type": "application/json" },
      body: JSON.stringify({ kind: "edit", node_uid: n.id, payload: { content }, rationale, model_name: "mens-via-mind" }) });
    el("pBody").textContent = "✓ wijzigingsvoorstel ingediend — de swarm beslist (zie de Pollen-deck)";
  } catch (e) { alert("voorstel mislukt"); }
};
el("btnDelete").onclick = async () => {
  const n = state.selected;
  if (!n || !MEg?.can_review) return;
  if (!confirm(`Permanent verwijderen?\n\n"${titleOf(n)}"\n\nDit kan niet ongedaan worden gemaakt.`)) return;
  try { await apiJ(`/graph/node/${n.id}`, { method: "DELETE" }); closePanel(); alert("verwijderd — herlaad de mind voor de nieuwe stand"); }
  catch (e) { alert(e.message); }
};
el("btnArchive").onclick = async () => {
  const n = state.selected;
  if (!n || !SERVER) return;
  const reason = prompt(`"${titleOf(n)}" voorstellen te archiveren — reden:`);
  if (!reason) return;
  try {
    await fetch("/graph/suggest", { method: "POST",
      headers: { ...AUTH.headers, "Content-Type": "application/json" },
      body: JSON.stringify({ kind: "invalidate", node_uid: n.id, payload: { reason }, rationale: reason, model_name: "mens-via-mind" }) });
    el("pBody").textContent = "✓ archiveer-voorstel ingediend — de swarm beslist (zie de Pollen-deck)";
  } catch { alert("voorstel mislukt"); }
};
drill.addEventListener("click", e => { if (e.target === drill) closeDrill(); });

/* ---- server-modus: variant-switcher wordt navigatie naar de rest van Nectar ---- */
if (SERVER) {
  /* elke Nectar-functie heeft hier z'n eigen deck — nooit terug naar de legacy-pagina */
  const v = el("variants");
  v.innerHTML =
    `<span class="chip" data-deck="focus">◎ focus</span>
     <span class="chip" data-deck="chores">🌼 pollinate<span id="navBadge"></span></span>
     <span class="chip" data-deck="governance">⚖ governance</span>
     <span class="chip" data-deck="beheer">⚙ beheer</span>
     <a class="chip" href="/ui#legacy" title="de klassieke tabbladen-interface">⌂ legacy</a>`;
  v.querySelectorAll("[data-deck]").forEach(c => c.onclick = () => Decks.open(c.dataset.deck));
  fetch("/graph/me", AUTH).then(r => r.json()).then(me => {
    MEg = me;
    if (me.ready_chores) {
      const b = document.getElementById("navBadge");
      if (b) { b.textContent = ` ${me.ready_chores}`; b.style.color = "var(--amber)"; b.style.fontWeight = "700"; }
    }
    if (me.can_review) {
      const r = document.createElement("span");
      r.className = "chip"; r.textContent = "☑ review";
      r.onclick = () => Decks.open("review");
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
