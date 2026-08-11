"""
rup/agregador.py
================
Agrega os registros de efetivo (rup.parser_rdo) por celula = codigo FVS.

Camada 1 (produtividade fisica) — NUMERADOR da RUP:
    Hh_acumulado por FVS, efetivo medio/dia, dias trabalhados, Hh por funcao.
O DENOMINADOR (quantidade executada) entra depois (Prevision/Sienge); aqui so
consolidamos o que o RDO sustenta sozinho.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any


def agregar_por_fvs(registros: list[dict]) -> list[dict]:
    """Consolida registros diarios por (obra, codigo FVS)."""
    grupos: dict[tuple[str, str], dict[str, Any]] = {}

    for r in registros:
        chave = (r["obra"], r["fvs_codigo"])
        g = grupos.get(chave)
        if g is None:
            g = grupos[chave] = {
                "obra": r["obra"],
                "fvs_codigo": r["fvs_codigo"],
                "fvs_nome": r["fvs_nome"],
                "hh_total": 0.0,
                "dias": set(),
                "pavimentos": set(),
                "hh_por_funcao": defaultdict(float),
                "efetivo_por_dia": defaultdict(float),
                "registros_compartilhados": 0,
                "registros": 0,
            }
        g["hh_total"] += r["hh_total"]
        g["dias"].add(r["data"])
        g["pavimentos"].update(r["pavimentos"])
        g["registros"] += 1
        if r["compartilhado"]:
            g["registros_compartilhados"] += 1
        for c in r["colaboradores"]:
            g["hh_por_funcao"][c["funcao"]] += c["hh"]
            g["efetivo_por_dia"][r["data"]] += 1

    saida: list[dict] = []
    for g in grupos.values():
        dias = len(g["dias"])
        efetivo_medio = (sum(g["efetivo_por_dia"].values()) / dias) if dias else 0.0
        saida.append({
            "obra": g["obra"],
            "fvs_codigo": g["fvs_codigo"],
            "fvs_nome": g["fvs_nome"],
            "hh_total": round(g["hh_total"], 1),
            "dias_trabalhados": dias,
            "efetivo_medio_dia": round(efetivo_medio, 1),
            "pavimentos": sorted(g["pavimentos"]),
            "n_pavimentos": len(g["pavimentos"]),
            "hh_por_funcao": {k: round(v, 1) for k, v in
                              sorted(g["hh_por_funcao"].items(),
                                     key=lambda x: -x[1])},
            "pct_compartilhado": round(
                100 * g["registros_compartilhados"] / g["registros"], 1)
            if g["registros"] else 0.0,
        })
    saida.sort(key=lambda x: -x["hh_total"])
    return saida
