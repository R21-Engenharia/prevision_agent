"""
Acesso aos dados do módulo de Inteligência de Custos.
=====================================================
Lê os snapshots coletados (compras_{pid}.json) e roda o motor de análise
(custos.analise) — cálculo determinístico no backend. Mesmo padrão dos outros
módulos: obra-scoped, sem estado.
"""
from __future__ import annotations

import json
from pathlib import Path

_RAIZ = Path(__file__).resolve().parent.parent


def _pid_da_obra(obra: str) -> int | None:
    from fvs_dashboard.core.data_manager import OBRAS
    cfg = OBRAS.get(obra)
    return cfg["prevision_id"] if cfg else None


def _compras_da_obra(obra: str) -> dict:
    pid = _pid_da_obra(obra)
    if not pid:
        return {}
    f = _RAIZ / "data" / f"compras_{pid}.json"
    if not f.exists():
        return {}
    return json.loads(f.read_text(encoding="utf-8"))


def material(obra: str, top: int = 40) -> dict:
    """Análise de custo de material: ABC + tendência de preço + alertas."""
    from custos.analise import analisar
    compras = _compras_da_obra(obra)
    if not compras:
        return {"obra": obra, "disponivel": False,
                "mensagem": "Compras ainda não coletadas para esta obra."}
    r = analisar(compras, top=top)
    return {"obra": obra, "disponivel": True, **r}


def desembolso(obra: str) -> dict:
    """Previsão de desembolso comprometido por janela (7/15/30/60/90 dias)."""
    from custos.desembolso import previsao
    pid = _pid_da_obra(obra)
    f = _RAIZ / "data" / f"desembolso_{pid}.json" if pid else None
    if not f or not f.exists():
        return {"obra": obra, "disponivel": False,
                "mensagem": "Desembolso ainda não coletado para esta obra."}
    dados = json.loads(f.read_text(encoding="utf-8"))
    return {"obra": obra, "disponivel": True, **previsao(dados)}
