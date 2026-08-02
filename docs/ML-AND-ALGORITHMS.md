# Models & Algorithms

Everything here runs **locally** — two small ONNX models (an embedder and a cross-encoder) plus
pure-Python arithmetic. No cloud LLM is involved in retrieval, ranking, or maintenance. All the
constants below are the defaults in `server/src/components/config.py` and are visible read-only in
the GUI (**Beheer → Instellingen**).

## 0. The two local models

| Role | Model | Default |
|---|---|---|
| Embeddings | fastembed `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 384-dim, multilingual (incl. Dutch), CPU |
| Reranking | fastembed `TextCrossEncoder` `Xenova/ms-marco-MiniLM-L-6-v2` | cross-encoder, CPU |

Embeddings are configurable (`EMBEDDINGS_*`) and can point at any OpenAI-compatible endpoint; the
default keeps everything on-box. Changing the model requires a **reindex** (see OPERATIONS) because
old and new vectors are not comparable.

---

## 1. Hybrid retrieval + Reciprocal Rank Fusion (RRF)

A query is answered by **two** independent retrievers and their rankings are fused:

- **Dense** — cosine similarity in the `knowledge_embedding` vector index (semantic meaning).
- **Sparse** — BM25 over the `knowledge_fulltext` index (exact tokens: symbols, error codes, paths).

Fusion uses **Reciprocal Rank Fusion**, which combines *ranks* (not scores, so the two scales never
need calibrating):

$$\text{RRF}(d) = \sum_{r \in \text{retrievers}} \frac{1}{k + \text{rank}_r(d)} \qquad k = 60$$

Why hybrid: pure vectors miss literal tokens (a UUID, `NB_MERGE_LATEST`, an env var); pure BM25
misses paraphrases. RRF with `k=60` is the well-established default (Cormack et al.) and needs no
per-corpus tuning.

---

## 2. Multi-hop expansion

After fusion, the top `MULTIHOP_ANCHORS = 5` hits pull in their **direct graph neighbours** (1 hop
along `CONTAINS`/`RELATES`) as extra candidates, weighted down by `MULTIHOP_BASE = 0.4`. This
surfaces knowledge that is *related* to the answer but doesn't itself match the query text — the
value a graph adds over a flat vector store.

---

## 3. Cross-encoder reranking

The fused candidate set (top `RERANK_TOP_K = 40`) is re-scored by a **cross-encoder**: unlike the
bi-encoder embedder (which encodes query and document separately), the cross-encoder reads the
`(query, document)` pair jointly and produces a far sharper relevance score. This is a classic
two-stage "retrieve cheap, rerank precise" pipeline. Toggle with `RERANK_ENABLED`; it degrades
gracefully (falls back to fusion order) if the model can't load.

---

## 4. The ranking function

Each surviving candidate gets a final score as a **dot product of features and weights**:

$$\text{score}(d) = \sum_i w_i \cdot f_i(d)$$

`FEATURE_KEYS = (sim, freshness, anchor, decision, learning, tag, superseded, bloom, importance,
worth, pagerank)`. The default weights reproduce the hand-tuned blend below; a **learned** ranker
(§8) replaces them once enough feedback exists.

| Feature | Meaning | Default weight / source |
|---|---|---|
| `sim` | fused semantic+lexical relevance | `SEMANTIC_WEIGHT 0.7` |
| `freshness` | time-decay (below) | `FRESHNESS_WEIGHT 0.3` |
| `anchor` | in the active project's topic subtree | `ANCHOR_BOOST 0.15` |
| `decision` | is a `decision` node | `DECISION_BOOST 0.1` |
| `learning` | is a `learning` node | `LEARNING_BOOST 0.3` |
| `tag` | query tag match | `TAG_BOOST 0.12` |
| `bloom` | lifecycle phase | `BLOOM_BOOST` (below) |
| `importance` | manual pin | `IMPORTANCE_WEIGHT 0.3` |
| `worth` | causal "did it help?" | `OUTCOME_WEIGHT 0.3` |
| `pagerank` | structural centrality | `PAGERANK_WEIGHT 0.1` |
| `superseded` | replaced by a newer version | `SUPERSEDE_PENALTY 0.6` (negative) |

### 4a. Freshness / decay

Relevance decays with age on an **exponential half-life** curve; every recall "touches" a memory
(resets its clock), so heavily-used knowledge never rots:

$$\text{freshness}(d) = 0.5^{\;\Delta t \,/\, H}$$

where $\Delta t$ is days since last use and $H$ is the half-life. Ordinary memories use
`FRESHNESS_HALF_LIFE_DAYS = 30`; **decisions and conventions** decay far slower with
`STABLE_HALF_LIFE_DAYS = 365` (they stay true longer). A per-node override is possible.

### 4b. Bloom lifecycle weighting

Knowledge matures **captured → validated → mature → deprecated**; the phase shifts ranking:

```
BLOOM_BOOST = { mature: +0.2, validated: +0.1, captured: -0.05, deprecated: -0.6 }
```

### 4c. Importance pin

A human/agent can pin importance $\in [0,1]$; the shift is centred so "important" rises and
"trivial" sinks:

$$\Delta = \text{IMPORTANCE\_WEIGHT} \cdot (\text{importance} - 0.5)$$

### 4d. Memory Worth (causal outcome)

Agents report whether a recalled memory **helped** (`hive_feedback`). Worth is the net signal, only
trusted after `OUTCOME_MIN_SAMPLES = 3` reports:

$$\text{worth}(d) = \frac{\text{pos} - \text{neg}}{\text{pos} + \text{neg}} \quad(\text{if } \text{pos}+\text{neg} \ge 3)$$

This is a *causal* signal (did using it lead to success?), distinct from mere frequency.

### 4e. Supersession penalty

When a newer memory supersedes an older one (`SUPERSEDES` edge), the old node's score is multiplied
down by `SUPERSEDE_PENALTY = 0.6`. It stays findable (history/audit) but the current truth wins.

---

## 5. Anti "context-rot" injection

More context is not better — long, noisy context measurably degrades model output. So recall injects
at most `RECALL_MAX_MEMORIES = 6`, drops anything below `RECALL_REL_FLOOR = 0.45` of the top hit, and
places the strongest items at the **ends** of the block (models attend most to the beginning and end
— the "lost in the middle" effect).

---

## 6. Structural importance — PageRank (in-app)

Well-connected knowledge is often more foundational. Nectar runs **PageRank in pure Python** over
the memory graph (no GDS plugin needed) and adds `PAGERANK_WEIGHT = 0.1 × pagerank` to the score.
Recomputed on demand by the *PageRank* scan.

$$PR(d) = \frac{1-\alpha}{N} + \alpha \sum_{e \to d} \frac{PR(e)}{\text{outdeg}(e)} \qquad \alpha = 0.85$$

---

## 7. Link prediction (relationship suggestions)

To keep the graph connected, a scan proposes `RELATES` edges between memories that are probably
related but not yet linked, scoring candidate pairs by **Adamic–Adar × cosine**:

$$\text{score}(u,v) = \Big(\sum_{w \in N(u)\cap N(v)} \frac{1}{\log |N(w)|}\Big) \times \cos(u, v)$$

A pair is only proposed if `cosine ≥ LINKPRED_MIN_SIM (0.55)` **and** it shares
`≥ LINKPRED_MIN_COMMON (2)` neighbours; top `LINKPRED_TOP (15)` become suggestion-Pollen — never
auto-linked.

---

## 8. Learning-to-rank (LTR)

Once ≥ `LTR_MIN_EXAMPLES = 40` labelled examples exist (from impressions + `hive_feedback`), a
**pure-Python logistic-regression** ranker is trained and *replaces* the hand-tuned weights of §4.
It learns the weight vector $\mathbf{w}$ by minimising log-loss with L2 regularisation:

$$\hat{y} = \sigma(\mathbf{w}\cdot\mathbf{f}), \qquad \mathcal{L} = -\big[y\log\hat{y} + (1-y)\log(1-\hat{y})\big] + \lambda\lVert\mathbf{w}\rVert^2$$

Trained by gradient descent (400 epochs, lr 0.3, λ 0.001). Cold-start (too few examples) keeps the
defaults. Retrain from **Beheer → Onderhoud → Ranker trainen**. Weak/biased feedback can make a
trained ranker worse than the defaults — retraining is cheap and reversible.

---

## 9. Contradiction detection (NLI, swarm-adjudicated)

fastembed has no local NLI model and the server stays LLM-free, so detection is split:

1. **Deterministic candidate detection** — a scan finds memory pairs whose Neo4j cosine score is in
   the band `[CONTRA_MIN_SIM 0.82, DEDUP_SIMILARITY_THRESHOLD 0.92)`: alike enough to be about the
   same subject, not so alike they're duplicates. Top `CONTRA_TOP = 12` per run.
2. **Swarm judgement** — each pair becomes a `contradiction_check` **think-Pollen**; a *different*
   agent decides *compatible* (close) or *contradiction* → supersede the outdated one.

The high floor (0.82) is deliberate: a real truth-conflict is about the *same* thing, so it sits
just under the dedup band. A lower floor floods the Swarm with unrelated pairs (a first live run at
0.70 opened 12 near-unrelated pairs).

> **Neo4j vector score note.** Neo4j's cosine index returns `score = (cosine + 1) / 2`, so a raw
> cosine of 0.64 reads as 0.82. Thresholds above are in Neo4j-score units.

---

## 10. Where each algorithm lives

| Algorithm | Code |
|---|---|
| Hybrid retrieval + RRF + features | `services/search_service.py` |
| Reranker | `services/reranker.py` |
| Write-gate + dedup | `services/memory_service.py` |
| PageRank · link prediction · scans | `services/curation_service.py` |
| Learning-to-rank | `services/ltr_service.py` |
| Contradiction · think-Pollen · consensus | `services/governance_service.py`, `repository/governance_repo.py` |
| Tuning constants | `components/config.py` |
