"""Classify: intent and urgency with a probability, plus P(safe to auto-respond) (A3).

Logistic regression on all-MiniLM-L6-v2 embeddings, trained at start-up on the dev tickets.
Grouped 5-fold CV (no message text shared between folds), dev set: intent 95% accuracy / 95% macro
precision; urgency 47% (identical texts carry different urgency labels, so text cannot do better).
Local and deterministic, so it keeps working when the model provider is down.

The answer-likelihood model reads more than the text (auto_features): the topic probabilities, the best
search score and hit count, and the channel. Out-of-fold on dev (evaluation/routing_threshold.py) this
raised AUC from 0.765 to 0.805; at the 0.85 threshold, auto-answers rose from 92 to 119 of 500 with the
wrong share at 14.3% (was 13.0%) and no must-escalate ticket answered. Calibration error is unchanged at
0.067. Its topic inputs on training rows are themselves out-of-fold, so it never learns from topic
predictions made on tickets the topic model trained on.
"""
import hashlib
import json
import os
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold, cross_val_predict

from src.ingest import Ticket, normalize
from src.retrieve import TOP_K

ROOT = Path(__file__).resolve().parent.parent
TRAIN_PATH = os.getenv("TRAIN_PATH", str(ROOT / "data/development_tickets.json"))
FALLBACK = {"intent": "unclear_request", "urgency": "medium"}
CHANNELS = ("email", "chat", "docs_comment", "forum")
# Regularisation per target, picked for calibration (evaluation/routing_threshold.py): intent at C=10 was
# underconfident (calibration error 0.185) and at C=1000 is 0.025; urgency at C=10 was overconfident (0.182),
# at C=1 is 0.037; answer-likelihood with auto_features is 0.067 at C=3 vs 0.080 at C=10.
C = {"intent": 1000, "urgency": 1, "auto": 3}


def make_model(target: str):
    return LogisticRegression(C=C[target], max_iter=5000)


def targets(t: Ticket) -> dict:
    lab = t.raw["labels"]
    return {"intent": lab["intent"], "urgency": lab["urgency"], "auto": lab["expected_route"] == "auto_respond"}


def auto_features(X, intent_probs, hits: list[list[dict]], channels: list[str]):
    """Answer-likelihood inputs: embedding, topic probabilities, best search score and hit count, channel."""
    search = np.array([[h[0]["score"] if h else 0.0, len(h) / TOP_K] for h in hits])
    chan = np.array([[c == k for k in CHANNELS] for c in channels], dtype=float)
    return np.hstack([X, intent_probs, search, chan])


def oof_intent_probs(X, y_intent, groups):
    """Topic probabilities for training rows from models that did not see their wording."""
    return cross_val_predict(make_model("intent"), X, y_intent, cv=GroupKFold(n_splits=5), groups=groups,
                             method="predict_proba")


class Classifier:
    def __init__(self, retriever, train_path: str = TRAIN_PATH):
        raw = Path(train_path).read_bytes()
        self.version = hashlib.sha256(raw).hexdigest()[:12]
        tickets = [normalize(t) for t in json.loads(raw)]
        self.embedder = retriever.model
        X = self.embed([t.text for t in tickets])
        y = {k: [targets(t)[k] for t in tickets] for k in ("intent", "urgency", "auto")}
        self.models = {k: make_model(k).fit(X, y[k]) for k in ("intent", "urgency")}
        F = auto_features(X, oof_intent_probs(X, y["intent"], [t.body for t in tickets]),
                          [retriever.search(t.text) for t in tickets], [t.channel for t in tickets])
        self.models["auto"] = make_model("auto").fit(F, y["auto"])

    def embed(self, texts):
        return self.embedder.encode(texts, normalize_embeddings=True)

    def classify(self, ticket: Ticket, hits: list[dict]) -> dict:
        if not ticket.text:
            return {"fallback": True, "p_auto": 0.0,
                    **{k: {"value": v, "confidence": 0.0, "alternatives": []} for k, v in FALLBACK.items()}}
        x = self.embed([ticket.text])
        probs = {k: self.models[k].predict_proba(x) for k in ("intent", "urgency")}
        f = auto_features(x, probs["intent"], [hits], [ticket.channel])
        out = {"fallback": False, "p_auto": round(float(self.models["auto"].predict_proba(f)[0][1]), 4)}
        for k in ("intent", "urgency"):
            ranked = sorted(zip(self.models[k].classes_, probs[k][0]), key=lambda p: -p[1])[:3]
            top = [{"value": str(c), "confidence": round(float(p), 4)} for c, p in ranked]
            out[k] = {**top[0], "alternatives": top[1:]}
        return out
