/**
 * The Nectar mind-graph island: React Flow renders/interacts, d3-force (in store.js)
 * lays out. Hover shows a tooltip with lazily-fetched node detail; single click selects
 * + expands, double click collapses back to the parent — same interaction language as
 * the old hand-rolled SVG graph.
 */
import { useMemo, useRef, useState, useSyncExternalStore } from "react";
import { ReactFlow, Handle, Position, useInternalNode } from "@xyflow/react";
import {
  store, subscribe, getVersion, typeVisible, nodeRadius, nodeColor,
  hasVisibleChildren, fetchDetail,
  clickNode, collapseAndFocusParent, deselect,
  dragStart, drag, dragStop,
} from "./store.js";

/* ---------- custom node ---------- */
function NectarNode({ id, data }) {
  const r = data.r;
  const cls = ["ng-node", "ng-" + data.nodeType,
    data.dimmed ? "dim" : "", data.selected ? "sel" : ""].filter(Boolean).join(" ");
  return (
    <div className={cls} style={{ width: r * 2, height: r * 2 }}>
      <Handle type="target" position={Position.Top} className="ng-handle" isConnectable={false} />
      <Handle type="source" position={Position.Bottom} className="ng-handle" isConnectable={false} />
      {data.nodeType === "hive" && data.sciFi && (
        <div className="ng-core">
          <div className="glow" />
          <div className="ring r1" />
          <div className="ring r2" />
        </div>
      )}
      <div className="ng-shape" style={{ background: data.color }} />
      {data.collapsible && (
        <button className="ng-collapse" title="Inklappen"
          onPointerDown={(e) => e.stopPropagation()}
          onClick={(e) => { e.stopPropagation(); collapseAndFocusParent(id); }}>−</button>
      )}
      <div className="ng-label">{data.label}</div>
    </div>
  );
}

/* ---------- floating edge: circle-edge to circle-edge, arrow just outside the target ---------- */
function centerOf(n, fallback) {
  const w = n.measured?.width ?? fallback, h = n.measured?.height ?? fallback;
  return { x: n.internals.positionAbsolute.x + w / 2, y: n.internals.positionAbsolute.y + h / 2 };
}
function FloatingEdge({ source, target, data }) {
  const s = useInternalNode(source), t = useInternalNode(target);
  if (!s || !t) return null;
  const sc = centerOf(s, data.sr * 2), tc = centerOf(t, data.tr * 2);
  const dx = tc.x - sc.x, dy = tc.y - sc.y, dist = Math.hypot(dx, dy) || 1;
  const ux = dx / dist, uy = dy / dist;
  const sx = sc.x + ux * (data.sr + 2), sy = sc.y + uy * (data.sr + 2);
  const tx = tc.x - ux * (data.tr + 8), ty = tc.y - uy * (data.tr + 8);
  const cls = ["ng-edge", data.rel === "relates" ? "relates" : "", data.lit ? "" : "dim"]
    .filter(Boolean).join(" ");
  return (
    <g className={cls}>
      <path d={`M${sx},${sy}L${tx},${ty}`} fill="none" markerEnd="url(#ng-arw)" />
      <text className="ng-elabel" x={(sx + tx) / 2} y={(sy + ty) / 2 - 4} textAnchor="middle">
        {data.rel}
      </text>
    </g>
  );
}

const nodeTypes = { nectar: NectarNode };
const edgeTypes = { floating: FloatingEdge };

/* ---------- tooltip ---------- */
function truncate(s, n) { return s && s.length > n ? s.slice(0, n - 1) + "…" : s; }

function NodeTooltip({ uid, x, y, wrapW }) {
  const n = store.byId.get(uid);
  if (!n) return null;
  const style = { left: Math.max(8, Math.min(x + 14, (wrapW || 800) - 316)), top: y + 16 };
  if (n.type === "attachment") {
    return (
      <div className="ng-tip" style={style}>
        <div className="ng-tip-title">📎 {n.filename}</div>
        <div className="ng-tip-meta">bijlage · klik voor een preview</div>
      </div>
    );
  }
  if (n.type === "hive") {
    return (
      <div className="ng-tip" style={style}>
        <div className="ng-tip-title">{n.title}</div>
        <div className="ng-tip-meta">het hart van de hive — klik een topic om uit te klappen</div>
      </div>
    );
  }
  const d = fetchDetail(uid);
  const body = d && (d.type === "topic" ? d.summary : d.content);
  return (
    <div className="ng-tip" style={style}>
      <div className="ng-tip-head">
        <span className="ng-tip-dot" style={{ background: nodeColor(n) }} />
        <span className="ng-tip-type">{n.type}</span>
        {d && d.lifecycle && <span className="ng-tip-badge">{d.lifecycle}</span>}
      </div>
      <div className="ng-tip-title">{n.title}</div>
      {body && <div className="ng-tip-body">{truncate(body, 300)}</div>}
      {d && d.tags && d.tags.length > 0 && (
        <div className="ng-tip-tags">{d.tags.slice(0, 6).map((t) => (
          <span key={t} className="ng-tip-tag">#{t}</span>
        ))}</div>
      )}
      {d
        ? <div className="ng-tip-meta">{(d.use_count ?? 0)}× gebruikt{d.scope ? ` · scope ${d.scope}` : ""}</div>
        : <div className="ng-tip-meta">laden…</div>}
    </div>
  );
}

/* ---------- app ---------- */
export default function GraphApp() {
  useSyncExternalStore(subscribe, getVersion);
  const wrapRef = useRef(null);
  const clickTimer = useRef(null);
  const tipTimer = useRef(null);
  const [tip, setTip] = useState(null);          // {uid, x, y}
  const [labelsOn, setLabelsOn] = useState(true);

  const hiveUid = store.bridge?.hiveUid;
  const selected = store.selectedUid;

  // Soft focus: dim everything that isn't the selection or a direct neighbour.
  const focusSet = useMemo(() => {
    if (!selected) return null;
    const set = new Set([selected]);
    for (const l of store.links) {
      if (l.a === selected) set.add(l.b);
      if (l.b === selected) set.add(l.a);
    }
    return set;
    // store.version covers links/selection changes
  }, [selected, store.version]);   // eslint-disable-line react-hooks/exhaustive-deps

  const nodes = useMemo(() => store.nodes
    .filter((n) => typeVisible(n.type))
    .map((n) => {
      const r = nodeRadius(n.type);
      const isSel = n.id === selected;
      const title = (n.type === "attachment" ? "📎 " : "")
        + (n.title.length > 28 ? n.title.slice(0, 27) + "…" : n.title);
      return {
        id: n.id,
        type: "nectar",
        position: { x: n.x, y: n.y },
        draggable: !(n.id === hiveUid || n.id === store.projectRoot),
        data: {
          nodeType: n.type, r, label: title, color: nodeColor(n),
          selected: isSel,
          dimmed: focusSet ? !focusSet.has(n.id) : false,
          sciFi: store.sciFi,
          collapsible: isSel && n.id !== hiveUid && n.type !== "attachment" && hasVisibleChildren(n.id),
        },
      };
    }), [store.version, focusSet, selected, hiveUid]);  // eslint-disable-line react-hooks/exhaustive-deps

  const edges = useMemo(() => store.links
    .filter((l) => {
      const p = store.byId.get(l.a), q = store.byId.get(l.b);
      return p && q && typeVisible(p.type) && typeVisible(q.type);
    })
    .map((l) => ({
      id: l.a + "|" + l.b,
      source: l.a,
      target: l.b,
      type: "floating",
      data: {
        rel: l.rel,
        lit: !focusSet || l.a === selected || l.b === selected,
        sr: nodeRadius(store.byId.get(l.a).type),
        tr: nodeRadius(store.byId.get(l.b).type),
      },
    })), [store.version, focusSet, selected]);  // eslint-disable-line react-hooks/exhaustive-deps

  const hideTip = () => {
    if (tipTimer.current) { clearTimeout(tipTimer.current); tipTimer.current = null; }
    setTip(null);
  };

  const onNodeMouseEnter = (e, node) => {
    if (tipTimer.current) clearTimeout(tipTimer.current);
    const rect = wrapRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left, y = e.clientY - rect.top;
    tipTimer.current = setTimeout(() => setTip({ uid: node.id, x, y }), 220);
  };

  const onNodeClick = (e, node) => {
    hideTip();
    if (clickTimer.current) clearTimeout(clickTimer.current);
    // defer so a double-click can cancel the expand (same 220ms as the old graph)
    clickTimer.current = setTimeout(() => {
      clickTimer.current = null;
      clickNode(node.id);
    }, 220);
  };

  const onNodeDoubleClick = (e, node) => {
    if (clickTimer.current) { clearTimeout(clickTimer.current); clickTimer.current = null; }
    hideTip();
    collapseAndFocusParent(node.id);
  };

  const onPaneClick = () => {
    hideTip();
    deselect();
    store.bridge?.onSelectionCleared();
  };

  return (
    <div ref={wrapRef}
      className={"ng-wrap" + (store.sciFi ? " scifi" : "") + (labelsOn ? "" : " nolabels")}>
      <svg style={{ position: "absolute", width: 0, height: 0 }} aria-hidden="true">
        <defs>
          <marker id="ng-arw" viewBox="0 0 10 10" refX="8" refY="5"
            markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">
            <path d="M0,0L10,5L0,10z" />
          </marker>
        </defs>
      </svg>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        nodeOrigin={[0.5, 0.5]}
        onInit={(inst) => { store.rf = inst; }}
        onNodeClick={onNodeClick}
        onNodeDoubleClick={onNodeDoubleClick}
        onPaneClick={onPaneClick}
        onNodeMouseEnter={onNodeMouseEnter}
        onNodeMouseLeave={hideTip}
        onNodeDragStart={(e, node) => { hideTip(); dragStart(node.id); }}
        onNodeDrag={(e, node) => drag(node.id, node.position)}
        onNodeDragStop={(e, node) => dragStop(node.id)}
        onMove={(e, viewport) => { hideTip(); setLabelsOn(viewport.zoom > 0.45); }}
        minZoom={0.04}
        maxZoom={3}
        fitView
        zoomOnDoubleClick={false}
        nodesConnectable={false}
        elementsSelectable={false}
      />
      {tip && <NodeTooltip uid={tip.uid} x={tip.x} y={tip.y}
        wrapW={wrapRef.current?.clientWidth} />}
    </div>
  );
}
