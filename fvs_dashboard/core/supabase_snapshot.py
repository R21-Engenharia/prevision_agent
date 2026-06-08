"""
core/supabase_snapshot.py
=========================
Substituto do SnapshotManager que persiste no Supabase PostgreSQL.

Mesma API publica que SnapshotManager — troca transparente em DataManager.
Usa upsert: cada refresh do dia sobrescreve o anterior, garantindo dados frescos.
"""

from __future__ import annotations

import datetime
from typing import Any

import pandas as pd

try:
    from supabase import create_client, Client as SupabaseClient
    _HAS_SUPABASE = True
except ImportError:
    _HAS_SUPABASE = False

TABLE = "fvs_snapshots"
_CHUNK = 400  # linhas por request (limite payload Supabase ~1MB)


def _aging_faixa(dias: int) -> str:
    if dias <= 3:  return "0-3d"
    if dias <= 7:  return "4-7d"
    if dias <= 14: return "8-14d"
    return ">14d"


class SupabaseSnapshotManager:
    """
    Gerencia snapshots FVS no Supabase.

    Persistencia garantida entre restarts do Streamlit Cloud.
    Historico acumula indefinidamente — cada dia = 1 registro por FVS.
    """

    def __init__(self, url: str, key: str) -> None:
        if not _HAS_SUPABASE:
            raise ImportError("Execute: pip install supabase>=2.0.0")
        self._client: SupabaseClient = create_client(url, key)

    # ── Verificacao ───────────────────────────────────────────────────────────

    def has_today_snapshot(self, obra: str) -> bool:
        today = datetime.date.today().isoformat()
        r = (self._client.table(TABLE)
             .select("id", count="exact")
             .eq("obra", obra)
             .eq("date_snapshot", today)
             .limit(1)
             .execute())
        return (r.count or 0) > 0

    def list_snapshot_dates(self, obra: str) -> list[datetime.date]:
        r = (self._client.table(TABLE)
             .select("date_snapshot")
             .eq("obra", obra)
             .order("date_snapshot")
             .execute())
        if not r.data:
            return []
        seen: set[str] = set()
        dates: list[datetime.date] = []
        for row in r.data:
            d = row["date_snapshot"]
            if d not in seen:
                seen.add(d)
                dates.append(datetime.date.fromisoformat(d[:10]))
        return dates

    # ── Salvar ────────────────────────────────────────────────────────────────

    def save_snapshot(
        self,
        obra: str,
        rows: list[dict],
        date: datetime.date | None = None,
    ) -> bool:
        """
        Upserta snapshot no Supabase.

        Sempre upserta (sem checagem de today_exists) para que refreshes
        manuais do dia atualizem o snapshot com dados mais recentes.
        Retorna True se houve insercao/atualizacao, False se rows vazio.
        """
        if not rows:
            return False
        if date is None:
            date = datetime.date.today()

        first_seen = self._load_first_seen(obra)

        records: list[dict] = []
        for r in rows:
            key = (r.get("act_id", ""), r.get("modelo", ""), r.get("local", ""))
            fs = first_seen.get(key, date)
            first_seen[key] = fs
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

        for i in range(0, len(records), _CHUNK):
            (self._client.table(TABLE)
             .upsert(
                 records[i : i + _CHUNK],
                 on_conflict="date_snapshot,obra,act_id,modelo,local",
             )
             .execute())

        return True

    # ── Carregar historico ────────────────────────────────────────────────────

    def load_history(self, obra: str) -> pd.DataFrame:
        r = (self._client.table(TABLE)
             .select("*")
             .eq("obra", obra)
             .order("date_snapshot")
             .execute())
        return self._to_df(r.data)

    def load_latest_snapshot(self, obra: str) -> pd.DataFrame:
        # Descobre a data mais recente
        r = (self._client.table(TABLE)
             .select("date_snapshot")
             .eq("obra", obra)
             .order("date_snapshot", desc=True)
             .limit(1)
             .execute())
        if not r.data:
            return pd.DataFrame()
        latest = r.data[0]["date_snapshot"]
        r2 = (self._client.table(TABLE)
              .select("*")
              .eq("obra", obra)
              .eq("date_snapshot", latest)
              .execute())
        return self._to_df(r2.data)

    # ── Estatisticas ──────────────────────────────────────────────────────────

    def snapshot_info(self, obra: str) -> dict[str, Any]:
        dates = self.list_snapshot_dates(obra)
        today = datetime.date.today()
        return {
            "n_snapshots": len(dates),
            "oldest":      dates[0].isoformat() if dates else None,
            "latest":      dates[-1].isoformat() if dates else None,
            "has_today":   today in dates,
        }

    def n_snapshots(self, obra: str) -> int:
        return len(self.list_snapshot_dates(obra))

    def oldest_snapshot(self, obra: str) -> datetime.date | None:
        dates = self.list_snapshot_dates(obra)
        return dates[0] if dates else None

    # ── Internos ──────────────────────────────────────────────────────────────

    def _load_first_seen(self, obra: str) -> dict[tuple[str, str, str], datetime.date]:
        """Busca o menor date_first_seen historico para cada (act_id, modelo, local)."""
        r = (self._client.table(TABLE)
             .select("act_id,modelo,local,date_first_seen")
             .eq("obra", obra)
             .execute())
        if not r.data:
            return {}
        result: dict[tuple[str, str, str], datetime.date] = {}
        for row in r.data:
            key = (str(row["act_id"]), str(row["modelo"]), str(row["local"]))
            fs_raw = row.get("date_first_seen")
            if not fs_raw:
                continue
            fs = datetime.date.fromisoformat(str(fs_raw)[:10])
            if key not in result or fs < result[key]:
                result[key] = fs
        return result

    @staticmethod
    def _to_df(data: list[dict]) -> pd.DataFrame:
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        df["date_snapshot"]   = pd.to_datetime(df["date_snapshot"]).dt.date
        df["date_first_seen"] = pd.to_datetime(df["date_first_seen"]).dt.date
        for col, default in [("nc_tratadas", 0), ("nc_pendentes", 0)]:
            if col not in df.columns:
                df[col] = default
        # Remove coluna interna do Supabase
        df.drop(columns=["id", "created_at"], errors="ignore", inplace=True)
        return df
