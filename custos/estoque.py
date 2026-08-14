"""
custos/estoque.py
=================
Stock Engine — cálculo DETERMINÍSTICO do estado do estoque (Fase 1). Sem IA: a IA,
depois, apenas EXPLICA estes números. Trabalha sobre estoque_{pid}.json (coletor
inventory-movements).

Por insumo calcula:
  • saldo corrente (já vem do coletor)
  • consumo médio diário (janela recente de consumo real do almoxarifado)
  • cobertura em dias  = saldo ÷ consumo/dia
  • data estimada de ruptura
  • valor parado em estoque  = saldo × custo unitário médio de entrada
  • status: ruptura | critico | baixo | ok | parado

`parado` (saldo com capital empatado e sem consumo recente) é oportunidade, não risco
de falta — os dois lados que uma plataforma de estoque precisa enxergar.
"""
from __future__ import annotations

from datetime import date, timedelta

# Limiares de cobertura (dias). Ajustáveis por política depois (ponto de pedido).
COB_CRITICO = 7
COB_BAIXO = 15
# "parado": sem consumo há N dias, ainda com saldo relevante
PARADO_DIAS = 120


def _consumo_dia(consumo_mensal: dict, hoje: date, janela_dias: int) -> tuple[float, float]:
    """Consumo/dia na janela recente. Devolve (consumo_dia, consumo_janela)."""
    corte = (hoje - timedelta(days=janela_dias)).strftime("%Y-%m")
    total = sum(q for ym, q in (consumo_mensal or {}).items() if ym >= corte)
    return (total / janela_dias if janela_dias else 0.0), total


def _status(saldo: float, cob: float | None, consumo_dia: float,
            dias_sem_consumo: int | None) -> str:
    if consumo_dia > 0:
        if saldo <= 0:
            return "ruptura"
        if cob is not None and cob < COB_CRITICO:
            return "critico"
        if cob is not None and cob < COB_BAIXO:
            return "baixo"
        return "ok"
    # sem consumo recente
    if saldo > 0 and (dias_sem_consumo is None or dias_sem_consumo >= PARADO_DIAS):
        return "parado"
    return "ok"


def analisar(dados: dict, hoje: date | None = None, janela_dias: int = 90,
             top: int = 40) -> dict:
    """Estado do estoque + alertas priorizados. `dados` = estoque_{pid}.json."""
    hoje = hoje or date.today()
    insumos = list((dados.get("insumos") or {}).values())

    itens = []
    for d in insumos:
        saldo = float(d.get("saldo") or 0)
        consumo_dia, consumo_jan = _consumo_dia(d.get("consumo_mensal"), hoje, janela_dias)
        cob = (saldo / consumo_dia) if consumo_dia > 0 else None
        ent_q = float(d.get("entrada_qtd") or 0)
        custo_unit = (float(d.get("valor_entrada") or 0) / ent_q) if ent_q else 0.0
        valor_saldo = round(saldo * custo_unit, 2)

        uc = d.get("ultimo_consumo") or ""
        dias_sem = None
        if uc:
            try:
                dias_sem = (hoje - date.fromisoformat(uc)).days
            except ValueError:
                dias_sem = None
        st = _status(saldo, cob, consumo_dia, dias_sem)
        ruptura = None
        if cob is not None and consumo_dia > 0 and saldo > 0:
            ruptura = (hoje + timedelta(days=int(cob))).isoformat()

        # impacto = R$ de material consumido por dia — mede a RELEVÂNCIA do item
        # (separa argamassa que queima R$/dia de fita crepe que não move a obra)
        impacto_dia = round(consumo_dia * custo_unit, 2)
        itens.append({
            "resource_id": d.get("resource_id"), "descricao": d.get("descricao"),
            "unidade": d.get("unidade_base"), "saldo": round(saldo, 3),
            "consumo_dia": round(consumo_dia, 3), "consumo_janela": round(consumo_jan, 3),
            "cobertura_dias": round(cob, 1) if cob is not None else None,
            "data_ruptura": ruptura, "valor_saldo": valor_saldo,
            "custo_unit": round(custo_unit, 4), "impacto_dia": impacto_dia, "status": st,
            "ultimo_consumo": uc, "dias_sem_consumo": dias_sem,
            "unidade_inconsistente": d.get("unidade_inconsistente", False),
        })

    # prioridade de alerta: status × IMPACTO (R$/dia consumido). Assim um item de
    # peso à beira da ruptura sobe, e um consumível irrelevante zerado não vira alarme.
    ordem = {"ruptura": 0, "critico": 1, "baixo": 2}
    risco = [i for i in itens if i["status"] in ordem]
    risco.sort(key=lambda i: (ordem[i["status"]], -(i["impacto_dia"] or 0),
                              i["cobertura_dias"] if i["cobertura_dias"] is not None else 1e9))
    for i in risco:
        i["prioridade"] = ("P1" if i["status"] == "ruptura"
                           else "P2" if i["status"] == "critico" else "P3")

    parados = sorted((i for i in itens if i["status"] == "parado"),
                     key=lambda i: -(i["valor_saldo"] or 0))

    resumo = {s: sum(1 for i in itens if i["status"] == s)
              for s in ("ruptura", "critico", "baixo", "ok", "parado")}
    return {
        "obra": dados.get("obra"), "coletado_em": dados.get("coletado_em"),
        "janela_dias": janela_dias,
        "n_insumos": len(itens),
        "valor_em_estoque": round(sum(i["valor_saldo"] or 0 for i in itens), 2),
        "valor_parado": round(sum(i["valor_saldo"] or 0 for i in parados), 2),
        "resumo_status": resumo,
        "alertas": risco[:top],
        "parados": parados[:top],
        "unidades_inconsistentes": sum(1 for i in itens if i["unidade_inconsistente"]),
    }
