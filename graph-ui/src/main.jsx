/**
 * Entry point: bundles to window.NectarGraph (IIFE), the imperative API the vanilla
 * index.html talks to. All graph state/behavior lives in store.js; React Flow renders.
 */
import { createRoot } from "react-dom/client";
import "@xyflow/react/dist/style.css";
import "./graph.css";
import GraphApp from "./GraphApp.jsx";
import * as ops from "./store.js";

let root = null;

export function mount(el, bridge) {
  ops.init(bridge);
  root = createRoot(el);
  root.render(<GraphApp />);
}

export const setRoot = ops.setRoot;
export const setProject = ops.setProject;
export const expand = ops.expand;
export const select = ops.select;
export const jumpTo = ops.jumpTo;
export const remove = ops.removeNode;
export const clear = ops.clearAll;
export const setTypeFilter = ops.setTypeFilter;
export const setSciFi = ops.setSciFi;
export const deselect = ops.deselect;
export const zoomIn = ops.zoomIn;
export const zoomOut = ops.zoomOut;
export const fit = ops.fit;
export const getSelected = ops.getSelected;
