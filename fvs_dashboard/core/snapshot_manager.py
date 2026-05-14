"""
core/snapshot_manager.py
========================
Gerencia snapshots diarios em Parquet para auditoria temporal.

Estrutura de arquivos:
    data/snapshots/
    ├── 2026-05-14/
    │   ├── cape_town_residence.parquet
    │   └── holmes_residence.parquet
    └── 2026-05-15/
        └── ...

Schema do snapshot (por linha = 1 FVS de 1 atividade liberada):
    date_snapshot, obra, act_id, wbs, floor, cf_pct,
    modelo, local, status, pct_exec, nc, data_ins,
    date_first_seen, dias_pendente, faixa_aging, link
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path
from typing import Any

import pandas as pd

# Raiz do projeto (prevision_agent/)
_SNAPSHOT_FILE = Path(__file__).resolve()
PROJECT_ROOT   = _SNAPSHOT_FILE.parents[2]      # prevision_agent/
SNAPSHOT_DIR   = PROJECT_ROOT / "data" / "snapshots"


def _obra_slug(obra: str) -> str:
    """'Cape Town Residence' → 'cape_town_residence'"""
    return re.sub(r"[^a-z0-9]+", "_", obra.lower()).strip("_")


def _aging_faixa(dias: int) -> str:
    if dias <= 3:  return "0-3d"
    if dias <= 7:  return "4-7d"
    if dias <= 14: return "8-14d"
    return ">14d"


class SnapshotManager:
    """
    Salva e carrega snapshots diarios de FVS liberadas.

    Uso basico:
        sm = SnapshotManager()
        sm.save_snapshot("Cape Town Residence", rows)   # rows de prepare_project()
        history = sm.load_history("Cape Town Residence")
    """

    def __init__(self) -> None:
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Helpers de path ───────────────────────────────────────────────────────

    def _day_dir(self, date: datetime.date) -> Path:
        return SNAPSHOT_DIR / date.isoformat()

    def _parquet_path(self, obra: str, date: datetime.date) -> Path:
        return self._day_dir(date) / f"{_obra_slug(obra)}.parquet"

    # ── Verificacao ───────────────────────────────────────────────────────────

    def has_today_snapshot(self, obra: str) -> bool:
        """Retorna True se ja existe snapshot para hoje."""
        return self._parquet_path(obra, datetime.date.today()).exists()

    def list_snapshot_dates(self, obra: str) -> list[datetime.date]:
        """Lista todas as datas com snapshot disponivel para a obra."""
        dates = []
        slug  = _obra_slug(obra)
        for day_dir in sorted(SNAPSHOT_DIR.iterdir()):
            if not day_dir.is_dir():
                continue
            pq = day_dir / f"{slug}.parquet"
            if pq.exists():
                try:
                    dates.append(datetime.date.fromisoformat(day_dir.name))
                except ValueError:
                    pass
        return dates

    # ── Salvar snapshot ───────────────────────────────────────────────────────

    def save_snapshot(
        self,
        obra: str,
        rows: list[dict],
        date: datetime.date | None = None,
    ) -> Path | None:
        """
        Salva snapshot do dia como Parquet.

        - Se ja existir snapshot para hoje, retorna None (sem sobrescrever).
        - Calcula date_first_seen cruzando com snapshots anteriores.
        - Adiciona faixa_aging e dias_pendente.

        Retorna o Path do arquivo salvo, ou None se ja existia.
        """
        if date is None:
            date = datetime.date.today()

        out_path = self._parquet_path(obra, date)
        if out_path.exists():
            return None

        if not rows:
            return None

        # Carrega mapa de date_first_seen a partir do historico existente
        first_seen = self._load_first_seen(obra)

        records = []
        for r in rows:
            key = (r.get("act_id", ""), r.get("modelo", ""), r.get("local", ""))

            if key in first_seen:
                fs = first_seen[key]
            else:
                fs = date
                first_seen[key] = fs  # registra para as proximas linhas do mesmo batch

            dias = (date - fs).days

            records.append({
                "date_snapshot":  date.isoformat(),
                "obra":           obra,
                "act_id":         r.get("act_id", ""),
                "wbs":            r.get("wbs", ""),
                "floor":          r.get("floor", ""),
                "cf_pct":         float(r.get("cf_pct") or 0),
                "modelo":         r.get("modelo", ""),
                "local":          r.get("local", ""),
                "status":         r.get("status", ""),
                "pct_exec":       float(r["pct_exec"]) if r.get("pct_exec") is not None else None,
                "nc":             int(r.get("nc") or 0),
                "nc_tratadas":    int(r.get("nc_tratadas") or 0),
                "nc_pendentes":   int(r.get("nc_pendentes") or 0),
                "data_ins":       r.get("data_ins", ""),
                "link":           r.get("link", ""),
                "date_first_seen": fs.isoformat(),
                "dias_pendente":  dias,
                "faixa_aging":    _aging_faixa(dias),
            })

        df = pd.DataFrame(records)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out_path, index=False)
        return out_path

    # ── Carregar historico ────────────────────────────────────────────────────

    def load_history(self, obra: str) -> pd.DataFrame:
        """
        Carrega e concatena todos os snapshots disponiveis para a obra.
        Retorna DataFrame vazio se nao existir historico.
        """
        slug  = _obra_slug(obra)
        parts = []

        for day_dir in sorted(SNAPSHOT_DIR.iterdir()):
            if not day_dir.is_dir():
                continue
            pq = day_dir / f"{slug}.parquet"
            if pq.exists():
                try:
                    parts.append(pd.read_parquet(pq))
                except Exception:
                    pass

        if not parts:
            return pd.DataFrame()

        df = pd.concat(parts, ignore_index=True)
        df["date_snapshot"]   = pd.to_datetime(df["date_snapshot"]).dt.date
        df["date_first_seen"] = pd.to_datetime(df["date_first_seen"]).dt.date
        # Retrocompatibilidade: preenche colunas ausentes em parquets antigos
        for col, default in [("nc_tratadas", 0), ("nc_pendentes", 0)]:
            if col not in df.columns:
                df[col] = default
        return df

    def load_latest_snapshot(self, obra: str) -> pd.DataFrame:
        """Carrega apenas o snapshot mais recente."""
        dates = self.list_snapshot_dates(obra)
        if not dates:
            return pd.DataFrame()
        pq = self._parquet_path(obra, dates[-1])
        df = pd.read_parquet(pq)
        df["date_snapshot"]   = pd.to_datetime(df["date_snapshot"]).dt.date
        df["date_first_seen"] = pd.to_datetime(df["date_first_seen"]).dt.date
        return df

    # ── Internos ──────────────────────────────────────────────────────────────

    def _load_first_seen(self, obra: str) -> dict[tuple[str, str, str], datetime.date]:
        """
        Carrega mapa (act_id, modelo, local) -> date_first_seen
        a partir de todos os snapshots anteriores.
        """
        history = self.load_history(obra)
        if history.empty:
            return {}
        result: dict[tuple[str, str, str], datetime.date] = {}
        for _, row in history.iterrows():
            key = (str(row["act_id"]), str(row["modelo"]), str(row["local"]))
            fs  = row["date_first_seen"]
            if isinstance(fs, str):
                fs = datetime.date.fromisoformat(fs)
            if key not in result or fs < result[key]:
                result[key] = fs
        return result

    # ── Estatisticas rapidas ──────────────────────────────────────────────────

    def n_snapshots(self, obra: str) -> int:
        """Numero de snapshots disponiveis."""
        return len(self.list_snapshot_dates(obra))

    def oldest_snapshot(self, obra: str) -> datetime.date | None:
        dates = self.list_snapshot_dates(obra)
        return dates[0] if dates else None
