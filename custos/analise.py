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


def tendencia_preco(insumo: dict, k: int = 3) -> dict:
    """
    Tendência do PU: média das últimas k compras vs a base (compras anteriores).
    Devolve variação %, direção (alta/estavel/baixa) e se está acelerando (a
    última compra ainda acima da média recente). Robustez: precisa de histórico.
    """
    hist = insumo.get("historico") or []
    if len(hist) < 2:
        return {"variacao_pct": None, "direcao": "sem_historico",
                "acelerando": False, "n_compras": len(hist)}
    pus_raw = [h["pu"] for h in hist]  # já ordenado por data no coletor
    # Filtra outlier de preço: o mesmo insumo às vezes é comprado em unidade
    # diferente (kg × barra), o que deixa o unitPrice incomparável. Mantém só
    # compras dentro de [mediana/3, mediana×3] — remove a unidade trocada.
    m = median(pus_raw)
    pus = [p for p in pus_raw if m / 3 <= p <= m * 3] or pus_raw
    if len(pus) < 2:
        return {"variacao_pct": None, "direcao": "sem_historico",
                "acelerando": False, "n_compras": len(hist)}
    # MEDIANA (não média) — robusta a outlier residual.
    med_rec = median(pus[-k:])
    med_base = median(pus[:-k] or pus[:-1])
    var = 100 * (med_rec - med_base) / med_base if med_base else 0.0
    direcao = "alta" if var > 3 else "baixa" if var < -3 else "estavel"
    acelerando = pus[-1] >= med_rec and direcao == "alta"
    return {"variacao_pct": round(var, 1), "direcao": direcao,
            "acelerando": acelerando, "n_compras": len(hist),
            "pu_recente": round(med_rec, 2), "pu_base": round(med_base, 2)}


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
    Recorta um insumo para os meses da janela: mantém só as compras do período e
    recalcula valor/quantidade/preço a partir delas. None se não comprou na janela.
    """
    hist = [h for h in (insumo.get("historico") or []) if (h.get("data") or "")[:7] in meses]
    if not hist:
        return None
    pus = [h["pu"] for h in hist]
    sq = sum(h["qtd"] for h in hist)
    mp = sum(h["pu"] * h["qtd"] for h in hist) / sq if sq else 0
    return {**insumo,
            "total_qtd": round(sq, 3),
            "total_valor": round(sum(h["pu"] * h["qtd"] for h in hist), 2),
            "n_compras": len(hist),
            "preco": {"primeiro": pus[0], "ultimo": pus[-1], "min": min(pus), "max": max(pus),
                      "medio": round(sum(pus) / len(pus), 4), "medio_ponderado": round(mp, 4)},
            "historico": hist}


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
            "total_valor": i.get("total_valor"), "n_compras": i.get("n_compras"),
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
                "texto": (f"{i.get('descricao')}: preço {tend['variacao_pct']:+.1f}% "
                          f"nas últimas compras (R$ {tend['pu_base']:.2f} → "
                          f"R$ {tend['pu_recente']:.2f})"),
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
