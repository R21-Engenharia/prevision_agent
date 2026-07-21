"""
core/decoracao_engine.py
========================
Engine do modulo de Decoracao.

Carrega atividades de acabamento a partir dos caches Prevision
(activities_raw.json + jobs_raw.json), filtra por keywords nos
nomes dos jobs e produz DataFrames prontos para KPIs e Gantt.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

# ─── Raiz do projeto ─────────────────────────────────────────────────────────
_ROOT    = Path(__file__).resolve().parent.parent.parent   # prevision_agent/
DATA_RAW = _ROOT / "data" / "raw"

# ─── Keywords que identificam atividades de decoracao nos nomes dos jobs ──────
DECOR_KEYWORDS: list[str] = [
    "PINTUR", "REVESTIM", "PISO", "MARCEN", "GESSO", "FORRO",
    "LOUCA",  "METAL",   "ACABAM", "BANCAD", "PORCELA", "MARMORE",
    "PEDRA",  "VIDRO",   "ESPELHO", "DECOR", "TEXTUR",  "TINTA",
    "VERNIZ", "MADEIRA", "PARQUET", "CONTRAPISO", "ASSENT",
    "AZULEJO", "CERAMICA", "REJUNT", "SILICO", "SELADOR",
    "ARGAMASSA", "IMPERMEAB",
]

# ─── Disciplinas ─────────────────────────────────────────────────────────────
DISCIPLINES: dict[str, list[str]] = {
    "Pintura":         ["PINTUR", "TINTA", "VERNIZ", "TEXTUR", "SELADOR"],
    "Revestimento":    ["REVESTIM", "AZULEJO", "CERAMICA", "PORCELA", "ASSENT",
                        "MARMORE", "REJUNT", "ARGAMASSA"],
    "Piso":            ["PISO", "CONTRAPISO", "PARQUET", "MADEIRA"],
    "Gesso / Forro":   ["GESSO", "FORRO"],
    "Marcenaria":      ["MARCEN"],
    "Metais e Loucas": ["LOUCA", "METAL", "BANCAD"],
    "Vidros":          ["VIDRO", "ESPELHO", "SILICO"],
    "Impermeabilizacao": ["IMPERMEAB"],
    "Acabamentos":     ["ACABAM", "DECOR", "PEDRA"],
}

DISC_COLORS: dict[str, str] = {
    "Pintura":           "#F6A623",
    "Revestimento":      "#4A7BB5",
    "Piso":              "#82A0C0",
    "Gesso / Forro":     "#A8D5A2",
    "Marcenaria":        "#C8935A",
    "Metais e Loucas":   "#9B59B6",
    "Vidros":            "#48C9B0",
    "Impermeabilizacao": "#E74C3C",
    "Acabamentos":       "#BDC3C7",
    "Outros":            "#95A5A6",
}

# Alinhado ao design system (fvs_dashboard/ui/theme.py — GANTT_STATUS)
STATUS_COLORS: dict[str, str] = {
    "Finalizada":   "#1E8E5A",
    "Em andamento": "#D98A00",
    "Nao iniciada": "#8A94A6",
    "Atrasada":     "#C41230",
}

OBRAS_CACHE: dict[str, dict[str, Path]] = {
    "Cape Town Residence": {
        "activities": DATA_RAW / "10223_activities_raw.json",
        "jobs":       DATA_RAW / "10223_jobs_raw.json",
    },
    "Holmes Residence": {
        "activities": DATA_RAW / "18992_activities_raw.json",
        "jobs":       DATA_RAW / "18992_jobs_raw.json",
    },
}


# ─── Helpers privados ─────────────────────────────────────────────────────────

def _classify_discipline(job_name: str) -> str:
    name = job_name.upper()
    for disc, keys in DISCIPLINES.items():
        if any(k in name for k in keys):
            return disc
    return "Outros"


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _agg_status(pct: float, exp_pct: float) -> str:
    if pct >= 100:
        return "Finalizada"
    if pct > 0:
        return "Atrasada" if (exp_pct or 0) > pct else "Em andamento"
    if (exp_pct or 0) > 0:
        return "Atrasada"
    return "Nao iniciada"


def _short_floor(name: str, max_len: int = 28) -> str:
    """Trunca nome longo de pavimento para exibicao no eixo Y do Gantt."""
    return name if len(name) <= max_len else name[:max_len - 1] + "…"


# ─── API publica ──────────────────────────────────────────────────────────────

def load_decoracao(obra: str | None = None) -> pd.DataFrame:
    """
    Carrega DataFrame de atividades de decoracao.

    Se obra=None, carrega e concatena ambas as obras.

    Colunas retornadas
    ------------------
    obra, act_id, wbs, floor, floor_short, floor_pos, discipline,
    job_name, start, end, duration, pct, expected_pct, status,
    start_dt, end_dt
    """
    obras = [obra] if obra else list(OBRAS_CACHE.keys())
    frames: list[pd.DataFrame] = []

    for obra_name in obras:
        cfg = OBRAS_CACHE.get(obra_name, {})
        acts_path = cfg.get("activities")
        jobs_path = cfg.get("jobs")

        if not acts_path or not acts_path.exists():
            continue
        if not jobs_path or not jobs_path.exists():
            continue

        with open(acts_path, encoding="utf-8") as f:
            acts_by_id: dict[str, Any] = {
                a["id"]: a for a in json.load(f).get("activities_list", [])
            }
        with open(jobs_path, encoding="utf-8") as f:
            jobs_list: list[dict] = json.load(f).get("activities_list", [])

        rows: list[dict] = []
        for jobs_act in jobs_list:
            act_id = jobs_act["id"]
            # primeiro job de decoracao que casar
            matched_job = next(
                (j for j in jobs_act.get("jobs", [])
                 if any(k in j.get("name", "").upper() for k in DECOR_KEYWORDS)),
                None,
            )
            if matched_job is None:
                continue
            act = acts_by_id.get(act_id)
            if act is None:
                continue

            start = _parse_date(act.get("startAt"))
            end   = _parse_date(act.get("endAt"))
            if start is None or end is None or end < start:
                continue

            pct     = float(act.get("percentageCompleted")         or 0)
            exp_pct = float(act.get("expectedPercentageCompleted") or 0)

            rows.append({
                "obra":        obra_name,
                "act_id":      act_id,
                "wbs":         act.get("wbsCode", ""),
                "floor":       act.get("_floor_name", ""),
                "floor_short": _short_floor(act.get("_floor_name", "")),
                "floor_pos":   int(act.get("_floor_position") or 0),
                "discipline":  _classify_discipline(matched_job["name"]),
                "job_name":    matched_job["name"],
                "start":       start,
                "end":         end,
                "duration":    (end - start).days + 1,
                "pct":         pct,
                "expected_pct": exp_pct,
                "status":      _agg_status(pct, exp_pct),
            })

        if rows:
            frames.append(pd.DataFrame(rows))

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    df["start_dt"] = pd.to_datetime(df["start"])
    df["end_dt"]   = pd.to_datetime(df["end"])
    return df.sort_values(["floor_pos", "start"]).reset_index(drop=True)


def compute_kpis(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {}

    hoje    = date.today()
    total   = len(df)
    fin     = int((df["status"] == "Finalizada").sum())
    em_and  = int((df["status"] == "Em andamento").sum())
    nao_ini = int((df["status"] == "Nao iniciada").sum())
    atras   = int((df["status"] == "Atrasada").sum())
    pct_med = round(float(df["pct"].mean()), 1)

    prox_30 = int(
        df[
            (df["start"] >= hoje) &
            (df["start"] <= hoje + timedelta(days=30)) &
            (df["status"] == "Nao iniciada")
        ].shape[0]
    )

    return {
        "total":        total,
        "finalizada":   fin,
        "em_andamento": em_and,
        "nao_iniciada": nao_ini,
        "atrasada":     atras,
        "pct_medio":    pct_med,
        "proximas_30d": prox_30,
    }


def build_floor_gantt(df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega atividades por pavimento para o Gantt.
    Uma linha por pavimento com: intervalo total, status agregado,
    % medio, contagem de atividades.
    """
    if df.empty:
        return pd.DataFrame()

    grp = (
        df.groupby(["obra", "floor", "floor_short", "floor_pos"])
        .agg(
            start_dt    = ("start_dt", "min"),
            end_dt      = ("end_dt",   "max"),
            n_ativs     = ("act_id",   "count"),
            pct_medio   = ("pct",      "mean"),
            n_fin       = ("status", lambda s: (s == "Finalizada").sum()),
            n_and       = ("status", lambda s: (s == "Em andamento").sum()),
            n_atra      = ("status", lambda s: (s == "Atrasada").sum()),
            n_nao       = ("status", lambda s: (s == "Nao iniciada").sum()),
            disciplines = ("discipline", lambda d: ", ".join(sorted(d.unique()))),
        )
        .reset_index()
    )

    def _floor_status(row) -> str:
        if row.n_atra > 0:
            return "Atrasada"
        if row.n_and > 0:
            return "Em andamento"
        if row.n_fin == row.n_ativs:
            return "Finalizada"
        return "Nao iniciada"

    grp["status"] = grp.apply(_floor_status, axis=1)
    grp["pct_medio"] = grp["pct_medio"].round(1)
    return grp.sort_values(["floor_pos"], ascending=True).reset_index(drop=True)


def build_discipline_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Contagem e % medio por disciplina."""
    if df.empty:
        return pd.DataFrame()
    return (
        df.groupby("discipline")
        .agg(
            total   = ("act_id", "count"),
            pct_med = ("pct",    "mean"),
            fin     = ("status", lambda s: (s == "Finalizada").sum()),
        )
        .reset_index()
        .assign(pct_med=lambda d: d["pct_med"].round(1))
        .sort_values("total", ascending=False)
    )
