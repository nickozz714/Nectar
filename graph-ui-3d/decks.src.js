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

/* [sleutel, label, alleen-voor-org_admin] */
const DECKS = [
  ["focus", "◎ focus"], ["chores", "🌼 pollinate"], ["review", "☑ review", true],
  ["governance", "⚖ governance"], ["historie", "🕘 historie", true], ["beheer", "⚙ beheer"],
];
const ADMIN_ONLY = new Set(DECKS.filter(d => d[2]).map(d => d[0]));
let onJump = null;         // (uid) => void — springt in de mind naar die node

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
#deck .bar-row { display: flex; align-items: center; gap: 10px; margin: 5px 0; }
#deck .bar-lbl { width: 108px; text-align: right; color: var(--dim); font-size: 10px; letter-spacing: .1em; text-transform: uppercase; flex: none; }
#deck .bar-track { flex: 1; height: 10px; background: rgba(62,224,255,.06); }
#deck .bar-fill { display: block; height: 100%; }
#deck .bar-val { width: 44px; font-weight: 600; flex: none; }
#deck .seg-track { display: flex; height: 12px; gap: 2px; margin: 8px 0 10px; }
#deck .seg { display: block; height: 100%; }
#deck .ddot { display: inline-block; width: 6px; height: 6px; transform: rotate(45deg); margin-right: 6px; }
#deck pre { background: rgba(62,224,255,.05); border: 1px solid var(--line); padding: 10px 12px;
  white-space: pre-wrap; word-break: break-all; font-size: 11px; }
#deck .fl { display: block; font-size: 9.5px; letter-spacing: .14em; text-transform: uppercase; color: var(--dim); margin: 8px 0 3px; }
#deck details { margin-top: 6px; } #deck summary { cursor: pointer; color: var(--dim); font-size: 10.5px; letter-spacing: .1em; text-transform: uppercase; }
#deck .grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 12px; }
`;

const TYPE_COLORS = { topic:"#f0a63a", memory:"#2fc4e8", decision:"#ff6a45", learning:"#43d98a",
  process:"#5fa4e6", workflow:"#8f76e8", skill:"#a06ae8", convention:"#e6c05c", glossary:"#6d87a0" };
const SCOPE_COLORS = { org:"#f0a63a", team:"#2fc4e8", account:"#a06ae8" };
const SENS_COLORS = k => k === "gevoelig" ? "#ff6a45" : k === "intern" ? "#e6c05c" : "#55ffa1";
const UIDISH = v => typeof v === "string" && (/^[0-9a-f]{8}-[0-9a-f]{4}/i.test(v) || /^[0-9a-f]{16,}$/i.test(v));

/* HUD-distributiebalken: elke balk gelabeld (identiteit nooit alleen via kleur), 2px lucht */
function distBars(obj, colorFn) {
  const entries = Object.entries(obj || {}).sort((a, b) => b[1] - a[1]);
  const max = Math.max(...entries.map(e => e[1]), 1);
  return entries.map(([k, v]) => `<div class="bar-row">
    <span class="bar-lbl">${esc(k)}</span>
    <span class="bar-track"><span class="bar-fill" style="width:${Math.max(2, v / max * 100)}%;background:${colorFn ? colorFn(k) : "var(--amber)"}"></span></span>
    <span class="bar-val">${v}</span></div>`).join("") || `<div class="empty">geen data</div>`;
}

function pill(txt, cls = "") { return `<span class="pchip ${cls}">${esc(txt)}</span>`; }

/* rollen: member < maintainer < org_admin. Eén helper voor account- én tokenrollen, zodat de
   keuzes overal gelijk zijn (extra optie "accountrol" = het token erft de rol van zijn account). */
const ROLE_LABELS = { member: "member — lezen & schrijven", maintainer: "maintainer — + onderhoud",
                      org_admin: "org_admin — + leden & reviewen" };
function roleSelect(id, current, { inherit = false } = {}) {
  const opts = (inherit ? [["", "— accountrol —"]] : []).concat(Object.entries(ROLE_LABELS));
  return `<select id="${id}" style="width:auto">${opts.map(([v, l]) =>
    `<option value="${v}"${(current || "") === v ? " selected" : ""}>${esc(l)}</option>`).join("")}</select>`;
}
function fmt(ms) { return ms ? new Date(ms).toLocaleString("nl-NL") : ""; }

/* ─── Focus ─────────────────────────────────────────────────────────── */
/* welke baan staat open in het formulier: null = nieuw, anders de baan zelf (bewerken) */
let focusEdit = null;
const stepTxt = s => typeof s === "string" ? s : (s.text ?? s.step ?? JSON.stringify(s));
const stepDone = s => typeof s === "object" && s.status === "done";
/* stappen als tekst, met de legacy-conventie: regels die met "x " beginnen zijn afgerond */
const stepsToText = steps => (steps || []).map(s => (stepDone(s) ? "x " : "") + stepTxt(s)).join("\n");
const textToSteps = t => t.split("\n").map(l => l.trim()).filter(Boolean).map(l =>
  l.toLowerCase().startsWith("x ") ? { text: l.slice(2).trim(), status: "done" } : { text: l, status: "open" });

async function renderFocus() {
  const foci = await api("/focus");
  const list = Array.isArray(foci) ? foci : (foci ? [foci] : []);
  const stepIcon = s => ({ done: "✓", current: "▶" }[typeof s === "object" ? s.status : ""] || "○");
  // Meerdere banen (lanes) per project: elke sessie steert zijn eigen focus. De baan-pill laat
  // zien welke dat is (label of sleutel; "" = project-breed) plus hoeveel sessies eraan hangen.
  const laneLbl = f => f.label || (f.lane ? f.lane : "project-breed");
  const perProject = new Map();
  list.forEach(f => {
    const key = f.project || "";
    if (!perProject.has(key)) perProject.set(key, []);
    perProject.get(key).push(f);
  });
  const cards = [...perProject.entries()].map(([proj, foci]) => `
    <h3>${esc(proj || "(geen project)")} · ${foci.length} ${foci.length === 1 ? "baan" : "banen"}</h3>
    ` + foci.map(f => `
    <div class="card">
      <div class="ct">🎯 ${esc(f.goal || "(zonder doel)")}</div>
      <div class="crow">${pill("baan: " + laneLbl(f), f.lane ? "amber" : "")}${(f.sessions || []).length ? pill((f.sessions || []).length + "× sessie") : ""}${f.done_when ? pill("klaar: " + f.done_when, "amber") : ""}${f.last_seen ? pill("gezien: " + fmt(f.last_seen)) : ""}</div>
      ${(f.steps || []).map(s => `
        <div style="display:flex;gap:9px;align-items:center;margin:3px 0;${stepDone(s) ? "opacity:.45" : ""}">
          <span>${stepIcon(s)}</span><span style="flex:1">${esc(stepTxt(s))}</span>
          ${stepDone(s) ? "" : `<span class="abtn green" data-adv="${esc(stepTxt(s))}" data-proj="${esc(f.project || "")}" data-lane="${esc(f.lane || "")}">✓ afronden</span>`}
        </div>`).join("")}
      ${f.guardrails ? `<div class="cex">guardrails: ${esc(Array.isArray(f.guardrails) ? f.guardrails.join(" · ") : f.guardrails)}</div>` : ""}
      ${(f.notes || []).length ? `<div class="cex">voortgang: ${esc(f.notes[f.notes.length - 1])}</div>` : ""}
      <div class="crow" style="margin-top:8px">
        <span class="abtn" data-edit="${esc(JSON.stringify({ project: f.project || "", lane: f.lane || "" }))}">✎ bewerken</span>
        <span class="abtn" data-note="${esc(f.project || "")}" data-lane="${esc(f.lane || "")}">✎ voortgangsnotitie</span>
        <span class="abtn red" data-clear="${esc(f.project || "")}" data-lane="${esc(f.lane || "")}">✕ baan wissen</span></div>
    </div>`).join("")).join("");
  /* één formulier, twee standen: nieuwe focus of een bestaande baan bewerken */
  const f = focusEdit;
  body.innerHTML = (list.length ? cards : `<div class="empty">Geen actieve focus — hieronder zet je er één.</div>`) + `
    <h3>${f ? "focus bewerken" : "nieuwe focus"}</h3>
    <div class="card">
      <div style="display:flex;flex-direction:column;gap:8px">
        <label class="fl">doel — wat bereiken we, in één zin</label>
        <input type="text" id="fGoal" placeholder="doel…" value="${esc(f?.goal || "")}">
        <label class="fl">stappen — één per regel; begin met 'x ' voor afgerond</label>
        <textarea id="fSteps" rows="5">${esc(stepsToText(f?.steps))}</textarea>
        <label class="fl">guardrails — één per regel; harde wel/niet-regels</label>
        <textarea id="fGuard" rows="3">${esc((f?.guardrails || []).join("\n"))}</textarea>
        <label class="fl">klaar wanneer…</label>
        <input type="text" id="fDone" placeholder="definition of done" value="${esc(f?.done_when || "")}">
        <div style="display:flex;gap:8px">
          <input type="text" id="fProj" placeholder="project (optioneel)" style="flex:1" value="${esc(f?.project || "")}" ${f ? "readonly" : ""}>
          <input type="text" id="fName" placeholder="baan-naam (optioneel)" style="flex:1" value="${esc(f ? (f.label || f.lane || "") : "")}" ${f ? "readonly" : ""}>
        </div>
        <div><span class="abtn amber" id="fSet">${f ? "opslaan" : "focus zetten"}</span>
          ${f ? `<span class="abtn" id="fCancel">annuleren</span>` : ""}<span class="ok" id="fOut"></span></div>
      </div></div>`;
  body.querySelectorAll("[data-adv]").forEach(b => b.onclick = async () => {
    try { await api("/focus/advance", { method: "POST", body: JSON.stringify({ completed_step: b.dataset.adv, project: b.dataset.proj, lane: b.dataset.lane }) }); renderFocus(); }
    catch (e) { alert(e.message); } });
  body.querySelectorAll("[data-note]").forEach(b => b.onclick = async () => {
    const note = prompt("Voortgangsnotitie:");
    if (!note) return;
    try { await api("/focus/advance", { method: "POST", body: JSON.stringify({ note, project: b.dataset.note, lane: b.dataset.lane }) }); renderFocus(); }
    catch (e) { alert(e.message); } });
  body.querySelectorAll("[data-edit]").forEach(b => b.onclick = () => {
    const key = JSON.parse(b.dataset.edit);
    focusEdit = list.find(x => (x.project || "") === key.project && (x.lane || "") === key.lane) || null;
    renderFocus();
  });
  body.querySelectorAll("[data-clear]").forEach(b => b.onclick = async () => {
    if (!confirm("Deze baan wissen?")) return;
    try { await api(`/focus?project=${encodeURIComponent(b.dataset.clear)}&lane=${encodeURIComponent(b.dataset.lane)}`, { method: "DELETE" });
      focusEdit = null; renderFocus(); }
    catch (e) { alert(e.message); } });
  if (f) body.querySelector("#fCancel").onclick = () => { focusEdit = null; renderFocus(); };
  body.querySelector("#fSet").onclick = async () => {
    const goal = body.querySelector("#fGoal").value.trim();
    if (!goal) { alert("Doel is verplicht"); return; }
    const payload = {
      goal, steps: textToSteps(body.querySelector("#fSteps").value),
      guardrails: body.querySelector("#fGuard").value.split("\n").map(s => s.trim()).filter(Boolean),
      done_when: body.querySelector("#fDone").value.trim(),
      project: body.querySelector("#fProj").value.trim(),
    };
    /* bewerken: stuur de exacte baan-sleutel mee, anders zou dit een nieuwe baan openen */
    if (f) payload.lane = f.lane || ""; else payload.name = body.querySelector("#fName").value.trim();
    try { await api("/focus", { method: "POST", body: JSON.stringify(payload) }); focusEdit = null; renderFocus(); }
    catch (e) { alert(e.message); }
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
    /* niet-ready pollen wachten op consensus; alleen een org_admin mag die bypassen (geaudit) */
    const wait = `<span class="pchip">wacht op meer stemmen (consensus)</span>`;
    const ready = c.status === "ready";
    let buttons = "";
    if (v.route === "op_route") {
      buttons = !ready ? wait : ["ADD", "REPLACE", "DELETE", "NOOP"].map(d =>
        `<span class="abtn" data-think="${d}" data-uid="${c.uid}">${d.toLowerCase()}</span>`).join("") +
        (v.merge_requested
          ? `<span class="pchip amber">samenvoegen aangevraagd · wacht op de zwerm</span>`
          : `<span class="abtn amber" data-merge="${c.uid}">⇄ samenvoegen aanvragen</span>`);
    } else if (v.route === "contradiction") {
      buttons = !ready ? wait : `<span class="abtn green" data-contra="compatible" data-uid="${c.uid}">verenigbaar</span>
        <span class="abtn" data-contra="a" data-uid="${c.uid}">A is actueel</span>
        <span class="abtn" data-contra="b" data-uid="${c.uid}">B is actueel</span>`;
    } else if (v.route === "human") {
      buttons = `<span class="pchip">wacht op menselijke review — zie de Review-deck</span>`;
    } else if (c.type === "cognition") {
      buttons = `<span class="pchip">onderzoekswerk voor een agent (websearch)</span>
        <span class="abtn red" data-res="reject" data-uid="${c.uid}">✕ taak laten vervallen</span>`;
    } else if (ready) {
      buttons = `<span class="abtn green" data-res="apply" data-uid="${c.uid}">✓ toepassen</span>
        <span class="abtn red" data-res="reject" data-uid="${c.uid}">✕ afwijzen</span>`;
    } else if (ME?.can_review) {
      buttons = `<span class="abtn green" data-res="apply" data-direct="1" data-uid="${c.uid}">✓ direct toepassen</span>
        <span class="abtn red" data-res="reject" data-direct="1" data-uid="${c.uid}">✕ afwijzen</span>
        <span class="pchip">org_admin — bypasst consensus (geaudit)</span>`;
    } else {
      buttons = wait;
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
      <span style="color:var(--dim)"> — ${ok ? "toegepast" : "afgewezen"}${c.resolved_by_name ? " door " + esc(c.resolved_by_name) : ""}${c.resolved ? " · " + fmt(c.resolved) : ""}</span>
      ${c.resolution ? `<div class="cex">${esc(c.resolution)}</div>` : ""}</div>`;
  }).join("");
  body.innerHTML = `<div class="crow"><span class="stat"><b>${data.ready ?? 0}</b><span>ready</span></span>
    <span class="stat"><b>${(data.chores || []).length}</b><span>open</span></span></div>
    <h3>open / actief</h3>${cards}<h3>afgehandeld</h3>${done || `<div class="empty">nog niets</div>`}`;
  body.querySelectorAll("[data-res]").forEach(b => b.onclick = () => act(() =>
    api(`/graph/chores/${b.dataset.uid}/resolve?action=${b.dataset.res}${b.dataset.direct ? "&direct=true" : ""}`,
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
  const ch = g.chores || {};
  const sens = (g.sensitive_nodes || []).length;
  const tile = (v, lbl, color, sub) => `<span class="stat" style="border-color:${color}55"><b style="color:${color}">${v}</b><span>${lbl}</span>${sub ? `<span>${sub}</span>` : ""}</span>`;
  let audit = "";
  if (ME?.can_review) {
    try {
      const rows = await api("/graph/audit?limit=50");
      const detTxt = d => { let o = {}; try { o = JSON.parse(d || "{}"); } catch { return ""; }
        return Object.entries(o).filter(([, v]) => v != null && v !== "" && typeof v !== "object" && !UIDISH(String(v)))
          .map(([k, v]) => `${esc(k.replace(/_/g, " "))}: ${esc(String(v))}`).join(" · "); };
      audit = `<h3>📜 audit-trail (laatste ${rows.length})</h3>` + rows.map(e => `
        <div style="margin:7px 0;border-left:2px solid var(--line);padding-left:10px">
          <div style="color:var(--dim);font-size:10px">${fmt(e.at)}</div>
          <div><b>${esc(histLabel(e.action))}</b> · ${esc(e.account || "systeem")}${e.target_title ? ` — ${esc(e.target_title)}` : ""}</div>
          ${detTxt(e.detail) ? `<div style="color:var(--dim)">${detTxt(e.detail)}</div>` : ""}
        </div>`).join("");
    } catch {}
  }
  body.innerHTML = `
    <div class="crow">
      ${tile(g.nodes_total || 0, "memories totaal", "#f0a63a")}
      ${tile(sens, "gevoelig", "#ff6a45")}
      ${tile((ch.open || 0) + (ch.ready || 0), "open pollinate", "#2fc4e8", `${ch.ready || 0} ready`)}
      ${tile(ch.awaiting_human || 0, "wacht op mens", "#a06ae8")}
    </div>
    <div class="grid2">
      <div class="card"><div class="ct">🔭 zichtbaarheid</div>${distBars(g.by_scope, k => SCOPE_COLORS[k] || "#8fa3b8")}</div>
      <div class="card"><div class="ct">🔐 gevoeligheid</div>${distBars(g.by_sensitivity, SENS_COLORS)}</div>
      <div class="card"><div class="ct">🧩 kennistype</div>${distBars(g.by_type, k => TYPE_COLORS[k] || "#8fa3b8")}</div>
      <div class="card"><div class="ct">🌼 pollinate-pijplijn</div>${distBars(
        Object.fromEntries([["open", ch.open || 0], ["ready", ch.ready || 0], ["wacht op mens", ch.awaiting_human || 0], ["toegepast", ch.resolved || 0], ["afgewezen", ch.rejected || 0]]),
        k => ({ open: "#5fa4e6", ready: "#f0a63a", "wacht op mens": "#a06ae8", toegepast: "#55ffa1", afgewezen: "#6d87a0" }[k]))}</div>
    </div>
    <h3>🧬 herkomst — model · account · persoon</h3>
    ${(g.by_origin || []).map(o => `<div style="display:flex;gap:10px;align-items:center;margin:4px 0">
      <span class="ddot" style="background:#2fc4e8"></span>
      <span style="flex:1">${esc(o.person)} <span style="color:var(--dim)">· via ${esc(o.account)} · 🤖 ${esc(o.model)}</span></span>
      <b>${o.count}</b></div>`).join("") || `<div class="empty">geen herkomst-gegevens</div>`}
    <h3>⚠️ als gevoelig geclassificeerd (${sens})</h3>
    ${(g.sensitive_nodes || []).map(n => `<div style="margin:3px 0"><span class="ddot" style="background:#ff6a45"></span>${esc(n.title)} ${pill(n.type)}</div>`).join("")
      || `<div class="empty">niets gemarkeerd — schoon</div>`}
    ${audit}`;
}

/* ─── Historie (audit-trail, org_admin) ─────────────────────────────── */
/* Nederlandse namen voor de audit-acties — anders leest de historie als logregels. */
const HIST_LABELS = { remember: "onthouden", create_topic: "topic aangemaakt", move_node: "verplaatst",
  merge_topics: "topics samengevoegd", delete: "verwijderd", suggest: "wijziging voorgesteld",
  resolve_chore: "pollen afgehandeld", admin_resolve_chore: "pollen afgehandeld (admin)",
  attach: "bijlage toegevoegd", attach_delete: "bijlage verwijderd", set_system: "systeemvlag gezet",
  set_role: "rol gewijzigd", invite_create: "uitnodiging aangemaakt", login: "ingelogd",
  login_entra: "ingelogd (Microsoft)", login_entra_provision: "account aangemaakt (Microsoft)",
  password_set: "wachtwoord ingesteld", password_set_for: "wachtwoord ingesteld voor",
  secret_set: "secret opgeslagen", secret_get: "secret gelezen", secret_read: "secret gelezen",
  skill_create: "skill aangemaakt", skill_update: "skill bijgewerkt",
  workflow_create: "workflow aangemaakt", workflow_update: "workflow bijgewerkt",
  approve_scope_widening: "scope-verbreding goedgekeurd", supersede: "vervangen (superseded)",
  resolve_contradiction: "tegenspraak afgehandeld", resolve_think: "denk-pollen afgehandeld",
  lifecycle: "levensfase gewijzigd", set_importance: "belang aangepast", set_decay: "verval aangepast",
  reclassify_sensitivity: "gevoeligheid herbeoordeeld", pagerank_scan: "pagerank herberekend",
  contradiction_scan: "tegenspraak-scan", linkpred_scan: "link-predictie", tidy_scan: "opruim-scan",
  staleness_scan: "staleness-scan", relate: "gekoppeld", unlink: "koppeling verwijderd",
  reembed: "opnieuw ge-embed", train_ranker: "ranker getraind", feedback: "feedback gegeven",
  invite_revoke: "uitnodiging ingetrokken", token_rotate: "token geroteerd", token_revoke: "token ingetrokken",
  create_account: "account aangemaakt", create_token: "token aangemaakt",
  set_consensus: "consensus-drempel gewijzigd", set_default_ui: "standaardinterface gewijzigd" };
const histLabel = a => HIST_LABELS[a] || (a || "").replace(/_/g, " ");
function timeAgo(ms) {
  if (!ms) return "";
  const s = Math.floor((Date.now() - ms) / 1000);
  if (s < 60) return "zojuist";
  const m = Math.floor(s / 60); if (m < 60) return m + " min geleden";
  const h = Math.floor(m / 60); if (h < 24) return h + " uur geleden";
  const d = Math.floor(h / 24); if (d < 7) return d + (d > 1 ? " dagen" : " dag") + " geleden";
  return new Date(ms).toLocaleDateString("nl-NL");
}

async function renderHistorie() {
  const ev = await api("/graph/audit?limit=200");
  body.innerHTML = `<div style="color:var(--dim);margin-bottom:10px">alles wat er in de hive gebeurde — mens én zwerm. klik een naam om de node in de mind op te zoeken.</div>` +
    (ev.length ? ev.map(e => {
      let detail = {}; try { detail = JSON.parse(e.detail || "{}"); } catch {}
      const name = e.target_title || detail.title || (UIDISH(e.target || "") ? "(verwijderd)" : (e.target || ""));
      const shown = name.length > 64 ? name.slice(0, 63) + "…" : name;
      /* alleen nog bestaande nodes zijn klikbaar — de rest is historie zonder bestemming */
      const tgt = e.target_title
        ? `<span class="abtn" data-jump="${esc(e.target)}">${esc(shown)}</span>`
        : (shown ? `<span style="color:var(--dim)">${esc(shown)}</span>` : "");
      return `<div style="margin:7px 0;border-left:2px solid var(--line);padding-left:10px">
        <div style="color:var(--dim);font-size:10px">${timeAgo(e.at)} · ${esc(e.account || "systeem")}</div>
        <div><b>${esc(histLabel(e.action))}</b> ${tgt}</div></div>`;
    }).join("") : `<div class="empty">nog geen gebeurtenissen</div>`);
  body.querySelectorAll("[data-jump]").forEach(b => b.onclick = () => {
    if (!onJump) return;
    close();
    onJump(b.dataset.jump);
  });
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
    const trained = a.ranker && a.ranker.trained;
    const life = [["mature", a.mature || 0, "#55ffa1"], ["validated", a.validated || 0, "#2fc4e8"],
                  ["captured", a.captured || 0, "#5fa4e6"], ["deprecated", a.deprecated || 0, "#6d87a0"]];
    const lifeTotal = life.reduce((t, x) => t + x[1], 0) || 1;
    sec.innerHTML = `
      <div class="crow">
        <span class="stat" style="border-color:#f0a63a55"><b style="color:#f0a63a">${a.total || 0}</b><span>memories totaal</span></span>
        <span class="stat"><b>${a.never_used || 0}</b><span>nooit opgehaald</span><span>archiveer-kandidaten</span></span>
        <span class="stat" style="border-color:${trained ? "#55ffa155" : "#e6c05c55"}"><b style="color:${trained ? "#55ffa1" : "#e6c05c"}">${trained ? "getraind" : "handmatig"}</b><span>ranker</span><span>${a.ranker ? a.ranker.examples : 0} feedback-voorbeelden</span></span>
      </div>
      <h3>🌸 bloom-levenscyclus</h3>
      <div style="color:var(--dim)">kennis rijpt: captured → validated → mature; deprecated zakt weg</div>
      <div class="seg-track">${life.map(([k, v, c]) => v ? `<span class="seg" title="${k}: ${v}" style="width:${v / lifeTotal * 100}%;background:${c}"></span>` : "").join("")}</div>
      <div class="crow">${life.map(([k, v, c]) => `<span><span class="ddot" style="background:${c}"></span>${k} <b>${v}</b></span>`).join("&nbsp;&nbsp;")}</div>
      <h3>🔥 meest gebruikt</h3>
      ${(a.most_used || []).map((m, i) => `<div style="display:flex;gap:10px;align-items:center;margin:4px 0">
        <span class="pchip" style="min-width:24px;text-align:center">${i + 1}</span>
        <span style="flex:1">${esc(m.title)}</span><b>${m.use_count}×</b></div>`).join("") || `<div class="empty">nog niets opgehaald</div>`}
      ${(a.gaps || []).length ? `<h3>🕳️ kennis-gaten — zoekopdrachten die niks opleverden</h3>` +
        a.gaps.map(g => `<div style="display:flex;gap:10px;margin:3px 0"><span style="flex:1">${esc(g.query)}</span><b>${g.count}× leeg</b></div>`).join("") : ""}`;
  },
  async onderhoud(sec) {
    const scans = [["tidy-scan", "🗂️ opruimen", "losse kennis zonder topic krijgt het dichtstbijzijnde topic voorgesteld (Pollinate)"],
      ["staleness-scan", "⏳ staleness", "oude maar veelgebruikte kennis krijgt een 'klopt dit nog?'-review"],
      ["topic-summaries", "📝 topic-samenvattingen", "werk per topic de samenvatting bij zodat elk topic toont wat het bevat"],
      ["pagerank-scan", "🕸️ pagerank", "herbereken structureel belang: goed-verbonden kennis komt hoger in recall"],
      ["linkpred-scan", "🔗 link-predictie", "stel RELATES-koppelingen voor tussen waarschijnlijk-gerelateerde memories"],
      ["contradiction-scan", "⚖️ tegenspraak", "vind sterk-gelijkende memories die elkaar tegenspreken; de swarm oordeelt"],
      ["reclassify-sensitivity", "🔐 herclassificeer gevoeligheid", "beoordeel alle memories opnieuw met de huidige classifier"],
      ["train-ranker", "🎚️ ranker trainen", "leer van de 'heeft het geholpen?'-feedback en vervang de handmatige weegfactoren"],
      ["reindex", "🧬 her-embedden", "herbereken alle embeddings — draai dit na het wisselen van embeddingmodel"]];
    sec.innerHTML = `<div style="color:var(--dim);margin-bottom:10px">deterministische scans die de hive gezond houden — de meeste openen <b>Pollinate</b> (voorstellen) i.p.v. direct te wijzigen; niets wordt ooit hard verwijderd</div>` +
      `<div class="grid2">` + scans.map(([ep, name, d]) => `<div class="card"><div class="ct">${name}</div>
      <div style="color:var(--dim)">${d}</div>
      <div class="crow"><span class="abtn" data-scan="${ep}">draaien</span><span class="ok" id="out-${ep}"></span></div></div>`).join("") + `</div>`;
    sec.querySelectorAll("[data-scan]").forEach(b => b.onclick = async () => {
      if (b.dataset.scan === "reindex" && !confirm("Alle embeddings opnieuw berekenen? Kan even duren.")) return;
      const out = sec.querySelector(`#out-${b.dataset.scan}`); out.textContent = " bezig…";
      try { const r = await api(`/graph/${b.dataset.scan}`, { method: "POST" });
        out.textContent = " ✓ " + Object.entries(r || {}).filter(([, v]) => typeof v !== "object").map(([k, v]) => `${k}: ${v}`).join(" · "); }
      catch (e) { out.textContent = " ✗ " + e.message; }
    });
  },
  async instellingen(sec) {
    const [s, knobs] = await Promise.all([api("/manage/swarm"), api("/manage/settings").catch(() => null)]);
    const knobHtml = (knobs?.groups || []).map(g => `<div class="card"><div class="ct">${g.icon || "⚙️"} ${esc(g.title)}</div>
      ${g.items.map(it => `<div style="margin:9px 0">
        <div style="display:flex;gap:8px;align-items:baseline"><b>${esc(it.key)}</b>
          <span class="pchip">${esc(String(it.value))}</span>${it.editable ? `<span class="pchip amber">live hierboven</span>` : ""}</div>
        ${it.what ? `<div style="color:var(--dim)">${esc(it.what)}</div>` : ""}
        <details><summary>aanpassen &amp; risico</summary>
          <div style="color:var(--dim)">${it.editable ? "live aanpasbaar hierboven — direct actief."
            : it.env ? `aanpasbaar via ${esc(it.env)} in <code>.env</code>, daarna <code>docker compose up -d --build</code>.`
            : "niet aanpasbaar."}</div>
          ${it.risk ? `<div style="color:var(--dim)">⚠️ ${esc(it.risk)}</div>` : ""}
        </details>
      </div>`).join("")}</div>`).join("");
    sec.innerHTML = `
      <div class="card"><div class="ct">🐝 consensus-drempel <span class="pchip amber">live</span></div>
        <div style="color:var(--dim)">stemmen (per account) voordat een Pollinate 'ready' wordt</div>
        <div class="crow"><input type="number" id="consN" min="1" style="width:80px" value="${s.consensus_threshold}">
          <span class="abtn" id="consSave">opslaan</span><span class="ok" id="consOut"></span></div></div>
      <div class="card"><div class="ct">🌍 cognition (wereld-research) <span class="pchip amber">live</span></div>
        <div style="color:var(--dim)">nieuwe memories krijgen een research-taak; budget: max ${s.cognition_budget?.max_new}/job · ${s.cognition_budget?.max_depth} rondes · ${s.cognition_budget?.daily_cap}/dag</div>
        <div class="crow"><span class="abtn ${s.cognition_enabled ? "green" : ""}" data-cog="true">aan</span>
          <span class="abtn ${!s.cognition_enabled ? "red" : ""}" data-cog="false">uit</span><span class="ok" id="cogOut"></span></div></div>
      <h3>zo staat het brein afgesteld (via .env, actief na herstart)</h3>
      <div style="color:var(--dim);margin:-4px 0 10px">alleen de twee knoppen hierboven zijn live; de rest zet je in <b>.env</b>, gevolgd door <code>docker compose up -d --build</code>. klap "risico" open voor wat er misgaat als je eraan draait.</div>${knobHtml}`;
    sec.querySelector("#consSave").onclick = async () => {
      try { await api("/manage/swarm/consensus", { method: "POST", body: JSON.stringify({ threshold: +sec.querySelector("#consN").value }) });
        sec.querySelector("#consOut").textContent = " ✓"; } catch (e) { alert(e.message); } };
    sec.querySelectorAll("[data-cog]").forEach(b => b.onclick = async () => {
      try { await api("/manage/swarm/cognition", { method: "POST", body: JSON.stringify({ enabled: b.dataset.cog === "true" }) });
        BEHEER_RENDER.instellingen(sec); } catch (e) { alert(e.message); } });
  },
  async toegang(sec) {
    const [accounts, invites, teams] = await Promise.all([
      api("/manage/accounts"), api("/manage/invites"), api("/manage/teams").catch(() => [])]);
    const accOpts = accounts.map(a => `<option value="${a.uid}">${esc(a.name)}${a.person ? " (" + esc(a.person) + ")" : ""}</option>`).join("");
    sec.innerHTML = `<div class="grid2">
      <div class="card"><div class="ct">👤 nieuw account</div>
        <label class="fl">naam</label><input type="text" id="accName" placeholder="accountnaam">
        <label class="fl">persoon (de mens erachter)</label><input type="text" id="accPerson">
        <label class="fl">team</label><select id="accTeam"><option value="">— geen team —</option>${teams.map(t => `<option value="${t.uid}">${esc(t.name)}</option>`).join("")}</select>
        <label class="fl">rol</label><select id="accRole"><option value="member">member — lezen & schrijven</option>
          <option value="maintainer">maintainer — + onderhoud</option><option value="org_admin">org_admin — + reviewen</option></select>
        <div class="crow" style="margin-top:10px"><span class="abtn amber" id="accMake">aanmaken</span><span class="ok" id="accOut"></span></div></div>
      <div class="card"><div class="ct">🎟️ token voor account</div>
        <div style="color:var(--dim)">geeft een machine/persoon toegang namens een account — eenmalig zichtbaar</div>
        <label class="fl">account</label><select id="tokAcc"><option value="">— kies account —</option>${accOpts}</select>
        <label class="fl">label</label><input type="text" id="tokLabel" placeholder="bv. werk-laptop">
        <label class="fl">rol van dit token (leeg = accountrol)</label>
        <select id="tokRole"><option value="">— accountrol —</option><option>member</option><option>maintainer</option><option>org_admin</option></select>
        <div class="crow" style="margin-top:10px"><span class="abtn amber" id="tokMake">token maken</span></div>
        <pre id="tokOut" style="display:none"></pre></div>
      <div class="card"><div class="ct">✉️ uitnodigingen</div>
        <div style="color:var(--dim)">een invite-code laat iemand zichzelf registreren met een vaste rol</div>
        <label class="fl">rol</label><select id="invRole"><option>member</option><option>maintainer</option><option>org_admin</option></select>
        <div style="display:flex;gap:8px"><div style="flex:1"><label class="fl">keer bruikbaar</label><input type="number" id="invUses" min="1" value="1"></div>
          <div style="flex:1"><label class="fl">verloopt na (dagen)</label><input type="number" id="invExp" min="1" value="14"></div></div>
        <div class="crow" style="margin-top:8px"><span class="abtn amber" id="invMake">uitnodiging maken</span></div>
        <pre id="invOut" style="display:none"></pre>
        <div id="invList" style="margin-top:8px">${invites.map(i => `<div style="display:flex;gap:8px;align-items:center;margin:3px 0;color:var(--dim)">
          🔑 ${esc(i.role)} · ${i.uses_left}× over ${i.uses_left ? `<span class="abtn red" data-rvk="${esc(i.code_hash)}">intrekken</span>` : `<span class="pchip">op</span>`}</div>`).join("")}</div></div>
    </div>
    <h3>🗝️ accounts & tokens <span class="abtn" id="tokClean" style="margin-left:8px">verlopen opruimen</span></h3>
    <div style="color:var(--dim);margin-bottom:6px">rol wijzigen geldt voor het account <b>én al zijn tokens</b>; een token kan daarna apart lager gezet worden</div>
    <div id="accList">${accounts.map(a => `<div style="margin:6px 0">
      <div style="display:flex;gap:10px;align-items:center">
        <span style="flex:1"><b>${esc(a.name)}</b>${a.person ? ` <span style="color:var(--dim)">· ${esc(a.person)}</span>` : ""}
          <span style="color:var(--dim)"> — ${a.active}/${a.tokens} tokens actief</span></span>
        ${roleSelect(`role-${a.uid}`, a.role)}
        <span class="abtn amber" data-role-acc="${a.uid}" data-role-name="${esc(a.name)}">rol opslaan</span>
        <span class="ok" id="roleOut-${a.uid}"></span>
        <span class="abtn" data-toks="${a.uid}">tokens</span></div>
      <div id="tk-${a.uid}"></div></div>`).join("")}</div>`;
    const A = { headers: {} };
    sec.querySelector("#accMake").onclick = async () => {
      try { const r = await api("/manage/accounts", { method: "POST", body: JSON.stringify({
          name: sec.querySelector("#accName").value.trim(), person: sec.querySelector("#accPerson").value.trim() || null,
          team_uid: sec.querySelector("#accTeam").value || null, role: sec.querySelector("#accRole").value }) });
        sec.querySelector("#accOut").textContent = " ✓ aangemaakt"; setTimeout(() => BEHEER_RENDER.toegang(sec), 800); }
      catch (e) { alert(e.message); } };
    sec.querySelector("#tokMake").onclick = async () => {
      try { const bdy = { account_uid: sec.querySelector("#tokAcc").value, label: sec.querySelector("#tokLabel").value.trim() || null };
        const role = sec.querySelector("#tokRole").value; if (role) bdy.role = role;
        const r = await api("/manage/tokens", { method: "POST", body: JSON.stringify(bdy) });
        const o = sec.querySelector("#tokOut"); o.style.display = "block"; o.textContent = "token (eenmalig zichtbaar!):\n" + r.token; }
      catch (e) { alert(e.message); } };
    sec.querySelector("#invMake").onclick = async () => {
      try { const r = await api("/manage/invites", { method: "POST", body: JSON.stringify({
          role: sec.querySelector("#invRole").value, uses: +sec.querySelector("#invUses").value, expires_days: +sec.querySelector("#invExp").value || null }) });
        const o = sec.querySelector("#invOut"); o.style.display = "block"; o.textContent = "invite-code (eenmalig zichtbaar!):\n" + (r.code || JSON.stringify(r)); }
      catch (e) { alert(e.message); } };
    sec.querySelectorAll("[data-rvk]").forEach(b => b.onclick = async () => {
      try { await api(`/manage/invites/${b.dataset.rvk}/revoke`, { method: "POST" }); BEHEER_RENDER.toegang(sec); } catch (e) { alert(e.message); } });
    sec.querySelector("#tokClean").onclick = async () => {
      try { const r = await api("/manage/tokens/cleanup", { method: "POST" }); alert(`${r.removed} token(s) opgeruimd`); BEHEER_RENDER.toegang(sec); }
      catch (e) { alert(e.message); } };
    sec.querySelectorAll("[data-role-acc]").forEach(b => b.onclick = async () => {
      const uid = b.dataset.roleAcc, out = sec.querySelector(`#roleOut-${uid}`);
      const role = sec.querySelector(`#role-${uid}`).value;
      if (!confirm(`Rol van ${b.dataset.roleName} op "${role}" zetten? Dit geldt ook voor al zijn tokens.`)) return;
      out.textContent = " bezig…";
      try { const r = await api(`/manage/accounts/${uid}/role`, { method: "POST", body: JSON.stringify({ role }) });
        out.textContent = ` ✓ ${r.previous || "?"} → ${r.role}`; }
      catch (e) { out.textContent = ""; alert(e.message); }
    });
    sec.querySelectorAll("[data-toks]").forEach(b => b.onclick = async () => {
      const box = sec.querySelector(`#tk-${b.dataset.toks}`);
      const tks = await api(`/manage/accounts/${b.dataset.toks}/tokens`);
      const fmtD = ms => ms ? new Date(ms).toLocaleDateString("nl-NL") : "—";
      box.innerHTML = tks.map((t, i) => `<div style="display:flex;gap:8px;align-items:center;margin:3px 0 3px 20px;color:var(--dim)">
        <span style="flex:1">${esc(t.label || "(zonder label)")} · verloopt ${fmtD(t.expires_at)}${t.revoked ? " · <b>ingetrokken</b>" : ""}</span>
        ${t.revoked ? "" : `${roleSelect(`trole-${b.dataset.toks}-${i}`, t.role, { inherit: true })}
          <span class="abtn" data-trole="${esc(t.token_hash)}" data-trole-sel="trole-${b.dataset.toks}-${i}">rol</span>
          <span class="abtn" data-rot="${esc(t.token_hash)}">rotate</span><span class="abtn red" data-rev="${esc(t.token_hash)}">intrekken</span>`}
        <span class="ok" id="troleOut-${b.dataset.toks}-${i}"></span></div>`).join("")
        || `<div class="empty" style="margin-left:20px">geen tokens</div>`;
      box.querySelectorAll("[data-trole]").forEach(x => x.onclick = async () => {
        const sel = box.querySelector(`#${x.dataset.troleSel}`);
        const out = box.querySelector(`#${x.dataset.troleSel.replace("trole-", "troleOut-")}`);
        const role = sel.value;
        if (!role) { alert("Kies een rol; '— accountrol —' laten staan verandert niets. Zet de rol van het account zelf om de accountrol te wijzigen."); return; }
        try { await api(`/manage/tokens/${x.dataset.trole}/role`, { method: "POST", body: JSON.stringify({ role }) });
          out.textContent = " ✓"; }
        catch (e) { alert(e.message); }
      });
      box.querySelectorAll("[data-rot]").forEach(x => x.onclick = async () => {
        try { const r = await api(`/manage/tokens/${x.dataset.rot}/rotate`, { method: "POST" }); alert("nieuw token (eenmalig!):\n\n" + r.token); b.onclick(); }
        catch (e) { alert(e.message); } });
      box.querySelectorAll("[data-rev]").forEach(x => x.onclick = async () => {
        if (!confirm("Dit token intrekken? De client verliest direct toegang.")) return;
        try { await api(`/manage/tokens/${x.dataset.rev}/revoke`, { method: "POST" }); b.onclick(); } catch (e) { alert(e.message); } });
    });
  },
  async data(sec) {
    sec.innerHTML = `<div class="card"><div class="ct">💾 back-up & restore</div>
      <div style="color:var(--dim)">volledige export van de hele hive (nodes, relaties, tags én bijlagen) als één JSON-bestand;
        terugzetten kan <b>samenvoegen</b> (upsert) of <b>vervangen</b> (hive eerst leegmaken = echte restore)</div>
      <div class="crow" style="margin-top:8px"><span class="abtn amber" id="expBtn">exporteren (download)</span><span class="ok" id="expOut"></span></div>
      <div style="margin-top:14px;padding-top:12px;border-top:1px solid var(--line)">
        <label class="fl">back-up-bestand</label><input type="file" id="impFile" accept="application/json,.json">
        <label class="fl">modus</label><select id="impMode"><option value="merge">samenvoegen (upsert)</option><option value="replace">vervangen (wipe + restore)</option></select>
        <div class="crow" style="margin-top:8px"><span class="abtn red" id="impBtn">importeren</span><span class="ok" id="impOut"></span></div></div></div>`;
    sec.querySelector("#expBtn").onclick = async () => {
      const out = sec.querySelector("#expOut"); out.textContent = " bezig…";
      try { const r = await fetch("/export", { headers: { Authorization: "Bearer " + TOKEN() } });
        const blob = await r.blob(); const a = document.createElement("a");
        a.href = URL.createObjectURL(blob); a.download = "nectar-export.json"; a.click(); out.textContent = " ✓"; }
      catch (e) { out.textContent = " ✗ " + e.message; } };
    sec.querySelector("#impBtn").onclick = async () => {
      const f = sec.querySelector("#impFile").files[0], mode = sec.querySelector("#impMode").value, out = sec.querySelector("#impOut");
      if (!f) { alert("Kies eerst een back-up-bestand."); return; }
      if (mode === "replace" && !confirm("VERVANGEN maakt de hele hive eerst leeg en zet daarna de back-up terug. Doorgaan?")) return;
      out.textContent = " bezig…";
      try { const bodyTxt = await f.text();
        const r = await fetch("/import?mode=" + mode, { method: "POST",
          headers: { Authorization: "Bearer " + TOKEN(), "Content-Type": "application/json" }, body: bodyTxt });
        const j = await r.json(); if (!r.ok) throw new Error(j.detail || r.status);
        out.textContent = ` ✓ ${j.imported.nodes} nodes, ${j.imported.relationships} relaties, ${j.imported.attachments} bijlagen`; }
      catch (e) { out.textContent = ""; alert(e.message); } };
  },
  async pakket(sec) {
    let skills = [];
    try { skills = await api("/skills"); } catch {}
    sec.innerHTML = `<div class="card"><div class="ct">📦 install-pakket voor claude</div>
      <div style="color:var(--dim)">download de zip, geef 'm samen met een token aan iemand; claude installeert nectar zelf (recall-hook + mcp)</div>
      <div class="crow" style="margin-top:8px"><a class="abtn amber" href="/install.zip" download>download install-zip</a></div></div>
      <h3>✨ skills in de hive (${skills.length})</h3>
      <div style="color:var(--dim);margin-bottom:8px">in een hive-verbonden claude: vraag "laad skill X", of kopieer het commando</div>
      ${skills.map(sk => { const cmd = `~/.hivemind/scripts/hive-skill-install.sh "${sk.title}"`;
        return `<div style="margin:8px 0"><b>✨ ${esc(sk.title)}</b>
          <div style="display:flex;gap:8px;align-items:center"><code style="flex:1;color:var(--dim);font-size:10.5px">${esc(cmd)}</code>
          <span class="abtn" data-view="${esc(sk.uid)}">bekijken</span>
          ${onJump ? `<span class="abtn" data-node="${esc(sk.uid)}">naar node</span>` : ""}
          <span class="abtn" data-copy="${esc(cmd)}">kopieer</span></div>
          <div id="sk-${esc(sk.uid)}"></div></div>`; }).join("") || `<div class="empty">nog geen skills in de hive</div>`}`;
    sec.querySelectorAll("[data-copy]").forEach(b => b.onclick = () => {
      navigator.clipboard?.writeText(b.dataset.copy); b.textContent = "✓"; setTimeout(() => b.textContent = "kopieer", 1200); });
    sec.querySelectorAll("[data-node]").forEach(b => b.onclick = () => { close(); onJump?.(b.dataset.node); });
    /* bekijken = de bestanden van de skill uitklappen, zoals in de legacy-GUI */
    sec.querySelectorAll("[data-view]").forEach(b => b.onclick = async () => {
      const box = sec.querySelector(`[id="sk-${b.dataset.view}"]`);
      if (box.dataset.open === "1") { box.innerHTML = ""; box.dataset.open = ""; b.textContent = "bekijken"; return; }
      box.innerHTML = `<div style="color:var(--dim)">laden…</div>`;
      try {
        const s = await api("/skills/" + b.dataset.view);
        const files = (s.files || []).map(f =>
          `<div style="margin-top:8px"><div style="color:var(--cyan);font-size:10.5px">${esc(f.path)}</div>
            <div class="cex" style="max-height:260px">${esc(f.content)}</div></div>`).join("");
        box.innerHTML = `<div style="margin-top:8px;border-top:1px solid var(--line);padding-top:8px">
          ${s.description ? `<div style="color:var(--dim)">${esc(s.description)}</div>` : ""}
          ${files || `<div class="empty">deze skill heeft geen bestanden</div>`}</div>`;
        box.dataset.open = "1"; b.textContent = "verbergen";
      } catch (e) { box.innerHTML = `<div style="color:#ff7847">${esc(e.message)}</div>`; }
    });
  },
};

/* ─── raamwerk ──────────────────────────────────────────────────────── */
const RENDER = { focus: renderFocus, chores: renderChores, review: renderReview,
                 governance: renderGovernance, historie: renderHistorie, beheer: renderBeheer };
const TITLES = { focus: "focus", chores: "pollinate", review: "review",
                 governance: "governance", historie: "historie", beheer: "beheer" };

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
  if (!ME) { try { ME = await api("/graph/me"); } catch { location.reload(); return; } }
  if (ADMIN_ONLY.has(name) && !ME.can_review) name = "chores";
  current = name;
  titleEl.textContent = TITLES[name] || name;
  tabsEl.innerHTML = DECKS.filter(([k]) => !ADMIN_ONLY.has(k) || ME.can_review).map(([k, l]) =>
    `<span class="chip ${k === current ? "on" : ""}" data-deck="${k}">${l}${k === "chores" && ME.ready_chores ? ` <b style="color:var(--amber)">${ME.ready_chores}</b>` : ""}</span>`).join("");
  tabsEl.querySelectorAll("[data-deck]").forEach(c => c.onclick = () => open(c.dataset.deck));
  host.classList.add("on");
  body.innerHTML = `<div class="empty">laden…</div>`;
  try { await RENDER[name](); } catch (e) { body.innerHTML = `<div class="empty">fout: ${esc(e.message)}</div>`; }
}

function close() { host?.classList.remove("on"); current = null; }
function isOpen() { return !!host?.classList.contains("on"); }

/* mind.src.js geeft hier de spring-naar-node callback door (historie → de 3D-mind) */
function init(opts = {}) { onJump = opts.onJump || null; }

export const Decks = { open, close, isOpen, init };
