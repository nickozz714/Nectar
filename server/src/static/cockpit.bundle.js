var __getOwnPropNames = Object.getOwnPropertyNames;
var __commonJS = (cb, mod) => function __require() {
  try {
    return mod || (0, cb[__getOwnPropNames(cb)[0]])((mod = { exports: {} }).exports, mod), mod.exports;
  } catch (e) {
    throw mod = 0, e;
  }
};

// cockpit.src.js
var require_cockpit_src = __commonJS({
  "cockpit.src.js"() {
    var TYPE_COLORS = {
      topic: "#f0a63a",
      memory: "#2fc4e8",
      decision: "#ff6a45",
      learning: "#43d98a",
      process: "#5fa4e6",
      workflow: "#8f76e8",
      skill: "#a06ae8",
      convention: "#e6c05c",
      glossary: "#6d87a0"
    };
    var TYPE_LABEL = {
      topic: "topic",
      memory: "memory",
      decision: "besluit",
      learning: "learning",
      process: "proces",
      workflow: "workflow",
      skill: "skill",
      convention: "conventie",
      glossary: "glossary"
    };
    var $ = (id) => document.getElementById(id);
    var stage = $("stage");
    var wires = $("wires");
    var hexA = (hex, a) => {
      const n = parseInt(hex.slice(1), 16);
      return `rgba(${n >> 16 & 255},${n >> 8 & 255},${n & 255},${a})`;
    };
    var nodes = /* @__PURE__ */ new Map();
    var parentsOf = /* @__PURE__ */ new Map();
    var childrenOf = /* @__PURE__ */ new Map();
    var relatedOf = /* @__PURE__ */ new Map();
    var totals = { nodes: 0, links: 0 };
    var focusId = null;
    var trail = [];
    var expanded = { parents: false, children: false, related: false };
    var detailCache = /* @__PURE__ */ new Map();
    var cards = /* @__PURE__ */ new Map();
    var pendingRemove = /* @__PURE__ */ new Map();
    var wireAnim = 0;
    var SERVER = location.pathname.startsWith("/ui/");
    var TOKEN = SERVER ? localStorage.getItem("hive_token") || "" : "";
    if (SERVER && !TOKEN) location.replace("/ui");
    var AUTH = SERVER ? { headers: { Authorization: "Bearer " + TOKEN } } : void 0;
    async function loadData() {
      const r = await fetch(SERVER ? "/graph/full" : "./data.json", AUTH);
      if (SERVER && (r.status === 401 || r.status === 403)) {
        location.replace("/ui");
        throw new Error("login");
      }
      if (!r.ok) throw new Error(`data.json: HTTP ${r.status}`);
      const d = await r.json();
      totals = { nodes: d.nodes.length, links: d.links.length };
      nodes = new Map(d.nodes.map((n) => [n.id, n]));
      const push = (m, k, v) => {
        if (!m.has(k)) m.set(k, []);
        m.get(k).push(v);
      };
      for (const l of d.links) {
        if (!nodes.has(l.source) || !nodes.has(l.target)) continue;
        if (l.rel === "CONTAINS") {
          push(childrenOf, l.source, l.target);
          push(parentsOf, l.target, l.source);
        } else {
          push(relatedOf, l.source, l.target);
          push(relatedOf, l.target, l.source);
        }
      }
      for (const [k, v] of relatedOf) relatedOf.set(k, [...new Set(v)]);
    }
    var byRank = (a, b) => (nodes.get(b)?.pagerank ?? 0) - (nodes.get(a)?.pagerank ?? 0);
    function bandsFor(id) {
      const parents = [...parentsOf.get(id) ?? []].sort(byRank);
      const children = [...childrenOf.get(id) ?? []].sort(byRank);
      const skip = /* @__PURE__ */ new Set([id, ...parents, ...children]);
      const related = [...relatedOf.get(id) ?? []].filter((x) => !skip.has(x)).sort(byRank);
      return { parents, children, related };
    }
    function getDetail(id) {
      if (!detailCache.has(id))
        detailCache.set(id, fetch(SERVER ? `/graph/node/${id}` : `./api/node/${id}`, AUTH).then((r) => r.ok ? r.json() : null).catch(() => null));
      return detailCache.get(id);
    }
    var FOCUS_W = 340;
    var FOCUS_H = 200;
    var CARD_W = 180;
    var CARD_H = 66;
    var GAP = 14;
    var BAND_GAP = 92;
    function layout() {
      const W = innerWidth, H = innerHeight;
      const panelW = Math.min(360, W * 0.4) + 52;
      const cx = Math.max(FOCUS_W / 2 + 40, (W - panelW) / 2);
      const bands = bandsFor(focusId);
      let cy = H / 2 + 14;
      if (!bands.parents.length && bands.children.length) cy -= Math.min(120, H * 0.11);
      if (!bands.children.length && bands.parents.length) cy += Math.min(120, H * 0.11);
      if (expanded.children) cy -= Math.min(90, H * 0.08);
      if (expanded.parents) cy += Math.min(90, H * 0.08);
      const out = [];
      out.push({ key: focusId, id: focusId, kind: "focus", x: cx, y: cy, w: FOCUS_W, h: FOCUS_H });
      const availW = W - panelW - 60;
      const rowBand = (ids, kind, dir) => {
        if (!ids.length) return;
        const exp = expanded[kind];
        const cw = exp ? 150 : CARD_W, ch = exp ? 54 : CARD_H, g = exp ? 10 : GAP;
        const bandGap = exp ? 66 : BAND_GAP;
        const perRow = Math.max(2, Math.floor((availW + g) / (cw + g)));
        const firstY = cy + dir * (FOCUS_H / 2 + bandGap + ch / 2);
        const edgeY = dir < 0 ? 96 : H - 96;
        const maxRows = Math.max(1, Math.floor(Math.abs(edgeY - firstY) / (ch + g)) + 1);
        const cap = exp ? maxRows * perRow : Math.min(8, perRow);
        let vis = ids, more = 0;
        if (ids.length > cap) {
          vis = ids.slice(0, cap - 1);
          more = ids.length - vis.length;
        }
        const slots = vis.slice();
        if (more) slots.push("__more");
        const rows = [];
        for (let i = 0; i < slots.length; i += perRow) rows.push(slots.slice(i, i + perRow));
        rows.forEach((row, ri) => {
          const y = firstY + dir * ri * (ch + g);
          const total = row.length * (cw + g) - g;
          row.forEach((rid, i) => {
            const x = cx - total / 2 + cw / 2 + i * (cw + g);
            if (rid === "__more")
              out.push({ key: `__more_${kind}`, kind: "more", band: kind, more, inert: exp, x, y, w: cw, h: ch });
            else
              out.push({ key: rid, id: rid, kind, x, y, w: cw, h: ch, rel: "CONTAINS" });
          });
        });
        const lastY = firstY + dir * (rows.length - 1) * (ch + g);
        out.push({
          key: `__label_${kind}`,
          kind: "label",
          text: kind === "parents" ? "\u25B4 ouders" : "\u25BE kinderen",
          x: cx,
          y: lastY + dir * (ch / 2 + 18),
          w: 120,
          h: 14
        });
      };
      rowBand(bands.parents, "parents", -1);
      rowBand(bands.children, "children", 1);
      if (bands.related.length) {
        const perCol = Math.max(2, Math.floor((H - 300) / (CARD_H + GAP)));
        let ids = bands.related, more = 0;
        const visMax = expanded.related ? perCol * 6 : Math.min(8, perCol * 2);
        if (ids.length > visMax) {
          ids = ids.slice(0, visMax - 1);
          more = bands.related.length - ids.length;
        }
        const slots = [...ids.map((id) => ({ id })), ...more ? [{ more, inert: expanded.related }] : []];
        const right = slots.filter((_, i) => i % 2 === 0), left = slots.filter((_, i) => i % 2 === 1);
        const side = (arr, sgn) => {
          arr.forEach((s, i) => {
            const col = Math.floor(i / perCol), row = i % perCol;
            const n = Math.min(arr.length - col * perCol, perCol);
            const x = cx + sgn * (FOCUS_W / 2 + 96 + CARD_W / 2 + col * (CARD_W + GAP));
            const y = cy + (row - (n - 1) / 2) * (CARD_H + GAP);
            if (s.more) out.push({ key: "__more_related", kind: "more", band: "related", more: s.more, inert: s.inert, x, y, w: CARD_W, h: CARD_H });
            else out.push({ key: s.id, id: s.id, kind: "related", x, y, w: CARD_W, h: CARD_H, rel: "RELATES" });
          });
        };
        side(right, 1);
        side(left, -1);
      }
      return out;
    }
    function cardHTML(node) {
      return `<div class="ct"></div><div class="cchip"></div><div class="cex"></div><div class="cnums"></div>`;
    }
    function styleCard(el, item) {
      const isFocus = item.kind === "focus";
      if (item.kind === "more") {
        el.className = "card more";
        el.querySelector(".ct").textContent = item.inert ? `+${item.more} buiten beeld` : `+${item.more} meer`;
        el.style.borderColor = "";
        el.style.boxShadow = "none";
        el.style.cursor = item.inert ? "default" : "pointer";
      } else {
        const n = nodes.get(item.id);
        const c = TYPE_COLORS[n.type] ?? "#6d87a0";
        el.className = "card" + (isFocus ? " focus" : "");
        el.querySelector(".ct").textContent = n.title;
        const chip = el.querySelector(".cchip");
        chip.textContent = TYPE_LABEL[n.type] ?? n.type;
        chip.style.color = c;
        chip.style.borderColor = hexA(c, 0.45);
        el.style.borderColor = hexA(c, isFocus ? 0.8 : 0.3);
        el.style.boxShadow = isFocus ? `0 0 34px ${hexA(c, 0.22)}, inset 0 0 22px rgba(0,0,0,.35)` : "none";
        if (isFocus) fillFocusExtras(el, n);
      }
      el.style.width = item.w + "px";
      el.style.height = item.h + "px";
      el.style.transform = `translate(${item.x - item.w / 2}px, ${item.y - item.h / 2}px)`;
    }
    async function fillFocusExtras(el, n) {
      const nums = el.querySelector(".cnums");
      const kids = childrenOf.get(n.id)?.length ?? 0, rel = relatedOf.get(n.id)?.length ?? 0;
      const numTxt = (uc) => `${kids} kinderen \xB7 ${rel} verwant \xB7 \xD7${uc} gebruikt`;
      nums.textContent = numTxt(n.use_count ?? 0);
      const d = await getDetail(n.id);
      if (focusId !== n.id) return;
      nums.textContent = numTxt(d?.use_count ?? n.use_count ?? 0);
      const ex = el.querySelector(".cex");
      ex.textContent = (d?.content || d?.summary || "\u2014 geen inhoud \u2014").trim();
    }
    function render(animate = true) {
      const items = layout();
      const keep = new Set(items.map((i) => i.key));
      for (const [key, rec] of cards) {
        if (keep.has(key)) continue;
        rec.el.style.opacity = "0";
        rec.el.style.transform += " scale(.86)";
        rec.el.style.pointerEvents = "none";
        pendingRemove.set(key, setTimeout(() => {
          rec.el.remove();
          cards.delete(key);
          pendingRemove.delete(key);
        }, 400));
      }
      for (const item of items) {
        if (item.kind === "label") {
          renderLabel(item, animate);
          continue;
        }
        let rec = cards.get(item.key);
        if (rec && pendingRemove.has(item.key)) {
          clearTimeout(pendingRemove.get(item.key));
          pendingRemove.delete(item.key);
        }
        if (!rec) {
          const el = document.createElement("div");
          el.innerHTML = cardHTML();
          const key = item.key;
          el.addEventListener("click", () => {
            const it = cards.get(key)?.item;
            if (!it) return;
            if (it.kind === "more") {
              if (!it.inert) {
                expanded[it.band] = true;
                render();
              }
            } else if (it.kind !== "focus") setFocus(it.id);
          });
          stage.appendChild(el);
          rec = { el, item };
          cards.set(item.key, rec);
          el.style.transition = "none";
          styleCard(el, item);
          el.style.opacity = "0";
          el.style.transform += " scale(.86)";
          void el.offsetWidth;
          el.style.transition = "";
        }
        rec.item = item;
        rec.el.style.pointerEvents = "";
        styleCard(rec.el, item);
        rec.el.style.opacity = item.kind === "more" && item.inert ? ".55" : "1";
      }
      animateWires(animate ? 700 : 60);
      updateStats();
    }
    function renderLabel(item, animate) {
      let rec = cards.get(item.key);
      if (rec && pendingRemove.has(item.key)) {
        clearTimeout(pendingRemove.get(item.key));
        pendingRemove.delete(item.key);
      }
      if (!rec) {
        const el = document.createElement("div");
        el.className = "bandlabel";
        stage.appendChild(el);
        rec = { el, item };
        cards.set(item.key, rec);
        el.style.transition = "none";
        el.style.transform = `translate(${item.x - 60}px, ${item.y - 7}px)`;
        void el.offsetWidth;
        el.style.transition = "";
      }
      rec.item = item;
      rec.el.textContent = item.text;
      rec.el.style.width = "120px";
      rec.el.style.textAlign = "center";
      rec.el.style.transform = `translate(${item.x - 60}px, ${item.y - 7}px)`;
      rec.el.style.opacity = ".85";
    }
    function drawWires() {
      const focus = cards.get(focusId);
      if (!focus) {
        wires.innerHTML = "";
        return;
      }
      const fr = focus.el.getBoundingClientRect();
      const fx = fr.left + fr.width / 2, fy = fr.top + fr.height / 2;
      let svg = "";
      for (const [key, rec] of cards) {
        const it = rec.item;
        if (!it || it.kind === "focus" || it.kind === "label" || it.kind === "more") continue;
        const r = rec.el.getBoundingClientRect();
        const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
        const o = parseFloat(getComputedStyle(rec.el).opacity || "1");
        const col = it.rel === "CONTAINS" ? "255,181,71" : "62,224,255";
        let d;
        if (it.kind === "parents" || it.kind === "children") {
          const y0 = it.kind === "parents" ? fr.top : fr.bottom;
          const y1 = it.kind === "parents" ? r.bottom : r.top;
          const mid = (y0 + y1) / 2;
          d = `M ${fx} ${y0} C ${fx} ${mid}, ${cx} ${mid}, ${cx} ${y1}`;
        } else {
          const leftSide = cx < fx;
          const x0 = leftSide ? fr.left : fr.right;
          const x1 = leftSide ? r.right : r.left;
          const mid = (x0 + x1) / 2;
          d = `M ${x0} ${fy} C ${mid} ${fy}, ${mid} ${cy}, ${x1} ${cy}`;
        }
        svg += `<path d="${d}" fill="none" stroke="rgba(${col},${(0.32 * o).toFixed(3)})" stroke-width="1.4"/><circle cx="${cx}" cy="${cy}" r="2" fill="rgba(${col},${(0.5 * o).toFixed(3)})"/>`;
      }
      wires.setAttribute("width", innerWidth);
      wires.setAttribute("height", innerHeight);
      wires.innerHTML = svg;
    }
    function animateWires(ms) {
      cancelAnimationFrame(wireAnim);
      const t0 = performance.now();
      const tick = (t) => {
        drawWires();
        if (t - t0 < ms) wireAnim = requestAnimationFrame(tick);
      };
      wireAnim = requestAnimationFrame(tick);
    }
    function setFocus(id, { pushTrail = true } = {}) {
      if (!nodes.has(id) || id === focusId) return;
      focusId = id;
      expanded = { parents: false, children: false, related: false };
      if (pushTrail) trail.push(id);
      render();
      renderCrumbs();
      renderPanel();
    }
    function goBack() {
      if (trail.length < 2) return;
      trail.pop();
      setFocus(trail[trail.length - 1], { pushTrail: false });
    }
    function renderCrumbs() {
      const el = $("crumbs");
      el.innerHTML = "";
      const show = trail.slice(-6);
      show.forEach((id, i) => {
        if (i) {
          const s = document.createElement("span");
          s.className = "sep";
          s.textContent = "\u203A";
          el.appendChild(s);
        }
        const c = document.createElement("div");
        const isNow = i === show.length - 1;
        c.className = "crumb" + (isNow ? " now" : "");
        c.textContent = nodes.get(id)?.title ?? "?";
        if (!isNow) c.addEventListener("click", () => {
          const gi = trail.length - show.length + i;
          trail = trail.slice(0, gi + 1);
          setFocus(trail[trail.length - 1], { pushTrail: false });
        });
        el.appendChild(c);
      });
    }
    function updateStats() {
      const b = bandsFor(focusId);
      $("stats").innerHTML = `<b>${totals.nodes}</b> nodes \xB7 <b>${totals.links}</b> links<br>focus: <b>${b.parents.length}</b> ouders \xB7 <b>${b.children.length}</b> kinderen \xB7 <b>${b.related.length}</b> verwant`;
    }
    async function renderPanel() {
      const id = focusId, n = nodes.get(id);
      const panel = $("panel");
      panel.classList.add("open");
      $("pTitle").textContent = n.title;
      const chips = [];
      const c = TYPE_COLORS[n.type] ?? "#6d87a0";
      chips.push(`<span class="pchip" style="color:${c};border-color:${hexA(c, 0.45)}">${TYPE_LABEL[n.type] ?? n.type}</span>`);
      if (n.lifecycle) chips.push(`<span class="pchip dim">${n.lifecycle}</span>`);
      if (n.scope) chips.push(`<span class="pchip dim">${n.scope}</span>`);
      if (n.use_count) chips.push(`<span class="pchip amber">\xD7${n.use_count} gebruikt</span>`);
      if (n.pagerank) chips.push(`<span class="pchip dim">rank ${(+n.pagerank).toFixed(2)}</span>`);
      $("pChips").innerHTML = chips.join("");
      $("pBody").textContent = "\u2026";
      $("pTags").innerHTML = (n.tags ?? []).map((t) => `<span class="pchip">#${t}</span>`).join("");
      const d = await getDetail(id);
      if (focusId !== id) return;
      $("pBody").textContent = (d?.content || d?.summary || n.title).trim();
    }
    function initSearch() {
      const input = $("search"), box = $("results");
      let hits = [], sel = -1;
      const close = () => {
        box.style.display = "none";
        hits = [];
        sel = -1;
      };
      const pick = (id) => {
        close();
        input.value = "";
        input.blur();
        setFocus(id);
      };
      const show = () => {
        if (!hits.length) return close();
        box.innerHTML = hits.map((n, i) => {
          const c = TYPE_COLORS[n.type] ?? "#6d87a0";
          return `<div data-i="${i}" class="${i === sel ? "sel" : ""}">
        <span class="dot" style="background:${c}"></span><span class="rt">${n.title}</span></div>`;
        }).join("");
        box.style.display = "block";
        [...box.children].forEach((el) => el.addEventListener("click", () => pick(hits[+el.dataset.i].id)));
      };
      let semTmr;
      input.addEventListener("input", () => {
        const q = input.value.trim().toLowerCase();
        if (q.length < 2) return close();
        hits = [...nodes.values()].filter((n) => n.title.toLowerCase().includes(q)).sort((a, b) => (b.pagerank ?? 0) - (a.pagerank ?? 0)).slice(0, 14);
        sel = hits.length ? 0 : -1;
        show();
        if (!SERVER) return;
        clearTimeout(semTmr);
        semTmr = setTimeout(async () => {
          try {
            const r = await fetch(`/graph/search?q=${encodeURIComponent(input.value.trim())}`, AUTH);
            if (!r.ok) return;
            const sem = await r.json();
            if (input.value.trim().toLowerCase() !== q) return;
            const seen = new Set(hits.map((h) => h.id));
            const extra = sem.map((x) => nodes.get(x.uid)).filter((x) => x && !seen.has(x.id));
            hits = [...hits, ...extra].slice(0, 14);
            if (sel < 0 && hits.length) sel = 0;
            show();
          } catch {
          }
        }, 220);
      });
      input.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
          close();
          input.blur();
          e.stopPropagation();
        } else if (e.key === "ArrowDown") {
          sel = Math.min(sel + 1, hits.length - 1);
          show();
          e.preventDefault();
        } else if (e.key === "ArrowUp") {
          sel = Math.max(sel - 1, 0);
          show();
          e.preventDefault();
        } else if (e.key === "Enter" && sel >= 0) pick(hits[sel].id);
      });
      document.addEventListener("click", (e) => {
        if (!$("searchBox").contains(e.target)) close();
      });
    }
    var PARAMS = new URLSearchParams(location.search);
    var EMBED = PARAMS.get("embed") === "1";
    var post = (msg) => {
      if (EMBED && window.parent !== window) window.parent.postMessage(msg, "*");
    };
    function initEmbed() {
      if (SERVER && !EMBED) {
        const v = document.getElementById("variants");
        if (v) v.innerHTML = `<a class="chip" href="/ui/mind">\u25C2 mind</a><a class="chip" href="/ui#legacy">\u2302 legacy</a>`;
      }
      if (!EMBED) return;
      document.getElementById("variants")?.remove();
      for (const c of document.querySelectorAll(".corner")) c.remove();
      const bar = document.createElement("div");
      bar.style.cssText = "position:fixed;top:18px;right:24px;z-index:30;display:flex;gap:8px";
      const mk = (txt, fn, amber) => {
        const c = document.createElement("span");
        c.className = "chip";
        if (amber) {
          c.style.color = "var(--amber)";
          c.style.borderColor = "rgba(255,181,71,.4)";
        }
        c.textContent = txt;
        c.addEventListener("click", fn);
        bar.appendChild(c);
      };
      mk("\u229A toon in stelsel", () => post({ type: "showInSystem", id: focusId }), true);
      mk("\u2715 sluit drilldown", () => post({ type: "close" }));
      document.body.appendChild(bar);
      const sb = document.getElementById("searchBox");
      if (sb) sb.style.right = "300px";
    }
    async function main() {
      await loadData();
      initEmbed();
      let best = null, bestN = -1;
      for (const n of nodes.values()) {
        if (n.type !== "topic") continue;
        const k = childrenOf.get(n.id)?.length ?? 0;
        if (k > bestN) {
          bestN = k;
          best = n.id;
        }
      }
      if (!best) throw new Error("geen topics gevonden in data.json");
      const params = PARAMS;
      const q = params.get("start");
      if (q) {
        const hit = [...nodes.values()].find((n) => n.title.toLowerCase().includes(q.toLowerCase()));
        if (hit) best = hit.id;
      }
      const fid = params.get("focus");
      if (fid && nodes.has(fid)) best = fid;
      initSearch();
      window.addEventListener("keydown", (e) => {
        if (e.key !== "Escape" || document.activeElement === $("search")) return;
        if (trail.length < 2 && EMBED) {
          post({ type: "close" });
          return;
        }
        goBack();
      });
      window.addEventListener("resize", () => render(false));
      setFocus(best);
      const ex = params.get("expand");
      if (ex && ex in expanded) {
        expanded[ex] = true;
        render();
      }
      $("splash").style.display = "none";
    }
    main();
  }
});
export default require_cockpit_src();
