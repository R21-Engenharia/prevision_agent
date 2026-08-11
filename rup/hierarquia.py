"""
rup/hierarquia.py
=================
Consolidação hierárquica das RUPs — genérica para qualquer célula construtiva.

    Célula Construtiva → Pacote de Serviço → Lote/Pavimento

Regra de ouro (definição do Elrik): a RUP de cada nível é sempre
    RUP = HH total ÷ Produção total
NUNCA a média das RUPs dos níveis abaixo. A linha de cima sempre totaliza as de
baixo, ponderando pela produção.

Fontes:
  • Produção por lote  → Sienge (cada linha de orçamento = um lote; a descrição
    "MOE - {CÉLULA} / {PACOTE}" dá célula e pacote; o WBS dá o lote).
  • HH                 → RDO (efetivo × 8,8h), atribuído ao pacote via de-para.
  • Lote (identidade)  → Prevision/RDO (pavimento) — plugado na Fase 2 do lote.

Este módulo monta Célula→Pacote agora; o Lote entra quando a produção do Sienge
for amarrada ao pavimento do Prevision.
"""
from __future__ import annotations

import re
from collections import defaultdict

_RE_CEL_PAC = re.compile(r"^\s*MOE\s*-\s*([^/]+?)\s*/\s*(.+)$", re.IGNORECASE)


def celula_de(texto: str) -> str:
    """
    Célula construtiva = disciplina do serviço (alvenaria, reboco, forma...).
    Chave robusta e simétrica: funciona igual pro nome da FVS (RDO) e pra
    descrição do item Sienge, ao contrário do texto "MOE - X / Y" que é
    inconsistente. Devolve 'outros' quando nenhuma disciplina bate.
    """
    from rup.depara import disciplinas_de
    d = disciplinas_de(texto)
    return sorted(d)[0] if d else "outros"


def pacote_de(descricao: str) -> str:
    """Nome do pacote (serviço específico) a partir da descrição do Sienge."""
    m = _RE_CEL_PAC.match(descricao or "")
    if m:
        return m.group(2).split("/")[0].strip()
    return re.sub(r"^\s*MOE\s*-\s*", "", descricao or "").strip() or "Outros"


def _lote_de_wbs(wbs: str | None) -> str:
    """Lote = 3º segmento do WBS Sienge (identidade provisória até o Prevision)."""
    s = str(wbs or "").split(".")
    return s[2] if len(s) >= 3 else "?"


def producao_por_pacote(eap: list[dict], apenas_mo: bool = True) -> dict[tuple[str, str], dict]:
    """
    Agrega a produção (qtd executada e orçada) por (célula, pacote), guardando os
    lotes. Só itens com unidade física fazem sentido pra RUP.
    """
    fisica = {"m2", "m3", "m", "kg", "un", "pto", "pt", "unid"}
    out: dict[tuple[str, str], dict] = defaultdict(lambda: {
        "celula": "", "pacote": "", "unidade": None,
        "qtd_executada": 0.0, "qtd_orcada": 0.0, "lotes": {}})
    for e in eap:
        if apenas_mo and not e.get("mao_de_obra"):
            continue
        if e.get("unidade_sienge") not in fisica:
            continue
        desc = e.get("descricao", "")
        cel, pac = celula_de(desc), pacote_de(desc)
        g = out[(cel, pac)]
        g["celula"], g["pacote"] = cel, pac
        g["unidade"] = e.get("unidade_sienge") or g["unidade"]
        qe = e.get("qtd_executada") or 0.0
        qo = e.get("qtd_orcada") or 0.0
        g["qtd_executada"] += qe
        g["qtd_orcada"] += qo
        lote = _lote_de_wbs(e.get("wbs_sienge"))
        g["lotes"][lote] = g["lotes"].get(lote, 0.0) + qe
    return out


def _rup(hh: float, prod: float) -> float | None:
    # Sem produção OU sem HH atribuído → RUP indefinida (None), nunca 0. HH=0 com
    # produção>0 significa lacuna de atribuição, não produtividade infinitamente boa.
    return round(hh / prod, 3) if (prod and hh) else None


def montar(
    fvs_hh_por_pacote: dict[tuple[str, str], float],
    producao: dict[tuple[str, str], dict],
    horas_dia: float = 8.8,
) -> list[dict]:
    """
    Monta a árvore Célula → Pacote consolidando HH e produção.

    fvs_hh_por_pacote: (célula, pacote) -> HH total (já atribuído pelo de-para).
    producao:          saída de producao_por_pacote.
    Devolve lista de células, cada uma com seus pacotes, HH/produção/RUP em todos
    os níveis — sempre HH_total ÷ Produção_total.
    """
    # une as chaves dos dois lados
    chaves = set(producao) | set(fvs_hh_por_pacote)
    celulas: dict[str, dict] = defaultdict(lambda: {
        "celula": "", "hh": 0.0, "producao": 0.0, "unidade": None, "pacotes": []})

    for chave in chaves:
        cel, pac = chave
        prod = producao.get(chave, {})
        hh = fvs_hh_por_pacote.get(chave, 0.0)
        qexec = prod.get("qtd_executada", 0.0)
        pacote = {
            "pacote": pac,
            "hh": round(hh, 1),
            "producao": round(qexec, 2),
            "unidade": prod.get("unidade"),
            "rup": _rup(hh, qexec),
            "qtd_orcada": round(prod.get("qtd_orcada", 0.0), 2),
            "n_lotes": len(prod.get("lotes", {})),
        }
        c = celulas[cel]
        c["celula"] = cel
        c["hh"] += hh
        c["producao"] += qexec
        c["unidade"] = pacote["unidade"] or c["unidade"]
        c["pacotes"].append(pacote)

    saida = []
    for c in celulas.values():
        # Consolidação UNIDADE-AWARE: não se soma m² com un. A produção da célula
        # é a da unidade dominante (a que mais produziu); pacotes de outra unidade
        # entram no detalhe mas não no total. Célula sem produção física → RUP None.
        prod_por_un: dict[str, float] = defaultdict(float)
        hh_por_un: dict[str, float] = defaultdict(float)
        for p in c["pacotes"]:
            if p["unidade"] and p["producao"]:
                prod_por_un[p["unidade"]] += p["producao"]
                hh_por_un[p["unidade"]] += p["hh"] or 0
        c["hh"] = round(c["hh"], 1)
        if prod_por_un:
            un_dom = max(prod_por_un, key=prod_por_un.get)
            c["unidade"] = un_dom
            c["producao"] = round(prod_por_un[un_dom], 2)
            # HH da unidade dominante ÷ produção dominante (totais, nunca média)
            c["rup"] = _rup(hh_por_un[un_dom], prod_por_un[un_dom])
            c["unidades_mistas"] = len(prod_por_un) > 1
        else:
            c["producao"] = 0.0
            c["rup"] = None          # só "vb"/sem produção física → não inventa RUP
            c["unidades_mistas"] = False
        c["pacotes"].sort(key=lambda p: -(p["hh"] or 0))
        saida.append(c)
    saida.sort(key=lambda c: -(c["hh"] or 0))
    return saida
