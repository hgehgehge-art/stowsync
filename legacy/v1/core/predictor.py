"""선적 순서 예측 — SPEC 5.5.

1) 중량 그룹: 양하항 위치(먼 정도) 구간별로 GaussianMixture 를 맞춰 3~4개 그룹 (Park et al. 2023 참고)
2) 사례기반 추론(FASTrak 방식): 과거 항차에서 가중 거리 Σ wᵢ·|xᵢ − xᵢ'| 가 가까운 k개 사례의
   적재 순서 백분위를 평균 → 예측 백분위 + 10~90% 구간 + 근거 사례 3건
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture


def _bucket(pod_d) -> np.ndarray:
    return np.rint(np.asarray(pod_d, float) * 4).astype(int)


class LoadSeqPredictor:
    def __init__(self, params: dict):
        pp = params["predictor"]
        self.k = pp["k_neighbors"]
        self.n_groups = pp["gmm_components"]
        fw = pp["feature_weights"]
        self.w = np.array([fw["pod"], fw["weight_group"], fw["weight"], fw["size40"], fw["dg"]])
        self.seed = params["seed"]
        self.gmms: dict[int, tuple[GaussianMixture, np.ndarray]] = {}

    # ── 학습 ──
    def fit(self, hist: pd.DataFrame) -> "LoadSeqPredictor":
        b = _bucket(hist.pod_d)
        allw = hist.weight.to_numpy().reshape(-1, 1)
        self._global = self._fit_gmm(allw)
        for k in np.unique(b):
            w = hist.weight.to_numpy()[b == k].reshape(-1, 1)
            self.gmms[int(k)] = self._fit_gmm(w) if len(w) >= 40 else self._global
        self.hist = hist.reset_index(drop=True).copy()
        self.hist["weight_group"] = self.weight_group(hist.pod_d, hist.weight)
        self.X = self._features(self.hist.pod_d, self.hist.weight_group, self.hist.weight,
                                self.hist["size"], self.hist.is_dg)
        self.y = self.hist.load_pct.to_numpy()
        return self

    def _fit_gmm(self, w):
        g = GaussianMixture(self.n_groups, random_state=self.seed, n_init=2).fit(w)
        rank = np.argsort(np.argsort(g.means_.ravel()))  # 성분 → 가벼운 순 그룹 번호
        return g, rank

    def weight_group(self, pod_d, weight) -> np.ndarray:
        """0 = 가벼움 … n_groups-1 = 무거움"""
        pod_d, weight = np.atleast_1d(pod_d).astype(float), np.atleast_1d(weight).astype(float)
        out = np.zeros(len(weight), int)
        b = _bucket(pod_d)
        for k in np.unique(b):
            g, rank = self.gmms.get(int(k), self._global)
            m = b == k
            out[m] = rank[g.predict(weight[m].reshape(-1, 1))]
        return out

    def _features(self, pod_d, group, weight, size, dg) -> np.ndarray:
        return np.column_stack([
            np.asarray(pod_d, float),
            np.asarray(group, float) / max(self.n_groups - 1, 1),
            np.clip((np.asarray(weight, float) - 2) / 28, 0, 1),
            (np.asarray(size) == 40).astype(float),
            np.asarray(dg, float),
        ])

    # ── 예측 ──
    def _neighbors(self, Xq: np.ndarray):
        d = (np.abs(Xq[:, None, :] - self.X[None, :, :]) * self.w).sum(axis=2)
        k = min(self.k, d.shape[1])
        idx = np.argpartition(d, k - 1, axis=1)[:, :k]
        dd = np.take_along_axis(d, idx, axis=1)
        o = np.argsort(dd, axis=1, kind="stable")
        return np.take_along_axis(idx, o, 1), np.take_along_axis(dd, o, 1)

    def predict_batch(self, pod_d, weight, size, dg, chunk: int = 256) -> pd.DataFrame:
        pod_d = np.asarray(pod_d, float)
        weight = np.asarray(weight, float)
        group = self.weight_group(pod_d, weight)
        Xq = self._features(pod_d, group, weight, size, dg)
        pct, lo, hi = [], [], []
        for s in range(0, len(Xq), chunk):
            idx, _ = self._neighbors(Xq[s:s + chunk])
            ys = self.y[idx]
            pct.append(ys.mean(1))
            lo.append(np.quantile(ys, 0.1, axis=1))
            hi.append(np.quantile(ys, 0.9, axis=1))
        cat = lambda a: np.concatenate(a) if a else np.array([])
        return pd.DataFrame({"pred_pct": cat(pct), "pred_lo": cat(lo), "pred_hi": cat(hi), "weight_group": group})

    def explain(self, pod_d: float, weight: float, size: int, dg: bool) -> dict:
        """한 박스에 대한 예측 + 이웃 분포 + 근거 사례 3건."""
        group = int(self.weight_group([pod_d], [weight])[0])
        Xq = self._features([pod_d], [group], [weight], [size], [dg])
        idx, dist = self._neighbors(Xq)
        ys = self.y[idx[0]]
        cases = self.hist.iloc[idx[0][:3]].copy()
        cases["distance"] = dist[0][:3]
        return {"pred_pct": float(ys.mean()), "pred_lo": float(np.quantile(ys, 0.1)),
                "pred_hi": float(np.quantile(ys, 0.9)), "neighbor_pcts": ys, "weight_group": group,
                "cases": cases}
