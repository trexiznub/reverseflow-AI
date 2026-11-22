"""Return-reason classification and sentiment analysis.

* Reason classifier: TF-IDF (word 1-2 grams + char 3-5 grams) + multinomial
  logistic regression, trained on returns whose reason was verified at inspection.
* Sentiment: TF-IDF + logistic regression trained on review star ratings
  (>=4 positive, <=2 negative). Score in [-1, 1].

Sentence-Transformers would be a drop-in upgrade for the vectoriser; TF-IDF is
used so the demo runs offline on a laptop with no model downloads.
Metrics are computed on a stratified 20% hold-out.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import FeatureUnion, Pipeline
from sqlalchemy import text, update
from sqlalchemy.orm import Session

from .. import models as m

_reason_model: Pipeline | None = None
_sentiment_model: Pipeline | None = None
_metrics: dict = {}


def _vectoriser():
    return FeatureUnion([
        ("w", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)),
        ("c", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=3, sublinear_tf=True, max_features=40000)),
    ])


def train(db: Session) -> dict:
    global _reason_model, _sentiment_model, _metrics
    r = pd.read_sql(text("SELECT id, reason_text, verified_reason FROM returns WHERE verified_reason IS NOT NULL"), db.bind)
    X_tr, X_te, y_tr, y_te = train_test_split(r.reason_text, r.verified_reason, test_size=0.2, random_state=11, stratify=r.verified_reason)
    model = Pipeline([("v", _vectoriser()), ("clf", LogisticRegression(max_iter=2000, C=4.0))]).fit(X_tr, y_tr)
    pred = model.predict(X_te)
    labels = sorted(r.verified_reason.unique())
    cm = confusion_matrix(y_te, pred, labels=labels)
    per_class = f1_score(y_te, pred, labels=labels, average=None)
    reason_metrics = {
        "accuracy": round(float(accuracy_score(y_te, pred)), 4),
        "macro_f1": round(float(f1_score(y_te, pred, average="macro")), 4),
        "train_n": int(len(X_tr)), "test_n": int(len(X_te)), "labels": labels,
        "per_class_f1": {l: round(float(f), 3) for l, f in zip(labels, per_class)},
        "confusion": cm.tolist(),
    }
    _reason_model = Pipeline([("v", _vectoriser()), ("clf", LogisticRegression(max_iter=2000, C=4.0))]).fit(r.reason_text, r.verified_reason)

    rv = pd.read_sql(text("SELECT id, text, rating FROM reviews"), db.bind)
    lab = rv[rv.rating != 3].assign(y=lambda d: (d.rating >= 4).astype(int))
    a, b, ya, yb = train_test_split(lab.text, lab.y, test_size=0.2, random_state=11, stratify=lab.y)
    sm = Pipeline([("v", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)), ("clf", LogisticRegression(max_iter=1000))]).fit(a, ya)
    sp = sm.predict(b)
    sentiment_metrics = {"accuracy": round(float(accuracy_score(yb, sp)), 4), "f1": round(float(f1_score(yb, sp)), 4),
                         "train_n": int(len(a)), "test_n": int(len(b))}
    _sentiment_model = Pipeline([("v", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)), ("clf", LogisticRegression(max_iter=1000))]).fit(lab.text, lab.y)
    _metrics = {"reason_classifier": reason_metrics, "sentiment": sentiment_metrics,
                "method": {"reason": "TF-IDF word+char n-grams, multinomial logistic regression", "sentiment": "TF-IDF + logistic regression on star ratings"}}
    return _metrics


def ensure_trained(db: Session):
    if _reason_model is None or _sentiment_model is None:
        train(db)


def metrics() -> dict:
    return _metrics


def classify(texts: list[str]) -> list[tuple[str, float]]:
    proba = _reason_model.predict_proba(texts)
    classes = _reason_model.classes_
    idx = proba.argmax(axis=1)
    return [(str(classes[i]), float(proba[k, i])) for k, i in enumerate(idx)]


def top_terms(reason: str, n: int = 8) -> list[str]:
    """Most indicative word features for a reason (explainability)."""
    vec = _reason_model.named_steps["v"].transformer_list[0][1]
    clf = _reason_model.named_steps["clf"]
    k = list(clf.classes_).index(reason)
    n_words = len(vec.vocabulary_)
    coefs = clf.coef_[k][:n_words]
    vocab = np.array(vec.get_feature_names_out())
    return vocab[np.argsort(coefs)[::-1][:n]].tolist()


def sentiment(texts: list[str]) -> list[float]:
    p = _sentiment_model.predict_proba(texts)[:, 1]
    return [round(float(2 * x - 1), 3) for x in p]


def score_all(db: Session, only_missing: bool = True) -> int:
    """Write predicted_reason / confidence / sentiment for returns and reviews."""
    ensure_trained(db)
    q = "SELECT id, reason_text FROM returns" + (" WHERE predicted_reason IS NULL" if only_missing else "")
    r = pd.read_sql(text(q), db.bind)
    if len(r):
        preds = classify(r.reason_text.tolist())
        sents = sentiment(r.reason_text.tolist())
        rows = [{"id": i, "predicted_reason": p, "reason_confidence": round(c, 3), "sentiment": s}
                for i, (p, c), s in zip(r.id, preds, sents)]
        db.execute(update(m.Return), rows)
    q2 = "SELECT id, text FROM reviews" + (" WHERE sentiment IS NULL" if only_missing else "")
    rv = pd.read_sql(text(q2), db.bind)
    if len(rv):
        s = sentiment(rv.text.tolist())
        db.execute(update(m.Review), [{"id": int(i), "sentiment": v} for i, v in zip(rv.id, s)])
    db.commit()
    return len(r)
