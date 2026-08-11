"""
rup/persistencia.py
===================
Grava o consolidado da Camada 1 (Hh por FVS) no Supabase, tabela rup_hh_fvs.

Upsert por (obra, fvs_codigo): recalcular o Hh não recria linha nem apaga as
colunas do denominador (unidade/qtd_executada/eap_referencia/rup_real) — só os
campos da Camada 1 vão no payload, então o que o Sienge preencher depois fica
intacto. Requer SUPABASE_URL e SUPABASE_KEY no ambiente.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

try:
    from supabase import create_client
    _HAS = True
except ImportError:
    _HAS = False


def _cliente():
    url, key = os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_KEY", "")
    if not (_HAS and url and key):
        raise RuntimeError(
            "Supabase não configurado (defina SUPABASE_URL/SUPABASE_KEY e "
            "instale supabase>=2.0.0).")
    return create_client(url, key)


_CAMPOS_C1 = (
    "hh_total", "dias_trabalhados", "efetivo_medio_dia", "n_pavimentos",
    "pavimentos", "hh_por_funcao", "pct_compartilhado", "fvs_nome",
)


def salvar_camada1(agregado: list[dict]) -> int:
    """
    Insere/atualiza as linhas de Hh por FVS. Devolve quantas foram gravadas.
    `agregado` é a saída de rup.agregador.agregar_por_fvs.
    """
    if not agregado:
        return 0
    cli = _cliente()
    agora = datetime.now(timezone.utc).isoformat()
    linhas = [{
        "obra": a["obra"],
        "fvs_codigo": a["fvs_codigo"],
        **{k: a[k] for k in _CAMPOS_C1},
        "atualizado_em": agora,
    } for a in agregado]
    cli.table("rup_hh_fvs").upsert(linhas, on_conflict="obra,fvs_codigo").execute()
    return len(linhas)
