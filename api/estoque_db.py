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
