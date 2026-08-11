"""
rup/parser_rdo.py
=================
Extrai, de UM RDO detalhado do InMeta, os registros de efetivo por servico.

Regra de negocio (confirmada pelo Elrik, 2026-08-10):
  Hora nao e lancada. Assume-se que quem esteve num servico no dia ficou 8,8h
  (media de horas/dia por colaborador). Logo:

      Hh_bruto(colaborador) = 8,8h

  Efetivo compartilhado: se a MESMA pessoa aparece em N servicos no mesmo RDO,
  as 8,8h dela sao divididas entre os N servicos (8,8 / N). Sem isso, uma pessoa
  em 3 frentes viraria 26,4h no dia — inflando a RUP. Essa divisao mantem a soma
  do dia fiel ao efetivo real e alimenta a Camada 3 (confianca): quanto maior o
  compartilhamento, menor a confianca da amostra.

Cada registro emitido representa "servico S, no pavimento P, no dia D":
    obra, data, fvs_codigo, fvs_nome, servico_id, pavimentos[],
    colaboradores[{nome, funcao, hh}], hh_total, efetivo, compartilhado
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any, Iterable

HORAS_DIA = 8.8  # media de horas trabalhadas por colaborador/dia

_ITEM_EQUIPE_DIA = "Equipe envolvida"
_ITENS_SERVICO   = ("Servicos controlados", "Serviços controlados")

# "FVS 09.01.03 - Execucao Reboco Interno - Shaft Hall" -> "09.01.03"
_RE_FVS = re.compile(r"FVS\s+([\d.]+)", re.IGNORECASE)


def _por_nome(itens: list[dict]) -> dict[str, dict]:
    return {it.get("nome"): it for it in itens or []}


def mapa_funcoes(detalhe: dict) -> dict[str, str]:
    """
    nome -> cargo, a partir do item "Equipe envolvida" (lista do dia).
    O cadastro guarda a funcao; o RDO por servico so traz o nome, entao esse
    mapa e a ponte nome->funcao.
    """
    it = _por_nome(detalhe.get("itens", [])).get(_ITEM_EQUIPE_DIA, {})
    mapa: dict[str, str] = {}
    for col in it.get("respostaColaboradores") or []:
        nome = (col.get("pessoa") or {}).get("nome")
        if nome:
            mapa[nome] = (col.get("cargo") or "").strip() or "Nao informado"
    return mapa


def _fvs_codigo(nome: str) -> str | None:
    m = _RE_FVS.search(nome or "")
    return m.group(1) if m else None


def _linhas_servico(detalhe: dict) -> Iterable[dict]:
    itens = _por_nome(detalhe.get("itens", []))
    for chave in _ITENS_SERVICO:
        it = itens.get(chave)
        if it:
            yield from (it.get("respostaBaseDados") or [])


def registros_do_rdo(detalhe: dict, obra: str) -> list[dict]:
    """
    Converte um RDO detalhado em registros de efetivo por servico, ja com o
    split das 8,8h entre servicos compartilhados pela mesma pessoa.
    So emite linhas com codigo FVS reconhecido (a amarracao da celula).
    """
    data = (detalhe.get("dataInspecao") or "")[:10]
    funcoes = mapa_funcoes(detalhe)

    linhas = list(_linhas_servico(detalhe))

    # 1) conta em quantos servicos cada pessoa aparece neste RDO (para o split)
    aparicoes: Counter[str] = Counter()
    parsed: list[dict] = []
    for row in linhas:
        serv = (row.get("Servico") or row.get("Serviço") or {}).get("servico") or []
        if not serv:
            continue
        fvs_nome = serv[0].get("nome", "")
        codigo = _fvs_codigo(fvs_nome)
        if not codigo:
            continue  # linha sem FVS reconhecida — fora da amarracao
        locais = [l.get("nome", "") for l in
                  (row.get("Local(is)") or {}).get("local") or []]
        equipe = [(c.get("pessoa") or {}).get("nome")
                  for c in (row.get("Equipe") or {}).get("colaborador") or []]
        equipe = [n for n in equipe if n]
        for n in equipe:
            aparicoes[n] += 1
        parsed.append({
            "fvs_codigo": codigo,
            "fvs_nome": fvs_nome,
            "servico_id": serv[0].get("_id"),
            "pavimentos": locais,
            "equipe": equipe,
        })

    # 2) monta os registros com Hh ja rateado
    out: list[dict] = []
    for p in parsed:
        colaboradores = []
        compartilhado = False
        for nome in p["equipe"]:
            n_serv = aparicoes[nome] or 1
            if n_serv > 1:
                compartilhado = True
            colaboradores.append({
                "nome": nome,
                "funcao": funcoes.get(nome, "Nao informado"),
                "hh": round(HORAS_DIA / n_serv, 3),
            })
        out.append({
            "obra": obra,
            "data": data,
            "fvs_codigo": p["fvs_codigo"],
            "fvs_nome": p["fvs_nome"],
            "servico_id": p["servico_id"],
            "pavimentos": p["pavimentos"],
            "colaboradores": colaboradores,
            "efetivo": len(colaboradores),
            "hh_total": round(sum(c["hh"] for c in colaboradores), 3),
            "compartilhado": compartilhado,
        })
    return out
