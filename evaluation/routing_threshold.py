"""Sweep the routing threshold on dev tickets and check confidence calibration.

Out-of-fold predictions from grouped 5-fold CV (identical message texts never straddle folds), so each
ticket is scored by a model that has not seen its wording. Each candidate threshold is run through route().

Usage: python -m evaluation.routing_threshold [--tickets PATH]
"""
import argparse
import json

import numpy as np
from sklearn.model_selection import GroupKFold, cross_val_predict

from src.classify import (TOPIC_ARTICLE_MIN, auto_features, auto_prob, expand_query, fit_auto, make_model,
                          oof_intent_probs, targets, topic_articles)
from src.ingest import normalize
from src.retrieve import ROOT, Retriever
from src.route import route


def ece(conf, correct, bins=10):
    """Expected calibration error: average gap between stated confidence and observed accuracy."""
    conf, correct = np.asarray(conf), np.asarray(correct, dtype=float)
    idx = np.minimum((conf * bins).astype(int), bins - 1)
    return sum(abs(conf[idx == b].mean() - correct[idx == b].mean()) * (idx == b).mean()
               for b in range(bins) if (idx == b).any())


def out_of_fold(tickets, r: Retriever) -> dict:
    """Per-ticket predictions from models that never saw that ticket's wording, plus its search hits.
    Everything Classifier builds (expanded search, answer-likelihood model, Platt layer, topic articles)
    is rebuilt here from each fold's training rows only."""
    X = r.model.encode([t.text for t in tickets], normalize_embeddings=True)
    groups, cv = np.array([t.body for t in tickets]), GroupKFold(n_splits=5)
    y = {k: np.array([targets(t)[k] for t in tickets]) for k in ("intent", "urgency", "auto")}
    channels, titles = np.array([t.channel for t in tickets]), {c["doc_id"]: c["title"] for c in r.chunks.values()}
    plain = [r.search(t.text) for t in tickets]  # routing, drafting and the answer-likelihood model
    oof = {k: cross_val_predict(make_model(k), X, y[k], cv=cv, groups=groups, method="predict_proba")
           for k in ("intent", "urgency")}
    classes = np.unique(y["intent"])
    p_auto, topic, hits = np.zeros(len(tickets)), [None] * len(tickets), [None] * len(tickets)
    for tr, te in cv.split(X, y["auto"], groups):
        articles = topic_articles([tickets[i] for i in tr])
        F = auto_features(X[tr], oof_intent_probs(X[tr], y["intent"][tr], groups[tr]), [plain[i] for i in tr],
                          channels[tr])
        model, platt = fit_auto(F, y["auto"][tr], groups[tr])
        intent_te = make_model("intent").fit(X[tr], y["intent"][tr]).predict_proba(X[te])
        for j, i in enumerate(te):
            hits[i] = r.search(expand_query(tickets[i].text, intent_te[j], classes, articles, titles))  # agent
            if intent_te[j].max() >= TOPIC_ARTICLE_MIN:
                topic[i] = articles.get(classes[intent_te[j].argmax()])
        p_auto[te] = auto_prob(model, platt, auto_features(X[te], intent_te, [plain[i] for i in te], channels[te]))
    pred = {k: np.unique(y[k])[oof[k].argmax(1)] for k in ("intent", "urgency")}
    return {"y": y, "oof": oof, "intent": pred["intent"], "urgency": pred["urgency"],
            "iconf": oof["intent"].max(1), "p_auto": p_auto, "hits": plain, "agent_hits": hits, "topic_article": topic}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickets", default=ROOT / "data/development_tickets.json")
    tickets = [normalize(t) for t in json.loads(open(ap.parse_args().tickets).read())]
    o = out_of_fold(tickets, Retriever())
    y, oof = o["y"], o["oof"]
    for k in ("intent", "urgency"):
        print(f"{k:8s} accuracy {(o[k] == y[k]).mean():.0%}, calibration error "
              f"{ece(oof[k].max(1), o[k] == y[k]):.3f} (target <= 0.05)")
    intent, iconf, p_auto, hits = o["intent"], o["iconf"], o["p_auto"], o["hits"]
    print(f"auto-respond calibration error {ece(p_auto, y['auto']):.3f}\n")
    labels = [t.raw["labels"] for t in tickets]
    print("threshold  auto%  auto&should-escalate  auto&must-not  escalated&could-auto")
    for th in [0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9]:
        acts = [route({"fallback": False, "p_auto": p, "intent": {"value": i, "confidence": c}}, h, threshold=th)
                ["action"] for p, i, c, h in zip(p_auto, intent, iconf, hits)]
        auto = np.array([a == "auto_respond" for a in acts])
        should_esc = np.array([lab["expected_route"] == "escalate" for lab in labels])
        must = np.array([lab["must_not_auto_respond"] for lab in labels])
        print(f"{th:9.2f}  {auto.mean():5.0%}  {(auto & should_esc).sum():20d}  {(auto & must).sum():13d}  "
              f"{(~auto & ~should_esc).sum():20d}")


if __name__ == "__main__":
    main()
