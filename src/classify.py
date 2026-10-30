"""Classify: intent and urgency with a probability, plus P(safe to auto-respond) (A3).

Logistic regression on all-MiniLM-L6-v2 embeddings, trained at start-up on the dev tickets.
Grouped 5-fold CV (no message text shared between folds), dev set: intent 94% accuracy / 95% macro
precision; urgency 47% (identical texts carry different urgency labels, so text cannot do better);
auto-respond AUC 0.76. Local and deterministic, so it keeps working when the model provider is down.
"""
import hashlib
import json
import os
from pathlib import Path

from sklearn.linear_model import LogisticRegression

from src.ingest import Ticket, normalize

ROOT = Path(__file__).resolve().parent.parent
TRAIN_PATH = os.getenv("TRAIN_PATH", str(ROOT / "data/development_tickets.json"))
FALLBACK = {"intent": "unclear_request", "urgency": "medium"}
# Regularisation per target, picked for calibration (evaluation/routing_threshold.py): intent at C=10 was
# underconfident (calibration error 0.185) and at C=1000 is 0.025; urgency at C=10 was overconfident (0.182),
# at C=1 is 0.037; auto-respond is best at C=10 (0.067).
C = {"intent": 1000, "urgency": 1, "auto": 10}


def make_model(target: str):
    return LogisticRegression(C=C[target], max_iter=5000)


def targets(t: Ticket) -> dict:
    lab = t.raw["labels"]
    return {"intent": lab["intent"], "urgency": lab["urgency"], "auto": lab["expected_route"] == "auto_respond"}


class Classifier:
    def __init__(self, embedder, train_path: str = TRAIN_PATH):
        raw = Path(train_path).read_bytes()
        self.version = hashlib.sha256(raw).hexdigest()[:12]
        tickets = [normalize(t) for t in json.loads(raw)]
        self.embedder = embedder
        X = self.embed([t.text for t in tickets])
        self.models = {k: make_model(k).fit(X, [targets(t)[k] for t in tickets]) for k in ("intent", "urgency", "auto")}

    def embed(self, texts):
        return self.embedder.encode(texts, normalize_embeddings=True)

    def classify(self, ticket: Ticket) -> dict:
        if not ticket.text:
            return {"fallback": True, "p_auto": 0.0,
                    **{k: {"value": v, "confidence": 0.0, "alternatives": []} for k, v in FALLBACK.items()}}
        x = self.embed([ticket.text])
        out = {"fallback": False, "p_auto": round(float(self.models["auto"].predict_proba(x)[0][1]), 4)}
        for k in ("intent", "urgency"):
            m = self.models[k]
            ranked = sorted(zip(m.classes_, m.predict_proba(x)[0]), key=lambda p: -p[1])[:3]
            top = [{"value": str(c), "confidence": round(float(p), 4)} for c, p in ranked]
            out[k] = {**top[0], "alternatives": top[1:]}
        return out
