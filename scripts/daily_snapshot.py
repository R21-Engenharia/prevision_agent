"""
Snapshot diario das FVS — roda sem depender de alguem abrir o app.
==================================================================
Busca as inspecoes atuais no InMeta e grava um snapshot do dia por obra.

Por que existe: o cache JSON e sobrescrito a cada refresh (espelha o estado
atual do InMeta, sem historico). Quem constroi historico sao os snapshots, e
ate agora eles so eram gravados quando alguem abria o Streamlit — o que deixou
buracos de meses na serie. Este script fecha essa lacuna.

Executar (a partir de prevision_agent/):
    python scripts/daily_snapshot.py

Variaveis de ambiente (ou .env):
    INMETA_EMAIL, INMETA_SENHA   obrigatorias
    INMETA_BASE_URL              opcional (default https://api.inmeta.com.br)
    SUPABASE_URL, SUPABASE_KEY   opcionais — se presentes, persiste no Supabase;
                                 caso contrario grava Parquet em data/snapshots/

Saida: codigo 0 em sucesso, 1 em falha (para o CI acusar o erro).
"""
from __future__ import annotations

import datetime
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
except ImportError:
    pass  # em CI as variaveis vem do ambiente

from fvs_dashboard.core.data_manager import DataManager, OBRAS
from fvs_dashboard.core.inmeta_client import InMetaClient


def log(msg: str) -> None:
    agora = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{agora}] {msg}", flush=True)


def main() -> int:
    email = os.getenv("INMETA_EMAIL")
    senha = os.getenv("INMETA_SENHA")
    if not email or not senha:
        log("ERRO: INMETA_EMAIL e INMETA_SENHA nao definidos.")
        return 1

    dm = DataManager()

    # Persistencia: Supabase quando configurado (producao), senao Parquet local
    sb_url, sb_key = os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_KEY", "")
    if sb_url and sb_key:
        try:
            dm.setup_supabase(sb_url, sb_key)
            log("Persistencia: Supabase")
        except Exception as exc:
            log(f"AVISO: Supabase indisponivel ({exc}); usando Parquet local.")
    else:
        log("Persistencia: Parquet local (data/snapshots/)")

    # 1. Atualiza o cache do InMeta
    try:
        client = InMetaClient(
            base_url=os.getenv("INMETA_BASE_URL", "https://api.inmeta.com.br"),
            email=email,
            senha=senha,
        )
        primeira = list(OBRAS.keys())[0]
        dm.refresh_inmeta(primeira, client)   # busca todas as obras de uma vez
        log("Cache InMeta atualizado.")
    except Exception as exc:
        log(f"ERRO ao atualizar o InMeta: {exc}")
        return 1

    # 2. Grava o snapshot de cada obra
    falhas = 0
    for obra in OBRAS:
        try:
            criado = dm.save_snapshot(obra)
            rows = dm.get_rows(obra)
            fin = sum(1 for r in rows if r["status"] == "FINALIZADA")
            em  = sum(1 for r in rows if r["status"] == "EM_ANDAMENTO")
            nao = sum(1 for r in rows if r["status"] == "NAO_INICIADA")
            estado = "gravado" if criado else "ja existia hoje"
            log(f"{obra}: {estado} | {len(rows)} FVS "
                f"(finalizada={fin} andamento={em} nao_iniciada={nao})")
        except Exception as exc:
            falhas += 1
            log(f"ERRO em {obra}: {exc}")

    if falhas:
        log(f"Concluido com {falhas} falha(s).")
        return 1

    log("Snapshot diario concluido com sucesso.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
