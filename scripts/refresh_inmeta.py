"""
Coleta do InMeta para os caches que a API le — sem depender do Streamlit.
=========================================================================
Atualiza os dois arquivos JSON que alimentam as telas de Backlog, Auditoria
e Tempo:

    data/raw/inmeta_inspections_raw.json   inspecoes (status, NC, execucao)
    data/raw/inmeta_diario_raw.json        RDOs com a condicao do tempo

Por que existe: ate agora o unico jeito de atualizar esses arquivos era abrir
o Streamlit e clicar em "atualizar". O daily_snapshot.py chega a regerar as
inspecoes, mas seu workflow so grava no Supabase e descarta o JSON; e o diario
do tempo nao era coletado em CI nenhum. Resultado: os dois ficaram semanas
parados. Este script fecha essa lacuna e e o que o botao "Atualizar InMeta"
dispara.

Executar (a partir de prevision_agent/):
    python scripts/refresh_inmeta.py

Variaveis de ambiente (ou .env):
    INMETA_EMAIL, INMETA_SENHA   obrigatorias
    INMETA_BASE_URL              opcional (default https://api.inmeta.com.br)

Saida: codigo 0 em sucesso, 1 em falha (para o CI acusar o erro).
"""
from __future__ import annotations

import datetime
import json
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

from fvs_dashboard.core.data_manager import DataManager, OBRAS, DATA_RAW
from fvs_dashboard.core.inmeta_client import InMetaClient

DIARIO_CACHE = DATA_RAW / "inmeta_diario_raw.json"


def log(msg: str) -> None:
    agora = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{agora}] {msg}", flush=True)


def _novo_client() -> InMetaClient:
    # `or` em vez do default do getenv: quando o secret nao existe, o GitHub
    # Actions define a variavel VAZIA — e getenv(x, default) devolveria "" (a
    # variavel existe), deixando a URL em branco.
    return InMetaClient(
        base_url=os.getenv("INMETA_BASE_URL") or "https://api.inmeta.com.br",
        email=os.getenv("INMETA_EMAIL"),
        senha=os.getenv("INMETA_SENHA"),
    )


def coletar_diario(client: InMetaClient) -> int:
    """
    Grava inmeta_diario_raw.json com os RDOs (condicao do tempo) de cada obra.
    Espelha o _do_refresh da pagina 7_Tempo: guarda os RDOs crus por insp_key;
    a normalizacao acontece na leitura, em api/main.py.
    """
    cache: dict = {"collected_at": str(datetime.date.today())}
    total = 0
    for obra_nome, cfg in OBRAS.items():
        rdos = client.fetch_diario_obra(cfg["inmeta_id"])
        cache[cfg["insp_key"]] = rdos
        total += len(rdos)
        log(f"  {obra_nome}: {len(rdos)} RDOs")
    DIARIO_CACHE.parent.mkdir(parents=True, exist_ok=True)
    DIARIO_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return total


def main() -> int:
    if not os.getenv("INMETA_EMAIL") or not os.getenv("INMETA_SENHA"):
        log("ERRO: INMETA_EMAIL e INMETA_SENHA nao definidos.")
        return 1

    client = _novo_client()
    dm = DataManager()

    # 1. Inspecoes (status/NC/execucao) — busca todas as obras de uma vez.
    try:
        primeira = next(iter(OBRAS))
        dm.refresh_inmeta(primeira, client)
        log("Inspecoes atualizadas (inmeta_inspections_raw.json).")
    except Exception as exc:
        log(f"ERRO ao coletar inspecoes: {exc}")
        return 1

    # 2. Diario do tempo (RDOs).
    try:
        total = coletar_diario(client)
        log(f"Diario do tempo atualizado: {total} RDOs (inmeta_diario_raw.json).")
    except Exception as exc:
        log(f"ERRO ao coletar o diario do tempo: {exc}")
        return 1

    log("Coleta InMeta concluida com sucesso.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
