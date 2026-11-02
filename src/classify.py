"""Classify: intent and urgency with a probability, plus P(safe to auto-respond) (A3).

Logistic regression on all-MiniLM-L6-v2 embeddings, trained at start-up on the dev tickets.
Grouped 5-fold CV (no message text shared between folds), dev set: intent 95% accuracy / 95% macro
precision; urgency 47% (identical texts carry different urgency labels, so text cannot do better).
Local and deterministic, so it keeps working when the model provider is down.

The answer-likelihood model reads more than the text (auto_features): the topic probabilities, the best
search score and hit count, and the channel; a Platt layer, fitted on out-of-fold scores, turns its score
into a calibrated probability. query() builds the search for what an agent sees on an escalation: the
ticket plus, when the topic is predicted with 90%+ confidence, that topic's usual article title.
Out-of-fold figures on dev (evaluation/routing_threshold.py) sit beside each piece below. Topic inputs on
training rows are themselves out-of-fold, so nothing learns from topic predictions made on tickets the
topic model trained on.
"""
import hashlib
import json
import os
from collections import Counter, defaultdict
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
# A confidently predicted topic (>= 0.9) shapes what the agent sees on an escalation: its usual article's title
# is added to the search query (out-of-fold on dev, right article found for non-fluent tickets 88.5% -> 96.6%,
# fluent 95.6% -> 97.4%), and if that search still misses the article it is suggested directly. Answers are
# drafted from the plain search: drafting from the expanded one released fewer answers (evaluation/passage_compare.py).
TOPIC_ARTICLE_MIN = 0.9
# Regularisation per target, picked for calibration (evaluation/routing_threshold.py): intent at C=10 was
# underconfident (calibration error 0.185) and at C=1000 is 0.025; urgency at C=10 was overconfident (0.182),
# at C=1 is 0.037; answer-likelihood with auto_features is 0.067 at C=3 vs 0.080 at C=10, and 0.044 with
# the Platt layer (fit_auto), which at 0.85 also answers 105 of 500 dev tickets at a 12.4% wrong share
# (the text-only model: 92 at 13.0%).
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


def topic_articles(tickets) -> dict:
    """Each topic's most-cited article in the training labels."""
    counts = defaultdict(Counter)
    for t in tickets:
        counts[t.raw["labels"]["intent"]].update(t.raw["labels"]["expected_doc_ids"])
    return {k: c.most_common(1)[0][0] for k, c in counts.items() if c}


def oof_intent_probs(X, y_intent, groups):
    """Topic probabilities for training rows from models that did not see their wording."""
    return cross_val_predict(make_model("intent"), X, y_intent, cv=GroupKFold(n_splits=5), groups=groups,
                             method="predict_proba")


def expand_query(text: str, intent_probs_row, classes, articles: dict, titles: dict) -> str:
    """The ticket text, plus the predicted topic's usual article title when the topic is confident."""
    i = int(np.argmax(intent_probs_row))
    article = articles.get(classes[i]) if intent_probs_row[i] >= TOPIC_ARTICLE_MIN else None
    return f"{text}\n{titles[article]}" if article in titles else text


def fit_auto(F, y, groups):
    """Answer-likelihood model plus a Platt layer fitted on its out-of-fold scores (no row scores itself)."""
    oof = cross_val_predict(make_model("auto"), F, y, cv=GroupKFold(n_splits=5), groups=groups,
                            method="decision_function")
    return make_model("auto").fit(F, y), LogisticRegression().fit(np.asarray(oof).reshape(-1, 1), y)


def auto_prob(model, platt, F):
    return platt.predict_proba(model.decision_function(F).reshape(-1, 1))[:, 1]


class Classifier:
    def __init__(self, retriever, train_path: str = TRAIN_PATH):
        raw = Path(train_path).read_bytes()
        self.version = hashlib.sha256(raw).hexdigest()[:12]
        tickets = [normalize(t) for t in json.loads(raw)]
        self.embedder = retriever.model
        X = self.embed([t.text for t in tickets])
        y = {k: [targets(t)[k] for t in tickets] for k in ("intent", "urgency", "auto")}
        groups = [t.body for t in tickets]
        self.models = {k: make_model(k).fit(X, y[k]) for k in ("intent", "urgency")}
        self.topic_article = topic_articles(tickets)
        self.titles = {c["doc_id"]: c["title"] for c in retriever.chunks.values()}
        # The answer-likelihood model reads the PLAIN search score: on dev, feeding it the expanded search instead
        # raised calibration error to 0.058 and the wrong share at 0.85 to 15.5%, because the topic title lifts
        # scores for unanswerable tickets too. The expanded search (query) supplies passages only.
        hits = [retriever.search(t.text) for t in tickets]
        F = auto_features(X, oof_intent_probs(X, y["intent"], groups), hits, [t.channel for t in tickets])
        self.auto, self.platt = fit_auto(F, y["auto"], groups)

    def embed(self, texts):
        return self.embedder.encode(texts, normalize_embeddings=True)

    def query(self, ticket: Ticket) -> str:
        """What to search for: see expand_query."""
        if not ticket.text:
            return ""
        p = self.models["intent"].predict_proba(self.embed([ticket.text]))[0]
        return expand_query(ticket.text, p, self.models["intent"].classes_, self.topic_article, self.titles)

    def classify(self, ticket: Ticket, hits: list[dict]) -> dict:
        """`hits` = the plain search on the ticket text (what the answer-likelihood model was trained on)."""
        if not ticket.text:
            return {"fallback": True, "p_auto": 0.0, "topic_article": None,
                    **{k: {"value": v, "confidence": 0.0, "alternatives": []} for k, v in FALLBACK.items()}}
        x = self.embed([ticket.text])
        probs = {k: self.models[k].predict_proba(x) for k in ("intent", "urgency")}
        f = auto_features(x, probs["intent"], [hits], [ticket.channel])
        out = {"fallback": False, "p_auto": round(float(auto_prob(self.auto, self.platt, f)[0]), 4)}
        for k in ("intent", "urgency"):
            ranked = sorted(zip(self.models[k].classes_, probs[k][0]), key=lambda p: -p[1])[:3]
            top = [{"value": str(c), "confidence": round(float(p), 4)} for c, p in ranked]
            out[k] = {**top[0], "alternatives": top[1:]}
        confident = out["intent"]["confidence"] >= TOPIC_ARTICLE_MIN
        out["topic_article"] = self.topic_article.get(out["intent"]["value"]) if confident else None
        return out
