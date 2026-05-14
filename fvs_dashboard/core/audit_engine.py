"""
core/audit_engine.py
====================
Motor de auditoria gerencial — agregacoes mensais/trimestrais.

Fontes de dados:
  1. inmeta_inspections_raw.json — 1.760 inspecoes historicas (nov/2024 a mai/2026)
     Campo de data: dataInspecao (unica data disponivel na API)
     Status: EM_ANDAMENTO ou FINALIZADA
  2. data/snapshots/*.parquet — snapshots diarios acumulados a partir de 2026-05-14

Limitacoes documentadas (Fase A):
  - Nenhum endpoint /nao-conformidades existe na API InMeta (todos retornam 404)
  - NC disponivel apenas como contagens: qtdNaoConformidade e qtdNaoConformidadeTratada
  - Nao ha createdAt / updatedAt / finishedAt nas inspecoes
  - dataInspecao = data de criacao/execucao (proxy para inicio da FVS)
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

import pandas as pd

STATUS_NAO_INICIADA = "NAO_INICIADA"
STATUS_EM_ANDAMENTO = "EM_ANDAMENTO"
STATUS_FINALIZADA   = "FINALIZADA"

_OBRA_MAP = {
    "Cape Town Residence": "cape_town",
    "Holmes Residence":    "holmes",
}

_DATA_RAW = Path(__file__).resolve().parents[2] / "data" / "raw"
_INSP_CACHE = _DATA_RAW / "inmeta_inspections_raw.json"


# ── Carregamento de inspecoes brutas ──────────────────────────────────────────

def load_raw_inspections(obra_filter: str | None = None) -> list[dict]:
    """
    Carrega inspecoes do cache JSON.
    obra_filter: None = todas, ou nome da obra ("Cape Town Residence")
    Cada item tem campos: dataInspecao, status, qtdNaoConformidade,
                          qtdNaoConformidadeTratada, modelo._id/nome, local._id/nome
    """
    if not _INSP_CACHE.exists():
        return []
    with open(_INSP_CACHE, encoding="utf-8") as f:
        raw = json.load(f)

    result = []
    for obra_name, insp_key in _OBRA_MAP.items():
        if obra_filter and obra_filter != obra_name:
            continue
        bucket = raw.get(insp_key, {})
        for insp in bucket.get("inspections", []):
            insp["_obra"] = obra_name
            result.append(insp)
    return result


# ── Evolucao mensal a partir das inspecoes brutas ────────────────────────────

def build_monthly_from_inspections(obra_filter: str | None = None) -> pd.DataFrame:
    """
    Agrupa as 1.760 inspecoes historicas por mes de dataInspecao x status.

    Retorna DataFrame:
      date_month (date, primeiro dia do mes) | obra | finalizada | em_andamento
      | nc_total | nc_pendentes | nc_tratadas | total_insp

    Fonte: dataInspecao (unica data disponivel — proxy para data de atividade da FVS).
    Limitacao: representa estado ATUAL das inspecoes, agrupado pela data de execucao.
    """
    insps = load_raw_inspections(obra_filter)
    if not insps:
        return pd.DataFrame()

    records = []
    for ins in insps:
        data_str = ins.get("dataInspecao", "")
        if not data_str:
            continue
        try:
            dt = datetime.date.fromisoformat(data_str[:10])
        except ValueError:
            continue
        month_start = dt.replace(day=1)
        records.append({
            "date_month":    month_start,
            "obra":          ins.get("_obra", ""),
            "status":        ins.get("status", ""),
            "nc":            int(ins.get("qtdNaoConformidade") or 0),
            "nc_tratadas":   int(ins.get("qtdNaoConformidadeTratada") or 0),
        })

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df["nc_pendentes"] = (df["nc"] - df["nc_tratadas"]).clip(lower=0)

    grp = df.groupby(["date_month", "obra"]).agg(
        finalizada   = ("status", lambda s: (s == STATUS_FINALIZADA).sum()),
        em_andamento = ("status", lambda s: (s == STATUS_EM_ANDAMENTO).sum()),
        nc_total     = ("nc", "sum"),
        nc_pendentes = ("nc_pendentes", "sum"),
        nc_tratadas  = ("nc_tratadas", "sum"),
        total_insp   = ("status", "count"),
    ).reset_index()

    return grp.sort_values(["obra", "date_month"])


# ── Evolucao mensal a partir dos snapshots diarios ───────────────────────────

def build_monthly_from_snapshots(history: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega snapshots diarios em visao mensal.
    Usa o ULTIMO snapshot de cada mes por obra.

    Retorna DataFrame:
      date_month | obra | finalizada | em_andamento | nao_iniciada
      | nc | nc_pendentes | nc_tratadas | total_fvs
    """
    if history.empty:
        return pd.DataFrame()

    df = history.copy()
    df["date_month"] = pd.to_datetime(df["date_snapshot"]).dt.to_period("M").apply(
        lambda p: p.to_timestamp().date()
    )

    # Pega o ultimo snapshot de cada (obra, mes)
    latest = (
        df.groupby(["obra", "date_month"])["date_snapshot"]
        .max()
        .reset_index()
        .rename(columns={"date_snapshot": "latest_snap"})
    )
    df2 = df.merge(latest, on=["obra", "date_month"])
    df2 = df2[df2["date_snapshot"] == df2["latest_snap"]]

    grp = df2.groupby(["date_month", "obra"]).agg(
        finalizada   = ("status", lambda s: (s == STATUS_FINALIZADA).sum()),
        em_andamento = ("status", lambda s: (s == STATUS_EM_ANDAMENTO).sum()),
        nao_iniciada = ("status", lambda s: (s == STATUS_NAO_INICIADA).sum()),
        nc           = ("nc", "sum"),
        nc_pendentes = ("nc_pendentes", "sum") if "nc_pendentes" in df2.columns else ("nc", "sum"),
        nc_tratadas  = ("nc_tratadas", "sum")  if "nc_tratadas"  in df2.columns else ("nc", lambda x: 0),
        total_fvs    = ("status", "count"),
    ).reset_index()

    return grp.sort_values(["obra", "date_month"])


# ── Calculos de KPIs para um periodo ─────────────────────────────────────────

def compute_audit_kpis(
    monthly_insp: pd.DataFrame,
    snapshots_latest: pd.DataFrame,
    date_start: datetime.date,
    date_end: datetime.date,
    obra_filter: str | None = None,
) -> dict[str, Any]:
    """
    Computa KPIs executivos para o periodo e obra selecionados.

    monthly_insp: saida de build_monthly_from_inspections()
    snapshots_latest: snapshot mais recente (dm.load_latest_snapshot ou last day of period)
    """
    kpis: dict[str, Any] = {}

    # ── Filtra inspecoes do periodo ───────────────────────────────────────────
    mi = monthly_insp.copy()
    if not mi.empty:
        mi = mi[(mi["date_month"] >= date_start) & (mi["date_month"] <= date_end)]
        if obra_filter:
            mi = mi[mi["obra"] == obra_filter]

    if mi.empty:
        kpis.update({
            "total_insp":     0,
            "finalizada":     0,
            "em_andamento":   0,
            "nc_total":       0,
            "nc_pendentes":   0,
            "nc_tratadas":    0,
            "pct_finalizada": 0.0,
        })
    else:
        total   = int(mi["total_insp"].sum())
        fin     = int(mi["finalizada"].sum())
        em_and  = int(mi["em_andamento"].sum())
        nc_tot  = int(mi["nc_total"].sum())
        nc_pend = int(mi["nc_pendentes"].sum())
        nc_trat = int(mi["nc_tratadas"].sum())
        kpis.update({
            "total_insp":     total,
            "finalizada":     fin,
            "em_andamento":   em_and,
            "nc_total":       nc_tot,
            "nc_pendentes":   nc_pend,
            "nc_tratadas":    nc_trat,
            "pct_finalizada": round(100 * fin / total, 1) if total else 0.0,
        })

    # ── Filtra snapshots para estado atual ────────────────────────────────────
    sn = snapshots_latest.copy()
    if not sn.empty and obra_filter:
        sn = sn[sn["obra"] == obra_filter]

    if sn.empty:
        kpis.update({
            "snap_total_fvs":    0,
            "snap_nao_iniciada": 0,
            "snap_criticas":     0,
            "snap_nc_pendentes": 0,
            "avg_dias_pendente": 0.0,
        })
    else:
        nao_ini  = int((sn["status"] == STATUS_NAO_INICIADA).sum())
        criticas = int(((sn["status"] == STATUS_NAO_INICIADA) & (sn["dias_pendente"] > 7)).sum())
        nc_pend_snap = int(sn["nc_pendentes"].sum()) if "nc_pendentes" in sn.columns else 0
        avg_dias = float(sn["dias_pendente"].mean()) if len(sn) else 0.0
        kpis.update({
            "snap_total_fvs":    len(sn),
            "snap_nao_iniciada": nao_ini,
            "snap_criticas":     criticas,
            "snap_nc_pendentes": nc_pend_snap,
            "avg_dias_pendente": round(avg_dias, 1),
        })

    return kpis


# ── Comparativo entre obras ───────────────────────────────────────────────────

def build_obra_comparison(monthly_insp: pd.DataFrame) -> pd.DataFrame:
    """
    Retorna DataFrame com Cape Town e Holmes lado a lado por mes.
    Colunas: date_month | fin_ct | fin_hm | em_ct | em_hm | nc_ct | nc_hm
    """
    if monthly_insp.empty:
        return pd.DataFrame()

    ct = monthly_insp[monthly_insp["obra"] == "Cape Town Residence"].set_index("date_month")
    hm = monthly_insp[monthly_insp["obra"] == "Holmes Residence"].set_index("date_month")

    all_months = sorted(set(ct.index) | set(hm.index))
    rows = []
    for m in all_months:
        rows.append({
            "date_month":  m,
            "fin_ct":      int(ct.loc[m, "finalizada"])   if m in ct.index else 0,
            "fin_hm":      int(hm.loc[m, "finalizada"])   if m in hm.index else 0,
            "em_ct":       int(ct.loc[m, "em_andamento"]) if m in ct.index else 0,
            "em_hm":       int(hm.loc[m, "em_andamento"]) if m in hm.index else 0,
            "nc_ct":       int(ct.loc[m, "nc_total"])     if m in ct.index else 0,
            "nc_hm":       int(hm.loc[m, "nc_total"])     if m in hm.index else 0,
            "nc_pend_ct":  int(ct.loc[m, "nc_pendentes"]) if m in ct.index else 0,
            "nc_pend_hm":  int(hm.loc[m, "nc_pendentes"]) if m in hm.index else 0,
        })
    return pd.DataFrame(rows)


# ── Metricas SLA a partir de snapshots ───────────────────────────────────────

def compute_sla(history: pd.DataFrame) -> dict[str, Any]:
    """
    Calcula metricas de SLA a partir do historico de snapshots.

    Retorna:
      avg_dias_nao_iniciada: media de dias_pendente para NAO_INICIADA
      avg_dias_em_andamento: media para EM_ANDAMENTO
      max_dias_nao_iniciada: maximo
      backlog_por_modelo: top 10 modelos com mais FVS pendentes
    """
    if history.empty:
        return {}

    # Usa snapshot mais recente de cada obra
    latest_date = history["date_snapshot"].max()
    latest = history[history["date_snapshot"] == latest_date]

    nao_ini = latest[latest["status"] == STATUS_NAO_INICIADA]
    em_and  = latest[latest["status"] == STATUS_EM_ANDAMENTO]

    backlog = (
        latest[latest["status"] != STATUS_FINALIZADA]
        .groupby("modelo")
        .agg(pendentes=("status", "count"), nc=("nc", "sum"))
        .sort_values("pendentes", ascending=False)
        .head(10)
        .reset_index()
    )

    return {
        "avg_dias_nao_iniciada": round(nao_ini["dias_pendente"].mean(), 1) if len(nao_ini) else 0.0,
        "avg_dias_em_andamento": round(em_and["dias_pendente"].mean(), 1) if len(em_and) else 0.0,
        "max_dias_nao_iniciada": int(nao_ini["dias_pendente"].max()) if len(nao_ini) else 0,
        "backlog_por_modelo":    backlog,
    }


# ── Helpers de filtro de periodo ─────────────────────────────────────────────

def period_dates(period: str, custom_start=None, custom_end=None):
    """
    Retorna (date_start, date_end) para o periodo selecionado.
    period: 'Mes' | 'Trimestre' | 'Semestre' | 'Anual' | 'Personalizado' | 'Tudo'
    """
    today = datetime.date.today()
    if period == "Mes":
        return today.replace(day=1), today
    if period == "Trimestre":
        return today - datetime.timedelta(days=90), today
    if period == "Semestre":
        return today - datetime.timedelta(days=180), today
    if period == "Anual":
        return today.replace(month=1, day=1), today
    if period == "Personalizado":
        return custom_start or today - datetime.timedelta(days=30), custom_end or today
    # Tudo
    return datetime.date(2024, 1, 1), today
