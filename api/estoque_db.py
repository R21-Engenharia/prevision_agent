"""
Acesso aos dados do módulo de ESTOQUE (Fase 1).
================================================
Lê o snapshot coletado (estoque_{pid}.json) e roda o Stock Engine
(custos.estoque) — cálculo determinístico no backend. Mesmo padrão de custos_db:
obra-scoped, sem estado. A IA, depois, apenas explica estes números.
"""
from __future__ import annotations

import json
from pathlib import Path

_RAIZ = Path(__file__).resolve().parent.parent


def _pid_da_obra(obra: str) -> int | None:
    from fvs_dashboard.core.data_manager import OBRAS
    cfg = OBRAS.get(obra)
    return cfg["prevision_id"] if cfg else None


def material(obra: str, top: int = 40, janela_dias: int = 90) -> dict:
    """Estado do estoque por insumo: saldo, consumo, cobertura, ruptura, parado."""
    from custos.estoque import analisar
    pid = _pid_da_obra(obra)
    f = _RAIZ / "data" / f"estoque_{pid}.json" if pid else None
    if not f or not f.exists():
        return {"obra": obra, "disponivel": False,
                "mensagem": "Estoque ainda não coletado para esta obra."}
    dados = json.loads(f.read_text(encoding="utf-8"))
    r = analisar(dados, janela_dias=janela_dias, top=top)
    return {"obra": obra, "disponivel": True, **r}


def catalogo(obra: str, janela_dias: int = 90) -> dict:
    """Catálogo completo por insumo com grupo + macro-grupo, saldo e consumo —
    base da tela 'Operar almoxarifado' (filtro por macro/grupo + baixa na linha)."""
    from datetime import date
    from custos.estoque import _consumo_dia
    from custos.normalizar import MACRO_ORDEM, grupo_de, macro_de
    pid = _pid_da_obra(obra)
    f = _RAIZ / "data" / f"estoque_{pid}.json" if pid else None
    if not f or not f.exists():
        return {"obra": obra, "disponivel": False, "itens": [], "macros": []}
    insumos = (json.loads(f.read_text(encoding="utf-8")).get("insumos") or {}).values()
    hoje = date.today()
    itens, por_macro = [], {}
    for d in insumos:
        grupo = grupo_de(d.get("descricao") or "")
        macro = macro_de(grupo)
        consumo_dia, _ = _consumo_dia(d.get("consumo_mensal"), hoje, janela_dias)
        itens.append({
            "resource_id": d.get("resource_id"), "descricao": d.get("descricao"),
            "grupo": grupo, "macro": macro, "saldo": d.get("saldo"),
            "unidade": d.get("unidade_base"), "consumo_dia": round(consumo_dia, 3)})
        por_macro.setdefault(macro, set()).add(grupo)
    itens.sort(key=lambda i: (i["macro"], i["grupo"], -(i.get("saldo") or 0)))
    macros = [{"macro": m, "grupos": sorted(por_macro[m]),
               "n": sum(1 for i in itens if i["macro"] == m)}
              for m in MACRO_ORDEM if m in por_macro]
    return {"obra": obra, "disponivel": True, "itens": itens, "macros": macros}


def buscar(obra: str, q: str = "", limite: int = 20) -> dict:
    """Busca insumos por descrição (para a UI escolher o que movimentar)."""
    pid = _pid_da_obra(obra)
    f = _RAIZ / "data" / f"estoque_{pid}.json" if pid else None
    if not f or not f.exists():
        return {"obra": obra, "disponivel": False, "itens": []}
    insumos = (json.loads(f.read_text(encoding="utf-8")).get("insumos") or {}).values()
    termo = (q or "").strip().lower()
    achados = [
        {"resource_id": d.get("resource_id"), "descricao": d.get("descricao"),
         "unidade": d.get("unidade_base"), "saldo": d.get("saldo")}
        for d in insumos
        if not termo or termo in (d.get("descricao") or "").lower()
    ]
    achados.sort(key=lambda i: -(i.get("saldo") or 0))
    return {"obra": obra, "disponivel": True, "itens": achados[:limite]}
