"""
custos/desembolso.py
====================
Previsão de desembolso a partir das parcelas a pagar (desembolso_{pid}.json).

Só o COMPROMETIDO (parcela agendada, com vencimento real) — determinístico. A
projeção estatística do não-comprado é um motor separado (não se mistura). As
janelas respondem "quanto vou desembolsar nos próximos 7/15/30/60/90 dias".
"""
from __future__ import annotations

from datetime import date, timedelta

JANELAS = (7, 15, 30, 60, 90)


def _pago(situacao: str | None) -> bool:
    # "A pagar" contém "paga" (de paGAR); casa palavra inteira p/ não confundir.
    palavras = (situacao or "").lower().replace("(", " ").replace(")", " ").split()
    return any(p in {"paga", "pago", "pagas", "quitada", "quitado"} for p in palavras)


def previsao(dados: dict, hoje: date | None = None) -> dict:
    """
    Desembolso comprometido por janela + vencidas + por fornecedor.
    `dados` = conteúdo de desembolso_{pid}.json.
    """
    hoje = hoje or date.today()
    parcelas = dados.get("parcelas") or []

    a_pagar = []
    for p in parcelas:
        if _pago(p.get("situacao")):
            continue
        d = p.get("data_venc")
        if not d:
            continue
        try:
            venc = date.fromisoformat(d)
        except ValueError:
            continue
        a_pagar.append((venc, float(p.get("valor") or 0), p.get("fornecedor_id")))

    vencidas = round(sum(v for venc, v, _ in a_pagar if venc < hoje), 2)
    janelas = {}
    for n in JANELAS:
        limite = hoje + timedelta(days=n)
        janelas[f"{n}d"] = round(sum(v for venc, v, _ in a_pagar
                                     if hoje <= venc <= limite), 2)

    # top fornecedores no horizonte de 30 dias
    lim30 = hoje + timedelta(days=30)
    por_forn: dict[int, float] = {}
    for venc, v, forn in a_pagar:
        if hoje <= venc <= lim30 and forn:
            por_forn[forn] = por_forn.get(forn, 0.0) + v
    top_forn = sorted(({"fornecedor_id": k, "valor": round(v, 2)}
                       for k, v in por_forn.items()), key=lambda x: -x["valor"])[:10]

    return {
        "total_a_pagar": round(sum(v for _, v, _ in a_pagar), 2),
        "vencidas": vencidas,
        "janelas": janelas,
        "top_fornecedores_30d": top_forn,
        "n_parcelas": len(a_pagar),
    }
