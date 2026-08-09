# graph-ui — the Nectar mind-graph island

The interactive mind graph on the `/ui` page. React Flow renders and handles
interaction (pan/zoom/drag/hover-tooltips); **d3-force** computes the layout
(`forceCollide` keeps nodes and their labels from overlapping). The simulation only
runs while the layout settles — there is no permanent render loop.

Only the graph pane is React: the rest of `index.html` stays vanilla JS and talks to
the island through the imperative `window.NectarGraph` API (see `src/main.jsx` for the
surface, `src/store.js` for the model/behavior, `src/GraphApp.jsx` for rendering).

## Build

```sh
npm install
npm run build   # → server/src/static/assets/graph.js + graph.css
```

The bundle is fully self-contained (React included, no CDN) and **committed to the
repo**, so the Docker image build needs no Node — `COPY server/src` picks it up and
FastAPI serves it at `/ui/assets/`. Rebuild + commit the bundle whenever you change
`src/`.
