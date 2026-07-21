"""
core/business.py
================
Regras de negocio do Dashboard FVS.
Extraido e refatorado de fase4_gera_relatorio.py e fase5_relatorio_fvs_status.py.
"""

from __future__ import annotations
import re
from collections import defaultdict
from typing import Any

# ── Constante central ────────────────────────────────────────────────────────
CF_NAME = "CONFERENCIA FINAL"   # normalizado sem acento para comparacao robusta

def _norm(s: str) -> str:
    """Normaliza string para comparacao: maiuscula, sem acento."""
    return (s.upper()
            .replace("Ç", "C").replace("ç", "c")
            .replace("Ã", "A").replace("ã", "a")
            .replace("Ê", "E").replace("ê", "e")
            .replace("Â", "A").replace("â", "a")
            .replace("Õ", "O").replace("õ", "o")
            .replace("Ú", "U").replace("ú", "u")
            .upper())


# ── Regra de liberacao FVS ────────────────────────────────────────────────────

def is_liberado(jobs: list[dict]) -> bool:
    """
    Retorna True se o pacote esta liberado para FVS:
      - Todos os jobs executivos = 100%
      - CONFERENCIA FINAL < 100% (ainda nao finalizado)
    """
    exec_jobs = [j for j in jobs if _norm(j.get("name", "")) != CF_NAME]
    cf_jobs   = [j for j in jobs if _norm(j.get("name", "")) == CF_NAME]
    if not cf_jobs or not exec_jobs:
        return False
    for j in exec_jobs:
        if (j.get("percentageCompleted") or 0) < 100:
            return False
    return (cf_jobs[0].get("percentageCompleted") or 0) < 100


def cf_pct(jobs: list[dict]) -> float:
    """Retorna o percentual de CONFERENCIA FINAL."""
    cf = [j for j in jobs if _norm(j.get("name", "")) == CF_NAME]
    return float(cf[0].get("percentageCompleted") or 0) if cf else 0.0


# ── Parsing de referencia FVS ─────────────────────────────────────────────────

def parse_ref(name: str) -> tuple[str, str]:
    """
    Separa 'FVS 01.02.03 - Descricao | Local do Local'
    em (modelo, local).
    """
    parts = name.split(" | ", 1)
    modelo = parts[0].strip()
    local  = parts[1].strip() if len(parts) > 1 else ""
    return modelo, local


# ── Indice de inspecoes ───────────────────────────────────────────────────────

def build_inspection_index(inspections: list[dict]) -> dict[tuple[str, str], list[dict]]:
    """
    Constroi indice (localId, modeloId) -> [inspecoes] para lookup O(1).
    """
    idx: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for i in inspections:
        l = i.get("local", {})
        m = i.get("modelo", {})
        if isinstance(l, dict) and isinstance(m, dict):
            lid = l.get("_id", "")
            mid = m.get("_id", "")
            if lid and mid:
                idx[(lid, mid)].append(i)
    return dict(idx)


def build_qa_index(qas: list[dict]) -> dict[str, list[dict]]:
    """Indice activity_id -> [QAs]."""
    idx: dict[str, list[dict]] = defaultdict(list)
    for qa in qas:
        idx[str(qa.get("itemId", ""))].append(qa)
    return dict(idx)


# ── Preparacao do projeto ─────────────────────────────────────────────────────

STATUS_NAO_INICIADA = "NAO_INICIADA"
STATUS_EM_ANDAMENTO = "EM_ANDAMENTO"
STATUS_FINALIZADA   = "FINALIZADA"


def prepare_project(
    activities: list[dict],
    qa_index: dict[str, list[dict]],
    insp_index: dict[tuple[str, str], list[dict]],
) -> list[dict]:
    """
    Para cada atividade liberada, cruza QAs com inspecoes InMeta.

    Retorna lista de linhas com campos:
      floor, act_id, wbs, cf_pct, modelo, local,
      status, pct_exec, nc, data_ins, link
    """
    rows: list[dict] = []

    liberadas = [
        a for a in activities
        if a.get("hasJobs") and is_liberado(a.get("jobs", []))
    ]

    for act in liberadas:
        act_id    = str(act["id"])
        floor_nm  = act.get("_floor_name", "")
        wbs       = act.get("wbsCode", "")
        cf        = cf_pct(act.get("jobs", []))

        for qa in qa_index.get(act_id, []):
            key    = (qa.get("partnerLocalId", ""), qa.get("partnerModelId", ""))
            insps  = insp_index.get(key, [])
            ref    = qa.get("partnerReferenceName", "")
            modelo, local = parse_ref(ref)

            if insps:
                ins         = sorted(insps, key=lambda x: x.get("dataInspecao", ""), reverse=True)[0]
                status      = ins.get("status", STATUS_NAO_INICIADA)
                svc         = ins.get("servico") or {}
                pct_exec    = svc.get("percentualExecutado")
                nc          = ins.get("qtdNaoConformidade") or 0
                nc_tratadas = ins.get("qtdNaoConformidadeTratada") or 0
                data_ins    = ins.get("dataInspecao", "")[:10]
                link        = ins.get("link", "")
            else:
                status      = STATUS_NAO_INICIADA
                pct_exec    = None
                nc          = 0
                nc_tratadas = 0
                data_ins    = ""
                link        = ""

            rows.append({
                "floor":       floor_nm,
                "act_id":      act_id,
                "wbs":         wbs,
                "cf_pct":      cf,
                "modelo":      modelo,
                "local":       local,
                "status":      status,
                "pct_exec":    pct_exec,
                "nc":          nc,
                "nc_tratadas": nc_tratadas,
                # qtdNaoConformidade JA e o saldo em aberto do InMeta — nao o
                # total historico. Ha inspecoes com nc=0 e tratadas=4, e a soma
                # de qtdNaoConformidade bate exatamente com o painel do InMeta.
                # A formula antiga (nc - nc_tratadas) subnotificava as NC em
                # aberto (180 reais viravam 155 na Cape Town).
                "nc_pendentes": nc,
                "data_ins":    data_ins,
                "link":        link,
            })

    return rows


# ── KPIs ──────────────────────────────────────────────────────────────────────

def compute_kpis(rows: list[dict], activities: list[dict]) -> dict[str, Any]:
    """Computa indicadores-chave a partir das linhas processadas."""
    liberadas_ids = {r["act_id"] for r in rows}

    total_lib     = len(liberadas_ids)
    finalizada    = sum(1 for r in rows if r["status"] == STATUS_FINALIZADA)
    em_andamento  = sum(1 for r in rows if r["status"] == STATUS_EM_ANDAMENTO)
    nao_iniciada  = sum(1 for r in rows if r["status"] == STATUS_NAO_INICIADA)
    nc_total      = sum(r["nc"] for r in rows)
    total_fvs     = len(rows)

    return {
        "total_lib":    total_lib,
        "total_fvs":    total_fvs,
        "finalizada":   finalizada,
        "em_andamento": em_andamento,
        "nao_iniciada": nao_iniciada,
        "nc_total":     nc_total,
        "pct_finalizada":   round(100 * finalizada   / total_fvs, 1) if total_fvs else 0,
        "pct_em_andamento": round(100 * em_andamento / total_fvs, 1) if total_fvs else 0,
        "pct_nao_iniciada": round(100 * nao_iniciada / total_fvs, 1) if total_fvs else 0,
    }


# ── Formatacao de pavimento ───────────────────────────────────────────────────

def short_floor(floor_name: str) -> str:
    """Extrai rotulo curto do pavimento: '09 PV - TIPO' -> '09 PV'."""
    m = re.match(r"^(\d+)[oaº]?\s*(?:PV|PVTO)", floor_name, re.IGNORECASE)
    if m:
        num = int(m.group(1))
        return f"{num:02d}o PV"
    return floor_name.split("|")[0].strip()[:25]
