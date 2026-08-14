"""
custos/desembolso.py
====================
Previsão de desembolso a partir das parcelas a pagar (desembolso_{pid}.json).

Só o COMPROMETIDO (parcela agendada, com vencimento real) — determinístico. A
projeção estatística do não-comprado é um motor separado (não se mistura). As
janelas respondem "quanto vou desembolsar nos próximos 7/15/30/60/90 dias".
"""
from __future__ import annotations

import unicodedata
from datetime import date, timedelta

JANELAS = (7, 15, 30, 60, 90)

# Classificação do desembolso pela NATUREZA do título (tipo de documento do Sienge).
# É o CAIXA TOTAL da obra — todos os títulos do centro de custo. A honestidade importa:
# a maior parte (PRV/PCT) são PROVISÕES e PARCELAS DE CONTRATO de empreiteiro, ainda
# SEM nota fiscal — não dá pra fatiar em serviço/material com segurança, então ficam
# num balde próprio "Provisão/Contrato". Só o que tem NOTA FISCAL é classificado como
# material ou serviço (aí sim é confiável).
_CATEGORIA = {
    "Provisão/Contrato": {"PRV", "PCT", "PPC", "MED", "CT", "CTR"},   # medição/contrato sem NF
    "Material (NF)": {"NFE", "NF", "NFSR", "CTE", "CTRC"},            # nota fiscal de material
    "Serviço (NF)": {"NFS", "NFSE", "RPA"},                          # nota fiscal de serviço
    "Imposto": {"DARF", "DARM", "GPS", "GARE", "GNRE", "ISS", "DAE",
                "GRF", "FGTS", "INSS", "GRRF", "GUIA", "DAM"},
    "Adiantamento": {"ADTO", "ADT", "ADM"},
}
_DOC2CAT = {doc: cat for cat, docs in _CATEGORIA.items() for doc in docs}


def _categoria(doc_tipo: str | None) -> str:
    """Natureza do título a partir do tipo de documento (fallback: Outros)."""
    return _DOC2CAT.get((doc_tipo or "").strip().upper(), "Outros")


def _pago(situacao: str | None) -> bool:
    """
    True só quando a parcela está QUITADA. Cuidado com as armadilhas do português:
    "Não paga" e "A pagar" contêm "paga"/"pagar" mas NÃO estão pagas. Só conta como
    pago "Totalmente paga"/"quitada" (Parcialmente paga ainda tem saldo → a pagar).
    """
    s = unicodedata.normalize("NFKD", (situacao or "").lower()).encode("ascii", "ignore").decode()
    if "nao" in s.split():          # "não paga" → não pago
        return False
    return "totalmente pag" in s or "quitad" in s


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
        a_pagar.append((venc, float(p.get("valor") or 0), p.get("fornecedor_id"),
                        _categoria(p.get("doc_tipo"))))

    vencidas = round(sum(v for venc, v, _, _ in a_pagar if venc < hoje), 2)
    janelas = {}
    for n in JANELAS:
        limite = hoje + timedelta(days=n)
        janelas[f"{n}d"] = round(sum(v for venc, v, _, _ in a_pagar
                                     if hoje <= venc <= limite), 2)

    # top fornecedores no horizonte de 30 dias
    lim30 = hoje + timedelta(days=30)
    por_forn: dict[int, float] = {}
    for venc, v, forn, _ in a_pagar:
        if hoje <= venc <= lim30 and forn:
            por_forn[forn] = por_forn.get(forn, 0.0) + v
    top_forn = sorted(({"fornecedor_id": k, "valor": round(v, 2)}
                       for k, v in por_forn.items()), key=lambda x: -x["valor"])[:10]

    # quebra do desembolso por natureza (Serviço/Material/Imposto/...) — o caixa é
    # total, mas o executivo precisa ver a composição (material é minoria)
    total_ap = sum(v for _, v, _, _ in a_pagar) or 1
    cat_tot: dict[str, float] = {}
    cat_30d: dict[str, float] = {}
    for venc, v, _, cat in a_pagar:
        cat_tot[cat] = cat_tot.get(cat, 0.0) + v
        if hoje <= venc <= lim30:
            cat_30d[cat] = cat_30d.get(cat, 0.0) + v
    por_categoria = sorted(
        ({"categoria": c, "total": round(t, 2), "d30": round(cat_30d.get(c, 0.0), 2),
          "pct": round(100 * t / total_ap, 1)} for c, t in cat_tot.items()),
        key=lambda x: -x["total"])

    return {
        "total_a_pagar": round(sum(v for _, v, _, _ in a_pagar), 2),
        "vencidas": vencidas,
        "janelas": janelas,
        "por_categoria": por_categoria,
        "top_fornecedores_30d": top_forn,
        "n_parcelas": len(a_pagar),
    }
