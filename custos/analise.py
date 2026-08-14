"""
custos/analise.py
=================
Motor de análise de custos de MATERIAL (Fase 1) — determinístico, sem IA nos
cálculos. Trabalha sobre as compras coletadas (custos_{pid}.json):

  • Curva ABC por realizado (onde o dinheiro foi gasto);
  • Tendência de preço por insumo (o preço está subindo?);
  • Alertas objetivos (preço em alta em item de peso).

A IA, se usada depois, só EXPLICA esses números — nunca os calcula.
"""
from __future__ import annotations

from statistics import median


def _classe_abc(pct_acum: float) -> str:
    if pct_acum <= 80:
        return "A"
    if pct_acum <= 95:
        return "B"
    return "C"


def curva_abc(insumos: list[dict]) -> list[dict]:
    """
    Ordena por valor comprado e classifica A/B/C pela participação acumulada.
    Cada insumo ganha: pct (do total) e pct_acum + classe.
    """
    ordenado = sorted(insumos, key=lambda i: -(i.get("total_valor") or 0))
    total = sum(i.get("total_valor") or 0 for i in ordenado) or 1
    acum = 0.0
    out = []
    for i in ordenado:
        v = i.get("total_valor") or 0
        acum += v
        pct_acum = 100 * acum / total
        out.append({**i, "pct": round(100 * v / total, 2),
                    "pct_acum": round(pct_acum, 2), "classe": _classe_abc(pct_acum)})
    return out


def tendencia_preco(insumo: dict) -> dict:
    """
    Tendência do preço comparando o ÚLTIMO preço contra a REFERÊNCIA HISTÓRICA do
    insumo — a primeira compra e a média (mediana) histórica. Assim, mesmo que o
    insumo tenha sido comprado uma única vez na janela, a variação é medida contra
    o histórico completo dele (não contra si mesmo). `historico` deve ser o
    histórico COMPLETO, nunca o recortado pela janela.
    """
    hist = insumo.get("historico") or []
    # pares (mês, preço), ordenados por data — guarda a data p/ referência temporal
    pares_raw = [((h.get("data") or "")[:7], h["pu"]) for h in hist]
    if not pares_raw:
        return {"variacao_pct": None, "direcao": "sem_historico", "n_compras": 0}
    # Filtra outlier: o mesmo insumo às vezes é comprado em unidade diferente
    # (kg × barra) → unitPrice incomparável. Mantém [mediana/3, mediana×3].
    m = median(p for _, p in pares_raw)
    pares = [(d, p) for d, p in pares_raw if m / 3 <= p <= m * 3] or pares_raw
    pus = [p for _, p in pares]
    if len(pus) < 2:
        return {"variacao_pct": None, "direcao": "compra_unica", "n_compras": len(pus),
                "ultimo": round(pus[-1], 2), "primeira": round(pus[0], 2),
                "medio": round(pus[0], 2), "primeira_mes": pares[0][0],
                "ultimo_mes": pares[-1][0]}
    primeira, primeira_mes = pus[0], pares[0][0]
    medio = median(pus)          # referência histórica robusta
    ultimo, ultimo_mes = pus[-1], pares[-1][0]
    var_medio = 100 * (ultimo - medio) / medio if medio else 0.0
    var_prim = 100 * (ultimo - primeira) / primeira if primeira else 0.0
    direcao = "alta" if var_medio > 3 else "baixa" if var_medio < -3 else "estavel"
    return {
        "variacao_pct": round(var_medio, 1),           # último vs média histórica
        "variacao_primeira_pct": round(var_prim, 1),   # último vs 1ª compra
        "direcao": direcao,
        "acelerando": ultimo >= medio and direcao == "alta",
        "n_compras": len(hist),
        "primeira": round(primeira, 2), "medio": round(medio, 2),
        "ultimo": round(ultimo, 2),
        "primeira_mes": primeira_mes, "ultimo_mes": ultimo_mes,
    }


def abc_por_grupo(insumos: list[dict]) -> list[dict]:
    """Agrupa insumos por grupo econômico (normalização) e aplica ABC ao grupo."""
    from collections import defaultdict
    from custos.normalizar import grupo_de
    g: dict[str, dict] = defaultdict(lambda: {"grupo": "", "total_valor": 0.0,
                                              "total_qtd_compras": 0, "n_insumos": 0})
    for i in insumos:
        gr = grupo_de(i.get("descricao", ""))
        d = g[gr]
        d["grupo"] = gr
        d["total_valor"] += i.get("total_valor") or 0
        d["total_qtd_compras"] += i.get("n_compras") or 0
        d["n_insumos"] += 1
    return curva_abc(list(g.values()))


def _recompute_janela(insumo: dict, meses: set[str]) -> dict | None:
    """
    Recorta um insumo para os meses da janela SÓ no gasto (valor/qtd/nº compras),
    para a ABC refletir a atividade recente. Mantém o `historico` e o `preco`
    COMPLETOS — a variação de preço é sempre contra a referência histórica, nunca
    contra a própria janela. None se o insumo não teve compra na janela.
    """
    janela = [h for h in (insumo.get("historico") or []) if (h.get("data") or "")[:7] in meses]
    if not janela:
        return None
    sq = sum(h["qtd"] for h in janela)
    return {**insumo,  # preserva historico + preco completos (referência)
            "total_qtd_janela": round(sq, 3),
            "total_valor": round(sum(h["pu"] * h["qtd"] for h in janela), 2),
            "n_compras_janela": len(janela)}


def analisar(compras: dict, top: int = 40, janela: str = "obra",
             hoje=None) -> dict:
    """
    Análise completa de material: ABC (insumo e grupo) + tendência + alertas.
    `compras` = conteúdo de compras_{pid}.json (chave "insumos").
    `janela` (mes_atual|mes_anterior|6m|12m|obra): recorta as COMPRAS ao período,
    recalculando ABC e alertas só com o que foi comprado na janela.
    """
    insumos = list((compras.get("insumos") or {}).values())
    if janela and janela != "obra":
        from rup.janela import meses as _meses
        sel, _ = _meses(janela, hoje)
        if sel is not None:
            ms = set(sel)
            insumos = [ri for ri in (_recompute_janela(i, ms) for i in insumos) if ri]
    abc = curva_abc(insumos)
    grupos = abc_por_grupo(insumos)
    total = sum(i.get("total_valor") or 0 for i in insumos)

    itens = []
    alertas = []
    for i in abc[:top]:
        tend = tendencia_preco(i)
        item = {
            "resource_id": i.get("resource_id"), "descricao": i.get("descricao"),
            "unidade": i.get("unidade"), "total_qtd": i.get("total_qtd"),
            "total_valor": i.get("total_valor"),
            # nº de compras na janela (se filtrado) e no histórico todo
            "n_compras": i.get("n_compras_janela", i.get("n_compras")),
            "n_compras_hist": i.get("n_compras"),
            "classe": i["classe"], "pct": i["pct"], "pct_acum": i["pct_acum"],
            "preco": i.get("preco"), "tendencia": tend,
            "fornecedores": len(i.get("fornecedores") or []),
        }
        itens.append(item)
        # alerta de preço: item de peso (A/B) com preço em alta
        if i["classe"] in ("A", "B") and tend["direcao"] == "alta":
            alertas.append({
                "tipo": "preco", "nivel": "alto" if tend["acelerando"] else "medio",
                "resource_id": i.get("resource_id"), "descricao": i.get("descricao"),
                "variacao_pct": tend["variacao_pct"], "classe": i["classe"],
                "valor": i.get("total_valor"),
                # prioridade: impacto (classe ABC) × piora (acelerando)
                "prioridade": ("P1" if i["classe"] == "A" and tend["acelerando"]
                               else "P2" if i["classe"] == "A"
                               else "P3" if tend["acelerando"] else "P4"),
                "texto": (f"{i.get('descricao')}: último R$ {tend['ultimo']:.2f} — "
                          f"{tend['variacao_pct']:+.1f}% vs média (R$ {tend['medio']:.2f}), "
                          f"{tend['variacao_primeira_pct']:+.1f}% vs 1ª compra "
                          f"(R$ {tend['primeira']:.2f})"),
            })
    alertas.sort(key=lambda a: (a["prioridade"], -(a.get("valor") or 0)))
    return {
        "total_comprado": round(total, 2),
        "n_insumos": len(insumos),
        "abc_resumo": {c: sum(1 for i in abc if i["classe"] == c) for c in "ABC"},
        "grupos": [{"grupo": g["grupo"], "total_valor": g["total_valor"],
                    "pct": g["pct"], "pct_acum": g["pct_acum"], "classe": g["classe"],
                    "n_insumos": g["n_insumos"]} for g in grupos],
        "itens": itens,
        "alertas": alertas,
    }
