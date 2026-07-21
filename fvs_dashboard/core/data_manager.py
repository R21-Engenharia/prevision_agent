"""
core/data_manager.py
====================
DataManager: orquestra carregamento de cache JSON, refresh de APIs e
computa DataFrames prontos para exibicao no dashboard.
"""

from __future__ import annotations

import json
import os
import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .business import (
    build_inspection_index,
    build_qa_index,
    compute_kpis,
    prepare_project,
    short_floor,
    STATUS_NAO_INICIADA,
    STATUS_EM_ANDAMENTO,
    STATUS_FINALIZADA,
)
from .inmeta_client import InMetaClient
from .snapshot_manager import SnapshotManager

# ── Raiz do projeto ───────────────────────────────────────────────────────────
# fvs_dashboard/ esta dentro de prevision_agent/
_DASHBOARD_DIR = Path(__file__).resolve().parent.parent   # fvs_dashboard/
PROJECT_ROOT   = _DASHBOARD_DIR.parent                    # prevision_agent/
DATA_RAW       = PROJECT_ROOT / "data" / "raw"

# ── Configuracao das obras ────────────────────────────────────────────────────
OBRAS: dict[str, dict[str, Any]] = {
    "Cape Town Residence": {
        "prevision_id": 10223,
        "inmeta_id":    "670d181e19927c97d4f22713",
        "jobs_cache":   DATA_RAW / "10223_jobs_raw.json",
        "qa_cache":     DATA_RAW / "10223_qa_raw.json",
        "insp_key":     "cape_town",
    },
    "Holmes Residence": {
        "prevision_id": 18992,
        "inmeta_id":    "670d2af985fc5d73377dd7b0",
        "jobs_cache":   DATA_RAW / "18992_jobs_raw.json",
        "qa_cache":     DATA_RAW / "18992_qa_raw.json",
        "insp_key":     "holmes",
    },
}

INSP_CACHE = DATA_RAW / "inmeta_inspections_raw.json"

# Garante que o diretorio de cache existe (necessario no Streamlit Cloud)
DATA_RAW.mkdir(parents=True, exist_ok=True)

# ── Status labels ─────────────────────────────────────────────────────────────
STATUS_LABEL = {
    STATUS_FINALIZADA:   "Finalizada",
    STATUS_EM_ANDAMENTO: "Em Andamento",
    STATUS_NAO_INICIADA: "Nao Iniciada",
}

STATUS_ORDER = {STATUS_FINALIZADA: 0, STATUS_EM_ANDAMENTO: 1, STATUS_NAO_INICIADA: 2}


class DataManager:
    """
    Gerencia todos os dados do dashboard.

    Os metodos get_* usam cache interno (_cache) para evitar
    releituras de disco dentro da mesma sessao Streamlit.
    Use invalidate() para forccar releitura.
    """

    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}
        self._sm: Any = SnapshotManager()

    def setup_supabase(self, url: str, key: str) -> None:
        """Ativa persistencia via Supabase (substitui Parquet local)."""
        from .supabase_snapshot import SupabaseSnapshotManager
        self._sm = SupabaseSnapshotManager(url, key)

    @property
    def uses_supabase(self) -> bool:
        try:
            from .supabase_snapshot import SupabaseSnapshotManager
            return isinstance(self._sm, SupabaseSnapshotManager)
        except Exception:
            return False

    # ── Internos: leitura de cache JSON ──────────────────────────────────────

    def _load_json(self, path: Path) -> Any:
        """
        Le o JSON com cache em memoria, invalidado pela data de modificacao.

        Antes o cache era indexado so pelo caminho: uma vez lido, o arquivo
        nunca mais era relido. No Streamlit isso passava despercebido (processo
        curto), mas a API e um processo longo — depois da coleta diaria ela
        continuaria servindo o dado antigo ate alguem reinicia-la.
        """
        key = str(path)
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = None

        em_cache = self._cache.get(key)
        if em_cache is not None and em_cache[0] == mtime:
            return em_cache[1]

        with open(path, encoding="utf-8") as f:
            dados = json.load(f)

        self._cache[key] = (mtime, dados)
        # Derivados (rows/df/kpis) foram calculados sobre o conteudo antigo
        self._invalidar_derivados()
        return dados

    def _invalidar_derivados(self) -> None:
        """Descarta rows_/df_/kpis_ apos releitura de um arquivo de origem."""
        for k in [k for k in self._cache
                  if k.startswith(("rows_", "df_", "kpis_", "top_modelos_"))]:
            self._cache.pop(k, None)

    def invalidate(self, path: Path | None = None) -> None:
        """Invalida cache interno (forcca releitura do disco)."""
        if path is None:
            self._cache.clear()
        else:
            self._cache.pop(str(path), None)

    # ── Idade do cache ────────────────────────────────────────────────────────

    def cache_age(self, obra: str) -> dict[str, str]:
        """Retorna idade dos arquivos de cache como string legivel."""
        cfg = OBRAS[obra]

        def _age(p: Path) -> str:
            if not p.exists():
                return "sem dados"
            delta = datetime.datetime.now() - datetime.datetime.fromtimestamp(p.stat().st_mtime)
            h = int(delta.total_seconds() // 3600)
            m = int((delta.total_seconds() % 3600) // 60)
            if h >= 24:
                return f"ha {h // 24}d {h % 24}h"
            if h >= 1:
                return f"ha {h}h {m}min"
            return f"ha {m}min"

        return {
            "prevision": _age(cfg["jobs_cache"]),
            "inmeta":    _age(INSP_CACHE),
        }

    def cache_mtime(self, obra: str) -> dict[str, datetime.datetime | None]:
        """Retorna datetime de modificacao dos caches."""
        cfg = OBRAS[obra]
        def _mt(p: Path):
            return datetime.datetime.fromtimestamp(p.stat().st_mtime) if p.exists() else None
        return {"prevision": _mt(cfg["jobs_cache"]), "inmeta": _mt(INSP_CACHE)}

    def inmeta_age_hours(self) -> float | None:
        """Retorna idade do cache InMeta em horas. None se nao existir."""
        if not INSP_CACHE.exists():
            return None
        delta = datetime.datetime.now() - datetime.datetime.fromtimestamp(INSP_CACHE.stat().st_mtime)
        return delta.total_seconds() / 3600

    def inmeta_needs_refresh(self) -> bool:
        """
        True se o cache precisa ser atualizado.
        Criterios: arquivo inexistente, ou de dia anterior, ou com mais de 4h.
        """
        if not INSP_CACHE.exists():
            return True
        mtime = datetime.datetime.fromtimestamp(INSP_CACHE.stat().st_mtime)
        now   = datetime.datetime.now()
        if mtime.date() < now.date():          # dado de ontem ou antes
            return True
        if (now - mtime).total_seconds() > 4 * 3600:  # mais de 4h mesmo dia
            return True
        return False

    # ── Carregamento de dados ─────────────────────────────────────────────────

    def _get_activities(self, obra: str) -> list[dict]:
        cfg = OBRAS[obra]
        if not cfg["jobs_cache"].exists():
            return []
        data = self._load_json(cfg["jobs_cache"])
        return data.get("activities_list", [])

    def _get_qas(self, obra: str) -> list[dict]:
        cfg = OBRAS[obra]
        if not cfg["qa_cache"].exists():
            return []
        data = self._load_json(cfg["qa_cache"])
        return data.get("quality_associations", [])

    def _get_inspections(self, obra: str) -> list[dict]:
        if not INSP_CACHE.exists():
            return []
        data = self._load_json(INSP_CACHE)
        key  = OBRAS[obra]["insp_key"]
        return data.get(key, {}).get("inspections", [])

    # ── DataFrame principal ───────────────────────────────────────────────────

    def get_rows(self, obra: str) -> list[dict]:
        """Retorna lista de linhas processadas (liberados x FVS status)."""
        cache_key = f"rows_{obra}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        acts  = self._get_activities(obra)
        qas   = self._get_qas(obra)
        insps = self._get_inspections(obra)

        qa_idx   = build_qa_index(qas)
        insp_idx = build_inspection_index(insps)
        rows     = prepare_project(acts, qa_idx, insp_idx)

        self._cache[cache_key] = rows
        return rows

    def get_df(self, obra: str) -> pd.DataFrame:
        """Retorna DataFrame formatado para exibicao."""
        cache_key = f"df_{obra}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        rows = self.get_rows(obra)
        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)

        # Formata colunas para exibicao
        df["Pavimento"]    = df["floor"].apply(short_floor)
        df["WBS"]          = df["wbs"]
        df["CF%"]          = df["cf_pct"].apply(lambda x: f"{x:.0f}%")
        df["Modelo FVS"]   = df["modelo"]
        df["Local"]        = df["local"]
        df["Status"]       = df["status"].map(STATUS_LABEL).fillna(df["status"])
        df["% Exec"]       = df["pct_exec"].apply(lambda x: f"{x}%" if x is not None else "—")
        df["NC"]           = df["nc"].apply(lambda x: str(x) if x else "")
        df["Data Insp."]   = df["data_ins"]
        df["Link InMeta"]  = df["link"]
        df["_status_ord"]  = df["status"].map(STATUS_ORDER).fillna(9)

        self._cache[cache_key] = df
        return df

    def get_kpis(self, obra: str) -> dict[str, Any]:
        """Retorna KPIs da obra."""
        cache_key = f"kpis_{obra}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        rows  = self.get_rows(obra)
        acts  = self._get_activities(obra)
        kpis  = compute_kpis(rows, acts)
        self._cache[cache_key] = kpis
        return kpis

    def get_top_modelos(self, obra: str, n: int = 10) -> pd.DataFrame:
        """Retorna top N modelos FVS com mais pendencias."""
        df = self.get_df(obra)
        if df.empty:
            return pd.DataFrame()

        grp = df.groupby("Modelo FVS").agg(
            Total    = ("Status", "count"),
            Finalizada   = ("status", lambda s: (s == STATUS_FINALIZADA).sum()),
            Em_Andamento = ("status", lambda s: (s == STATUS_EM_ANDAMENTO).sum()),
            Nao_Iniciada = ("status", lambda s: (s == STATUS_NAO_INICIADA).sum()),
            NC       = ("nc", "sum"),
        ).reset_index()
        grp["Pendentes"] = grp["Em_Andamento"] + grp["Nao_Iniciada"]
        return grp.sort_values("Pendentes", ascending=False).head(n)

    # ── Refresh de dados ──────────────────────────────────────────────────────

    # ── Snapshots historicos ──────────────────────────────────────────────────

    def save_snapshot(self, obra: str) -> bool:
        """
        Salva snapshot do dia para a obra.
        Parquet: pula se ja existir snapshot hoje.
        Supabase: sempre upserta (dados mais recentes vencem).
        """
        rows = self.get_rows(obra)
        if not rows:
            return False
        if not self.uses_supabase and self._sm.has_today_snapshot(obra):
            return False
        result = self._sm.save_snapshot(obra, rows)
        return bool(result)

    def save_all_snapshots(self) -> dict[str, bool]:
        """Salva snapshot de todas as obras. Retorna {obra: salvou}."""
        return {obra: self.save_snapshot(obra) for obra in OBRAS}

    def load_history(self, obra: str) -> "pd.DataFrame":
        """Carrega historico completo de snapshots para a obra."""
        return self._sm.load_history(obra)

    def load_latest_snapshot(self, obra: str) -> "pd.DataFrame":
        """Carrega apenas o snapshot mais recente."""
        return self._sm.load_latest_snapshot(obra)

    def snapshot_info(self, obra: str) -> dict:
        """Informacoes sobre os snapshots disponiveis."""
        return self._sm.snapshot_info(obra)

    # ── Refresh de dados ──────────────────────────────────────────────────────

    def refresh_inmeta(self, obra: str, client: InMetaClient) -> None:
        """
        Atualiza inspecoes InMeta para TODAS as obras e salva o cache.
        (O endpoint retorna tudo por alvo; atualizamos todos de uma vez.)
        """
        all_data: dict[str, Any] = {}
        if INSP_CACHE.exists():
            with open(INSP_CACHE, encoding="utf-8") as f:
                all_data = json.load(f)

        all_data["collected_at"] = datetime.datetime.now().isoformat()

        for obra_name, cfg in OBRAS.items():
            insps = client.fetch_inspections(cfg["inmeta_id"])
            key   = cfg["insp_key"]
            all_data[key] = {
                "alvo_id":     cfg["inmeta_id"],
                "inspections": insps,
            }

        with open(INSP_CACHE, "w", encoding="utf-8") as f:
            json.dump(all_data, f, ensure_ascii=False)

        # Invalida cache em memoria
        self.invalidate(INSP_CACHE)
        for obra_name in OBRAS:
            self._cache.pop(f"rows_{obra_name}", None)
            self._cache.pop(f"df_{obra_name}", None)
            self._cache.pop(f"kpis_{obra_name}", None)
