# -*- coding: utf-8 -*-
"""ml/evaluate_up_hit_rate_2025.py

사용자 정의(B): 실제 거래(익일 수익>0) 기준 '상승 적중률' 계산

정의
- 모델이 '상승'으로 판단한 종목: 예측 클래스(argmax) ∈ {1..6}
  (학습 설정상 class0은 <2% 구간, class1~6은 2% 이상 구간)
- 실제 성과(익일): next_close / today_close - 1
- 적중(hit): 익일 수익률 > 0

출력
- 전체 상승 적중률(Precision): P(익일수익>0 | 예측상승)
- 예측상승 표본 수, 일평균 예측상승 종목 수
- 클래스별(1~6) 적중률/표본 수
- prob_up(=class1~6 합) 기준 임계값별 적중률도 참고로 출력

주의
- "익일 수익>0"은 거래비용/슬리피지 미반영
- 데이터는 일봉 종가 기준
"""

import os
import sys
import glob
import warnings
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml.config import CFG
from ml.data_pipeline import load_all_bars, compute_technical_indicators, get_feature_columns

warnings.filterwarnings("ignore")


def _load_latest_model() -> Tuple[CatBoostClassifier, List[str], str]:
    model_files = glob.glob(os.path.join(CFG.model_dir, "catboost_*.cbm"))
    if not model_files:
        raise FileNotFoundError(f"No model found in {CFG.model_dir}")
    model_path = max(model_files, key=os.path.getctime)

    model = CatBoostClassifier()
    model.load_model(model_path)

    try:
        feature_names = list(model.feature_names_)
    except Exception:
        feature_names = get_feature_columns()

    return model, feature_names, model_path


def _build_features(df_all: pd.DataFrame) -> pd.DataFrame:
    processed = []
    for code, group in df_all.groupby("code"):
        group = group.sort_values("date").reset_index(drop=True)
        if len(group) < 60:
            continue
        processed.append(compute_technical_indicators(group))

    if not processed:
        raise ValueError("No valid data after indicator computation")

    df_features = pd.concat(processed, ignore_index=True)
    df_features["date"] = df_features["date"].dt.strftime("%Y-%m-%d")
    return df_features


def _predict(model: CatBoostClassifier, feature_names: List[str], df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
    for col in feature_names:
        if col not in df.columns:
            df[col] = 0

    X = df[feature_names]
    if X.empty:
        return np.zeros((len(df),), dtype=np.int64), np.zeros((len(df),), dtype=np.float32)

    probs = model.predict_proba(X)
    if probs.ndim == 2:
        pred_class = probs.argmax(axis=1).astype(np.int64)
        prob_up = probs[:, 1:].sum(axis=1).astype(np.float32)
        return pred_class, prob_up

    return np.zeros((len(df),), dtype=np.int64), np.zeros((len(df),), dtype=np.float32)


def evaluate_2025(start_date: str = "2025-01-01", end_date: str = "2025-12-31") -> None:
    print("=" * 100)
    print("Evaluate 'Up Hit Rate' (next-day return > 0 | predicted up) - 2025")
    print("predicted up: argmax class in 1..6")
    print("=" * 100)

    df_all = load_all_bars("2024-10-01", "2025-12-31")
    df = _build_features(df_all)

    model, feature_names, model_path = _load_latest_model()
    print(f"[INFO] Model: {model_path}")

    dates = sorted(df[(df["date"] >= start_date) & (df["date"] <= end_date)]["date"].unique())
    if len(dates) < 2:
        raise ValueError("Not enough dates")

    total_pred_up = 0
    total_hit = 0

    cls_pred = {k: 0 for k in range(1, 7)}
    cls_hit = {k: 0 for k in range(1, 7)}

    # prob threshold diagnostics
    thresholds = [0.5, 0.6, 0.7, 0.8, 0.9]
    thr_pred = {t: 0 for t in thresholds}
    thr_hit = {t: 0 for t in thresholds}

    pred_up_per_day = []

    for i in range(len(dates) - 1):
        today = dates[i]
        next_day = dates[i + 1]

        day = df[df["date"] == today].copy()
        nxt = df[df["date"] == next_day][["code", "close"]].copy()
        if day.empty or nxt.empty:
            continue

        next_close = nxt.set_index("code")["close"]
        day = day[day["code"].isin(next_close.index)].copy()
        if day.empty:
            continue

        pred_class, prob_up = _predict(model, feature_names, day)
        day["pred_class"] = pred_class
        day["prob_up"] = prob_up

        # realized next-day return
        day["next_close"] = day["code"].map(next_close)
        day = day[(day["close"] > 0) & (day["next_close"] > 0)]
        if day.empty:
            continue
        day["ret_next"] = day["next_close"] / day["close"] - 1.0

        mask_up = (day["pred_class"] >= 1)
        up_df = day[mask_up]
        n_up = len(up_df)
        if n_up == 0:
            pred_up_per_day.append(0)
            continue

        hits = (up_df["ret_next"] > 0).sum()
        total_pred_up += n_up
        total_hit += int(hits)
        pred_up_per_day.append(n_up)

        # class-wise
        for k in range(1, 7):
            sub = up_df[up_df["pred_class"] == k]
            if len(sub) == 0:
                continue
            cls_pred[k] += len(sub)
            cls_hit[k] += int((sub["ret_next"] > 0).sum())

        # threshold diagnostics on prob_up
        for t in thresholds:
            sub = up_df[up_df["prob_up"] >= t]
            if len(sub) == 0:
                continue
            thr_pred[t] += len(sub)
            thr_hit[t] += int((sub["ret_next"] > 0).sum())

    precision = (total_hit / total_pred_up * 100.0) if total_pred_up > 0 else 0.0
    avg_up = float(np.mean(pred_up_per_day)) if pred_up_per_day else 0.0

    print("\n" + "=" * 100)
    print("OVERALL")
    print(f"Predicted-up trades: {total_pred_up:,}")
    print(f"Hit count (ret_next>0): {total_hit:,}")
    print(f"Up Hit Rate (Precision): {precision:.2f}%")
    print(f"Avg predicted-up per day: {avg_up:.1f}")

    print("\n" + "=" * 100)
    print("BY CLASS (1~6)")
    rows = []
    for k in range(1, 7):
        n = cls_pred[k]
        h = cls_hit[k]
        r = (h / n * 100.0) if n > 0 else 0.0
        rows.append({"class": k, "pred": n, "hit": h, "hit_rate_pct": r})
    print(pd.DataFrame(rows).to_string(index=False))

    print("\n" + "=" * 100)
    print("PROB_UP THRESHOLD DIAGNOSTIC (within predicted-up set)")
    rows = []
    for t in thresholds:
        n = thr_pred[t]
        h = thr_hit[t]
        r = (h / n * 100.0) if n > 0 else 0.0
        rows.append({"prob_up>=": t, "pred": n, "hit": h, "hit_rate_pct": r})
    print(pd.DataFrame(rows).to_string(index=False))
    print("=" * 100)


if __name__ == "__main__":
    evaluate_2025()
