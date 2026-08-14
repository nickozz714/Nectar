/* NECTAR // MIND — decks: Focus, Pollen, Review, Governance en Beheer als eigen
   HUD-panelen bínnen de 3D-interface. Alles praat rechtstreeks met de API met de
   GUI-login; niets verwijst terug naar de legacy-pagina. Alleen actief in server-modus. */

const TOKEN = () => localStorage.getItem("hive_token") || "";
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, opts = {}) {
  const r = await fetch(path, { ...opts, headers: {
    Authorization: "Bearer " + TOKEN(), "Content-Type": "application/json", ...(opts.headers || {}) } });
  if (!r.ok) {
    let d = ""; try { d = (await r.json()).detail || ""; } catch {}
    throw new Error(d || `HTTP ${r.status}`);
  }
  try { return await r.json(); } catch { return null; }
}

let ME = null;
let current = null;          // open deck-naam
let host, body, tabsEl, titleEl;

const DECKS = [
  ["focus", "◎ focus"], ["chores", "🌼 pollen"], ["review", "☑ review"],
  ["governance", "⚖ governance"], ["beheer", "⚙ beheer"],
];

const CSS = `
#deck { position: fixed; inset: 0; z-index: 18; background: rgba(2,4,9,.6);
        opacity: 0; pointer-events: none; transition: opacity .25s ease; display: flex;
        align-items: center; justify-content: center; }
#deck.on { opacity: 1; pointer-events: auto; }
#deck .dpanel { width: min(1080px, 94vw); height: 88vh; display: flex; flex-direction: column;
  background: rgba(4,8,15,.92); border: 1px solid var(--line); border-radius: 0;
  clip-path: polygon(22px 0, 100% 0, 100% calc(100% - 22px), calc(100% - 22px) 100%, 0 100%, 0 22px);
  backdrop-filter: blur(12px); box-shadow: 0 0 60px rgba(62,224,255,.12); overflow: hidden;
  position: relative;
  transform: perspective(1600px) rotateX(9deg) scale(.92) translateY(34px); opacity: 0;
  transition: transform .42s cubic-bezier(.2,.9,.25,1), opacity .3s ease; }
#deck.on .dpanel { transform: none; opacity: 1; }
#deck .dpanel::before { content: ""; position: absolute; top: 0; left: 22px; right: 0; height: 2px;
  background: linear-gradient(90deg, var(--amber), transparent 60%); opacity: .7; }
#deck.on .dpanel::after { content: ""; position: absolute; inset: 0; pointer-events: none;
  background: linear-gradient(180deg, transparent 0%, rgba(62,224,255,.07) 50%, transparent 100%);
  background-size: 100% 220%; animation: dsweep .9s ease-out 1; opacity: 0; }
@keyframes dsweep { from { opacity: 1; background-position: 0 -110%; } to { opacity: 0; background-position: 0 110%; } }
@media (prefers-reduced-motion: reduce) { #deck .dpanel { transition: none; transform: none; } }
#deck .dhead { display: flex; align-items: center; gap: 10px; padding: 14px 18px;
  border-bottom: 1px solid var(--line); flex-wrap: wrap; }
#deck .dtitle { font-size: 12px; letter-spacing: .28em; color: var(--amber); text-transform: uppercase; font-weight: 700; }
#deck .dtabs { display: flex; gap: 6px; flex-wrap: wrap; margin-left: 8px; }
#deck .dclose { margin-left: auto; }
#deck .dbody { flex: 1; overflow-y: auto; padding: 18px; font-size: 12.5px; line-height: 1.7; }
#deck .chip.on { color: var(--amber); border-color: rgba(255,181,71,.4); }
#deck h3 { font-size: 11px; letter-spacing: .22em; text-transform: uppercase; color: var(--cyan);
  margin: 22px 0 10px; } #deck h3:first-child { margin-top: 0; }
#deck .card { background: var(--panel); border: 1px solid var(--line); border-radius: 0;
  clip-path: polygon(10px 0, 100% 0, 100% calc(100% - 10px), calc(100% - 10px) 100%, 0 100%, 0 10px);
  padding: 13px 15px; margin-bottom: 12px; }
#deck .card .ct { font-weight: 600; font-size: 13px; line-height: 1.5; }
#deck .crow { display: flex; gap: 5px; flex-wrap: wrap; margin: 7px 0; }
#deck .cex { color: var(--dim); white-space: pre-wrap; max-height: 130px; overflow-y: auto;
  margin: 6px 0; border-left: 2px solid var(--line); padding-left: 10px; }
#deck .abtn { display: inline-flex; border: 1px solid var(--line); border-radius: 0;
  clip-path: polygon(6px 0, 100% 0, 100% calc(100% - 6px), calc(100% - 6px) 100%, 0 100%, 0 6px);
  padding: 5px 11px; font-size: 10px; letter-spacing: .14em; text-transform: uppercase;
  cursor: pointer; color: var(--cyan); user-select: none; }
#deck .abtn:hover { background: rgba(62,224,255,.08); }
#deck .abtn.amber { color: var(--amber); border-color: rgba(255,181,71,.4); }
#deck .abtn.red { color: #ff7847; border-color: rgba(255,120,71,.4); }
#deck .abtn.green { color: #55ffa1; border-color: rgba(85,255,161,.35); }
#deck .stat { display: inline-flex; flex-direction: column; gap: 2px; border: 1px solid var(--line);
  border-radius: 0; clip-path: polygon(8px 0, 100% 0, 100% calc(100% - 8px), calc(100% - 8px) 100%, 0 100%, 0 8px);
  padding: 10px 16px; margin: 0 8px 8px 0; min-width: 110px; }
#deck .stat b { font-size: 18px; } #deck .stat span { font-size: 9.5px; letter-spacing: .14em;
  text-transform: uppercase; color: var(--dim); }
#deck table { border-collapse: collapse; width: 100%; font-size: 11.5px; }
#deck th { text-align: left; color: var(--dim); font-size: 9.5px; letter-spacing: .14em;
  text-transform: uppercase; padding: 4px 10px 6px 0; border-bottom: 1px solid var(--line); }
#deck td { padding: 6px 10px 6px 0; border-bottom: 1px solid rgba(62,224,255,.08); }
#deck input[type=text], #deck input[type=number], #deck textarea, #deck select {
  background: var(--panel); color: var(--ink); border: 1px solid var(--line); border-radius: 0;
  font: 12px var(--mono); padding: 7px 10px; outline: none; }
#deck input:focus, #deck textarea:focus { border-color: var(--cyan); }
#deck .ok { color: #55ffa1; font-size: 11px; margin-left: 8px; }
#deck .empty { color: var(--dim); padding: 20px 0; }
`;

function pill(txt, cls = "") { return `<span class="pchip ${cls}">${esc(txt)}</span>`; }
function fmt(ms) { return ms ? new Date(ms).toLocaleString("nl-NL") : ""; }

/* ─── Focus ─────────────────────────────────────────────────────────── */
async function renderFocus() {
  const foci = await api("/focus");
  const list = Array.isArray(foci) ? foci : (foci ? [foci] : []);
  const stepTxt = s => typeof s === "string" ? s : (s.text ?? s.step ?? JSON.stringify(s));
  const stepDone = s => typeof s === "object" && !!s.done;
  body.innerHTML = (list.length ? list.map(f => `
    <div class="card">
      <div class="ct">🎯 ${esc(f.goal || "(zonder doel)")}</div>
      <div class="crow">${f.project ? pill("project: " + f.project) : ""}${f.done_when ? pill("klaar: " + f.done_when, "amber") : ""}</div>
      ${(f.steps || []).map(s => `
        <div style="display:flex;gap:9px;align-items:center;margin:3px 0;${stepDone(s) ? "opacity:.45" : ""}">
          <span>${stepDone(s) ? "✓" : "○"}</span><span style="flex:1">${esc(stepTxt(s))}</span>
          ${stepDone(s) ? "" : `<span class="abtn green" data-adv="${esc(stepTxt(s))}" data-proj="${esc(f.project || "")}">✓ afronden</span>`}
        </div>`).join("")}
      ${f.guardrails ? `<div class="cex">guardrails: ${esc(Array.isArray(f.guardrails) ? f.guardrails.join(" · ") : f.guardrails)}</div>` : ""}
      <div class="crow" style="margin-top:8px"><span class="abtn red" data-clear="${esc(f.project || "")}">✕ focus wissen</span></div>
    </div>`).join("") : `<div class="empty">Geen actieve focus — hieronder zet je er één.</div>`) + `
    <h3>nieuwe focus</h3>
    <div class="card">
      <div style="display:flex;flex-direction:column;gap:8px">
        <input type="text" id="fGoal" placeholder="doel…">
        <textarea id="fSteps" rows="4" placeholder="stappen — één per regel"></textarea>
        <input type="text" id="fGuard" placeholder="guardrails (optioneel)">
        <input type="text" id="fDone" placeholder="klaar wanneer… (optioneel)">
        <div><span class="abtn amber" id="fSet">focus zetten</span><span class="ok" id="fOut"></span></div>
      </div></div>`;
  body.querySelectorAll("[data-adv]").forEach(b => b.onclick = async () => {
    try { await api("/focus/advance", { method: "POST", body: JSON.stringify({ completed_step: b.dataset.adv, project: b.dataset.proj }) }); renderFocus(); }
    catch (e) { alert(e.message); } });
  body.querySelectorAll("[data-clear]").forEach(b => b.onclick = async () => {
    try { await api(`/focus?project=${encodeURIComponent(b.dataset.clear)}`, { method: "DELETE" }); renderFocus(); }
    catch (e) { alert(e.message); } });
  body.querySelector("#fSet").onclick = async () => {
    const goal = body.querySelector("#fGoal").value.trim();
    if (!goal) return;
    try {
      await api("/focus", { method: "POST", body: JSON.stringify({
        goal, steps: body.querySelector("#fSteps").value.split("\n").map(s => s.trim()).filter(Boolean),
        guardrails: body.querySelector("#fGuard").value.trim(), done_when: body.querySelector("#fDone").value.trim() }) });
      renderFocus();
    } catch (e) { alert(e.message); }
  };
}

/* ─── Pollen ────────────────────────────────────────────────────────── */
async function renderChores() {
  const data = await api("/graph/chores");
  const act = async (fn) => { try { await fn(); renderChores(); } catch (e) { alert(e.message); } };
  const nodeBlock = (n, label) => n && n.title
    ? `<div style="margin:6px 0"><div class="crow">${label ? pill(label, "amber") : ""}<b>${esc(n.title)}</b></div><div class="cex">${esc(n.content || "")}</div></div>` : "";
  const cards = (data.chores || []).map(c => {
    const v = c.view || {};
    const chips = [pill(c.type), pill(c.status, c.status === "ready" ? "amber" : ""),
      v.similarity != null ? pill("gelijkenis " + Number(v.similarity).toFixed(2)) : "",
      c.votes ? pill(c.votes + " stem(men)") : "",
      c.claimed_by_name ? pill(`🐝 ${c.claim_active ? "geclaimd" : "eerder geclaimd"} door ${c.claimed_by_name}`) : ""].join("");
    let buttons = "";
    if (v.route === "op_route") {
      buttons = ["ADD", "REPLACE", "DELETE", "NOOP"].map(d =>
        `<span class="abtn" data-think="${d}" data-uid="${c.uid}">${d.toLowerCase()}</span>`).join("") +
        `<span class="abtn amber" data-merge="${c.uid}">⇄ samenvoegen aanvragen</span>`;
    } else if (v.route === "contradiction") {
      buttons = `<span class="abtn green" data-contra="compatible" data-uid="${c.uid}">verenigbaar</span>
        <span class="abtn" data-contra="a" data-uid="${c.uid}">A is actueel</span>
        <span class="abtn" data-contra="b" data-uid="${c.uid}">B is actueel</span>`;
    } else if (v.route === "human") {
      buttons = `<span class="pchip">wacht op menselijke review — zie de Review-deck</span>`;
    } else if (c.type === "cognition") {
      buttons = `<span class="pchip">onderzoekswerk voor een agent (websearch)</span>
        <span class="abtn red" data-res="reject" data-uid="${c.uid}">✕ taak laten vervallen</span>`;
    } else {
      buttons = `<span class="abtn green" data-res="apply" data-uid="${c.uid}">✓ toepassen</span>
        <span class="abtn red" data-res="reject" data-uid="${c.uid}">✕ afwijzen</span>`;
    }
    return `<div class="card"><div class="ct">${esc(v.headline || c.type)}</div>
      <div class="crow">${chips}</div>
      ${v.explain ? `<div style="color:var(--dim)">${esc(v.explain)}</div>` : ""}
      ${nodeBlock(v.primary, v.primary?.label)}${nodeBlock(v.compare, v.compare?.label)}
      <div class="crow" style="margin-top:9px" data-refs='${esc(JSON.stringify(v.refs || {}))}'>${buttons}</div></div>`;
  }).join("") || `<div class="empty">Geen open Pollen — de hive is bij. 🐝</div>`;
  const done = (data.resolved || []).slice(0, 12).map(c => {
    const ok = c.status === "resolved";
    return `<div style="opacity:.65;margin:4px 0">${ok ? "✓" : "✗"} ${esc(c.view?.headline || c.type)}
      <span style="color:var(--dim)"> — ${ok ? "toegepast" : "afgewezen"}${c.resolved_by_name ? " door " + esc(c.resolved_by_name) : ""}${c.resolved ? " · " + fmt(c.resolved) : ""}</span></div>`;
  }).join("");
  body.innerHTML = `<div class="crow"><span class="stat"><b>${data.ready ?? 0}</b><span>ready</span></span>
    <span class="stat"><b>${(data.chores || []).length}</b><span>open</span></span></div>
    <h3>open / actief</h3>${cards}<h3>afgehandeld</h3>${done || `<div class="empty">nog niets</div>`}`;
  body.querySelectorAll("[data-res]").forEach(b => b.onclick = () => act(() =>
    api(`/graph/chores/${b.dataset.uid}/resolve?action=${b.dataset.res}${ME?.can_review ? "&direct=true" : ""}`,
        { method: "POST", body: JSON.stringify({ note: "via mind" }) })));
  body.querySelectorAll("[data-think]").forEach(b => b.onclick = () => act(() =>
    api("/graph/think/resolve", { method: "POST", body: JSON.stringify({ pollen_uid: b.dataset.uid, decision: b.dataset.think, note: "via mind" }) })));
  body.querySelectorAll("[data-merge]").forEach(b => b.onclick = () => act(() =>
    api("/graph/think/request-merge", { method: "POST", body: JSON.stringify({ pollen_uid: b.dataset.merge }) })));
  body.querySelectorAll("[data-contra]").forEach(b => b.onclick = () => {
    const refs = JSON.parse(b.closest("[data-refs]").dataset.refs || "{}");
    const verdict = b.dataset.contra;
    const payload = verdict === "compatible"
      ? { pollen_uid: b.dataset.uid, verdict: "compatible" }
      : { pollen_uid: b.dataset.uid, verdict: "contradiction",
          current: verdict === "a" ? refs.a : refs.b, outdated: verdict === "a" ? refs.b : refs.a };
    act(() => api("/graph/contradiction/resolve", { method: "POST", body: JSON.stringify(payload) }));
  });
}

/* ─── Review (org_admin) ────────────────────────────────────────────── */
async function renderReview() {
  const items = await api("/review/chores");
  body.innerHTML = (items || []).map(c => `<div class="card">
      <div class="ct">${esc(c.node_title || c.type)}</div>
      <div class="crow">${pill(c.type, "amber")}${c.node_scope ? pill(c.node_scope) : ""}</div>
      <div class="cex">${esc(typeof c.payload === "string" ? c.payload : JSON.stringify(c.payload || {}, null, 1))}</div>
      <div class="crow"><span class="abtn green" data-rv="approve" data-uid="${c.uid}">✓ goedkeuren</span>
        <span class="abtn red" data-rv="reject" data-uid="${c.uid}">✕ afwijzen</span></div></div>`).join("")
    || `<div class="empty">Geen scope-verbredingen die op een mens wachten.</div>`;
  body.querySelectorAll("[data-rv]").forEach(b => b.onclick = async () => {
    try { await api(`/review/chores/${b.dataset.uid}/${b.dataset.rv}`, { method: "POST", body: JSON.stringify({ note: "via mind" }) }); renderReview(); }
    catch (e) { alert(e.message); } });
}

/* ─── Governance ────────────────────────────────────────────────────── */
async function renderGovernance() {
  const g = await api("/graph/governance");
  const dist = (title, obj) => `<h3>${title}</h3><div class="crow">` +
    Object.entries(obj || {}).sort((a, b) => b[1] - a[1]).map(([k, v]) =>
      `<span class="stat"><b>${v}</b><span>${esc(k)}</span></span>`).join("") + `</div>`;
  body.innerHTML = `
    <div class="crow"><span class="stat"><b>${g.nodes_total}</b><span>nodes totaal</span></span></div>
    ${dist("per scope", g.by_scope)}${dist("per type", g.by_type)}
    ${dist("gevoeligheid", g.by_sensitivity)}${dist("pollen-pijplijn", g.chores)}
    <h3>herkomst (model · account · persoon)</h3>
    <table><tr><th>model</th><th>account</th><th>persoon</th><th>nodes</th></tr>
      ${(g.by_origin || []).map(o => `<tr><td>${esc(o.model)}</td><td>${esc(o.account)}</td><td>${esc(o.person)}</td><td>${o.count}</td></tr>`).join("")}</table>
    <h3>gevoelig gemarkeerd (${(g.sensitive_nodes || []).length})</h3>
    ${(g.sensitive_nodes || []).map(n => `<div style="margin:3px 0">🔒 ${esc(n.title)} ${pill(n.type)}</div>`).join("")
      || `<div class="empty">niets gemarkeerd</div>`}`;
}

/* ─── Beheer ────────────────────────────────────────────────────────── */
let BEHEER_SEC = "inzicht";
async function renderBeheer() {
  const admin = ME?.can_review;
  const secs = admin
    ? [["inzicht", "📊 inzicht"], ["onderhoud", "🧹 onderhoud"], ["instellingen", "🎛️ instellingen"], ["toegang", "🔑 toegang"], ["data", "💾 data"], ["pakket", "📦 pakket"]]
    : [["inzicht", "📊 inzicht"], ["pakket", "📦 pakket"]];
  if (!secs.find(s => s[0] === BEHEER_SEC)) BEHEER_SEC = "inzicht";
  const nav = `<div class="crow" style="margin-bottom:14px">${secs.map(([k, l]) =>
    `<span class="abtn ${k === BEHEER_SEC ? "amber" : ""}" data-sec="${k}">${l}</span>`).join("")}</div>`;
  body.innerHTML = nav + `<div id="secBody"><div class="empty">laden…</div></div>`;
  body.querySelectorAll("[data-sec]").forEach(b => b.onclick = () => { BEHEER_SEC = b.dataset.sec; renderBeheer(); });
  const sec = body.querySelector("#secBody");
  try { await BEHEER_RENDER[BEHEER_SEC](sec, admin); }
  catch (e) { sec.innerHTML = `<div class="empty">fout: ${esc(e.message)}</div>`; }
}

const BEHEER_RENDER = {
  async inzicht(sec) {
    const a = await api("/graph/analytics");
    const scalars = Object.entries(a).filter(([, v]) => typeof v === "number");
    const objs = Object.entries(a).filter(([, v]) => v && typeof v === "object" && !Array.isArray(v));
    const arrs = Object.entries(a).filter(([, v]) => Array.isArray(v));
    sec.innerHTML =
      `<div class="crow">${scalars.map(([k, v]) => `<span class="stat"><b>${v}</b><span>${esc(k)}</span></span>`).join("")}</div>` +
      objs.map(([k, v]) => `<h3>${esc(k)}</h3><div class="crow">${Object.entries(v).map(([kk, vv]) =>
        `<span class="stat"><b>${typeof vv === "number" ? vv : esc(String(vv))}</b><span>${esc(kk)}</span></span>`).join("")}</div>`).join("") +
      arrs.map(([k, v]) => v.length && typeof v[0] === "object"
        ? `<h3>${esc(k)}</h3><table><tr>${Object.keys(v[0]).map(h => `<th>${esc(h)}</th>`).join("")}</tr>
           ${v.slice(0, 10).map(r => `<tr>${Object.values(r).map(c => `<td>${esc(String(c))}</td>`).join("")}</tr>`).join("")}</table>` : "").join("");
  },
  async onderhoud(sec) {
    const scans = [["tidy-scan", "🗂️ opruimen", "losse kennis krijgt een topic-voorstel (Pollen)"],
      ["staleness-scan", "⏳ staleness", "oude veelgebruikte kennis → review-Pollen"],
      ["topic-summaries", "📝 topic-samenvattingen", "werk per topic de samenvatting bij"],
      ["contradiction-scan", "⚔️ tegenspraak", "sterk gelijkende paren → think-Pollen"],
      ["linkpred-scan", "🔗 link-predictie", "waarschijnlijke verbanden voorstellen"],
      ["pagerank-scan", "🏛️ pagerank", "structureel belang herberekenen"],
      ["train-ranker", "🧠 ranker trainen", "learning-to-rank op feedback"],
      ["reindex", "🧬 her-embedden", "alle embeddings opnieuw (kan even duren)"],
      ["reclassify-sensitivity", "🔍 herclassificeren", "gevoeligheids-labels verversen"]];
    sec.innerHTML = scans.map(([ep, name, d]) => `<div class="card"><div class="ct">${name}</div>
      <div style="color:var(--dim)">${d}</div>
      <div class="crow"><span class="abtn" data-scan="${ep}">draaien</span><span class="ok" id="out-${ep}"></span></div></div>`).join("");
    sec.querySelectorAll("[data-scan]").forEach(b => b.onclick = async () => {
      const out = sec.querySelector(`#out-${b.dataset.scan}`); out.textContent = " bezig…";
      try { const r = await api(`/graph/${b.dataset.scan}`, { method: "POST" });
        out.textContent = " ✓ " + Object.entries(r || {}).filter(([, v]) => typeof v !== "object").map(([k, v]) => `${k}: ${v}`).join(" · "); }
      catch (e) { out.textContent = " ✗ " + e.message; }
    });
  },
  async instellingen(sec) {
    const s = await api("/manage/swarm");
    sec.innerHTML = `
      <div class="card"><div class="ct">🖥️ standaardinterface</div>
        <div style="color:var(--dim)">waar leden na inloggen landen — beide blijven bereikbaar</div>
        <div class="crow"><span class="abtn ${ME.default_ui !== "mind" ? "amber" : ""}" data-ui="legacy">legacy</span>
          <span class="abtn ${ME.default_ui === "mind" ? "amber" : ""}" data-ui="mind">mind 3d</span><span class="ok" id="uiOut"></span></div></div>
      <div class="card"><div class="ct">🐝 consensus-drempel</div>
        <div style="color:var(--dim)">stemmen (per account) voordat een Pollen 'ready' wordt</div>
        <div class="crow"><input type="number" id="consN" min="1" style="width:80px" value="${s.consensus_threshold}">
          <span class="abtn" id="consSave">opslaan</span><span class="ok" id="consOut"></span></div></div>
      <div class="card"><div class="ct">🌍 cognition (wereld-research)</div>
        <div style="color:var(--dim)">nieuwe memories krijgen een research-Pollen; budget: max ${s.cognition_budget?.max_new}/job · ${s.cognition_budget?.max_depth} rondes · ${s.cognition_budget?.daily_cap}/dag</div>
        <div class="crow"><span class="abtn ${s.cognition_enabled ? "green" : ""}" data-cog="true">aan</span>
          <span class="abtn ${!s.cognition_enabled ? "red" : ""}" data-cog="false">uit</span><span class="ok" id="cogOut"></span></div></div>`;
    sec.querySelectorAll("[data-ui]").forEach(b => b.onclick = async () => {
      try { await api("/manage/ui-default", { method: "POST", body: JSON.stringify({ ui: b.dataset.ui }) });
        ME.default_ui = b.dataset.ui; BEHEER_RENDER.instellingen(sec); } catch (e) { alert(e.message); } });
    sec.querySelector("#consSave").onclick = async () => {
      try { await api("/manage/swarm/consensus", { method: "POST", body: JSON.stringify({ threshold: +sec.querySelector("#consN").value }) });
        sec.querySelector("#consOut").textContent = " ✓"; } catch (e) { alert(e.message); } };
    sec.querySelectorAll("[data-cog]").forEach(b => b.onclick = async () => {
      try { await api("/manage/swarm/cognition", { method: "POST", body: JSON.stringify({ enabled: b.dataset.cog === "true" }) });
        BEHEER_RENDER.instellingen(sec); } catch (e) { alert(e.message); } });
  },
  async toegang(sec) {
    const [accounts, invites] = await Promise.all([api("/manage/accounts"), api("/manage/invites")]);
    sec.innerHTML = `<h3>accounts</h3>
      <table><tr><th>account</th><th>persoon</th><th>rol</th><th>tokens</th></tr>
      ${(accounts || []).map(a => `<tr><td>${esc(a.name)}</td><td>${esc(a.person || "—")}</td>
        <td>${esc(a.role)}</td><td>${a.active ?? a.active_tokens ?? "—"}</td></tr>`).join("")}</table>
      <h3>invites</h3>
      <div class="crow"><select id="invRole"><option>member</option><option>maintainer</option><option>org_admin</option></select>
        <input type="number" id="invUses" value="1" min="1" style="width:70px" title="aantal keer bruikbaar">
        <span class="abtn amber" id="invMake">nieuwe invite</span><span class="ok" id="invOut" style="user-select:all"></span></div>
      ${(invites || []).map(i => `<div style="margin:4px 0;color:var(--dim)">🔑 ${esc(i.role)} · ${i.uses_left ?? i.uses ?? "?"}× over ${i.code_hash ? `<span class="abtn red" data-rvk="${esc(i.code_hash)}">intrekken</span>` : ""}</div>`).join("")}`;
    sec.querySelector("#invMake").onclick = async () => {
      try { const r = await api("/manage/invites", { method: "POST", body: JSON.stringify({
          role: sec.querySelector("#invRole").value, uses: +sec.querySelector("#invUses").value, expires_days: 14 }) });
        sec.querySelector("#invOut").textContent = " code: " + (r.code || JSON.stringify(r)); }
      catch (e) { alert(e.message); } };
    sec.querySelectorAll("[data-rvk]").forEach(b => b.onclick = async () => {
      try { await api(`/manage/invites/${b.dataset.rvk}/revoke`, { method: "POST" }); BEHEER_RENDER.toegang(sec); }
      catch (e) { alert(e.message); } });
  },
  async data(sec) {
    sec.innerHTML = `<div class="card"><div class="ct">💾 export</div>
      <div style="color:var(--dim)">volledige JSON-export van de zichtbare hive</div>
      <div class="crow"><span class="abtn amber" id="expBtn">download export</span><span class="ok" id="expOut"></span></div></div>
      <div class="card"><div class="ct">🛟 back-ups</div>
      <div style="color:var(--dim)">volume-snapshots draaien op de server (zie OPERATIONS.md); import kan via de API (/import)</div></div>`;
    sec.querySelector("#expBtn").onclick = async () => {
      const out = sec.querySelector("#expOut"); out.textContent = " bezig…";
      try {
        const r = await fetch("/export", { headers: { Authorization: "Bearer " + TOKEN() } });
        const blob = await r.blob();
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob); a.download = "nectar-export.json"; a.click();
        out.textContent = " ✓";
      } catch (e) { out.textContent = " ✗ " + e.message; }
    };
  },
  async pakket(sec) {
    let skills = [];
    try { skills = await api("/skills"); } catch {}
    sec.innerHTML = `<div class="card"><div class="ct">📦 install-pakket</div>
      <div style="color:var(--dim)">hivemind-install.zip — de client-kit voor een nieuwe machine</div>
      <div class="crow"><a class="abtn amber" href="/install.zip" download>download kit</a></div></div>
      <h3>gedeelde skills (${(skills || []).length})</h3>
      ${(skills || []).map(s => `<div style="margin:5px 0"><b>${esc(s.title || s.name)}</b>
        <div style="color:var(--dim)">${esc((s.description || s.content || "").slice(0, 160))}</div></div>`).join("")
        || `<div class="empty">geen skills gevonden</div>`}`;
  },
};

/* ─── raamwerk ──────────────────────────────────────────────────────── */
const RENDER = { focus: renderFocus, chores: renderChores, review: renderReview,
                 governance: renderGovernance, beheer: renderBeheer };
const TITLES = { focus: "focus", chores: "pollen", review: "review", governance: "governance", beheer: "beheer" };

function build() {
  const style = document.createElement("style"); style.textContent = CSS; document.head.appendChild(style);
  host = document.createElement("div"); host.id = "deck";
  host.innerHTML = `<div class="dpanel">
    <div class="dhead"><span class="dtitle">NECTAR // <span id="deckName"></span></span>
      <div class="dtabs"></div><span class="chip dclose" id="deckClose">✕ sluit (esc)</span></div>
    <div class="dbody"></div></div>`;
  document.body.appendChild(host);
  body = host.querySelector(".dbody");
  tabsEl = host.querySelector(".dtabs");
  titleEl = host.querySelector("#deckName");
  host.querySelector("#deckClose").onclick = close;
  host.addEventListener("click", e => { if (e.target === host) close(); });
}

async function open(name) {
  if (!host) build();
  if (!ME) { try { ME = await api("/graph/me"); } catch { location.replace("/ui"); return; } }
  if (name === "review" && !ME.can_review) name = "chores";
  current = name;
  titleEl.textContent = TITLES[name] || name;
  tabsEl.innerHTML = DECKS.filter(([k]) => k !== "review" || ME.can_review).map(([k, l]) =>
    `<span class="chip ${k === current ? "on" : ""}" data-deck="${k}">${l}${k === "chores" && ME.ready_chores ? ` <b style="color:var(--amber)">${ME.ready_chores}</b>` : ""}</span>`).join("");
  tabsEl.querySelectorAll("[data-deck]").forEach(c => c.onclick = () => open(c.dataset.deck));
  host.classList.add("on");
  body.innerHTML = `<div class="empty">laden…</div>`;
  try { await RENDER[name](); } catch (e) { body.innerHTML = `<div class="empty">fout: ${esc(e.message)}</div>`; }
}

function close() { host?.classList.remove("on"); current = null; }
function isOpen() { return !!host?.classList.contains("on"); }

export const Decks = { open, close, isOpen };
