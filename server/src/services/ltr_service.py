"""Learning-to-rank: train a small local logistic-regression ranker from the labeled recall
examples that hive_feedback produces, and store its weights on the org so search() uses them
instead of the hand-tuned blend. Pure Python — no torch, no sklearn, keeps Nectar local-only.
Cold-start is handled in search_service._ranker: until a model is trained, the hand-tuned
weights are used."""
from __future__ import annotations

import math
import time

from neo4j import Session

from src.authentication.deps import AuthedAccount, assert_role
from src.components.config import get_settings
from src.repository import audit_repo, graph_repo
from src.services.search_service import FEATURE_KEYS


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))


def train(session: Session, account: AuthedAccount) -> dict:
    """Fit weights that predict 'did this recalled memory help' from its ranking features.
    Needs >= LTR_MIN_EXAMPLES labeled examples; otherwise it reports how many more are needed
    and leaves the hand-tuned weights in place. Maintainer."""
    assert_role(account, "maintainer", "Training the ranker")
    settings = get_settings()
    examples = graph_repo.ranker_examples(session, account.org_uid)
    n = len(examples)
    if n < settings.LTR_MIN_EXAMPLES:
        return {"trained": False, "examples": n, "need": settings.LTR_MIN_EXAMPLES,
                "note": f"Not enough feedback yet ({n}/{settings.LTR_MIN_EXAMPLES}). The hand-tuned "
                        "weights stay in use until then; feedback keeps accruing."}

    keys = list(FEATURE_KEYS)
    d = len(keys)
    X = [[ex["features"].get(k, 0.0) for k in keys] for ex in examples]
    y = [1 if ex["label"] else 0 for ex in examples]

    w = [0.0] * d
    b = 0.0
    lr, reg, epochs = 0.3, 0.001, 400
    for _ in range(epochs):
        gw = [0.0] * d
        gb = 0.0
        for i in range(n):
            p = _sigmoid(sum(w[j] * X[i][j] for j in range(d)) + b)
            err = p - y[i]
            for j in range(d):
                gw[j] += err * X[i][j]
            gb += err
        for j in range(d):
            w[j] -= lr * (gw[j] / n + reg * w[j])
        b -= lr * gb / n

    weights = {keys[j]: round(w[j], 5) for j in range(d)}
    payload = {"weights": weights, "bias": round(b, 5), "examples": n,
               "positives": sum(y), "trained_at": int(time.time())}
    graph_repo.set_ranker_weights(session, account.org_uid, payload)
    audit_repo.log(session, account.org_uid, account.uid, "train_ranker", account.org_uid,
                   {"examples": n, "positives": sum(y)})
    return {"trained": True, "examples": n, "positives": sum(y), "weights": weights}
