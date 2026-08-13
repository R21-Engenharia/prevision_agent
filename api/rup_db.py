"""
Acesso à Camada 1 da RUP (Hh por FVS) — tabela rup_hh_fvs no Supabase.
=====================================================================
Mesmo estilo de api/agente_db.py: fala com o PostgREST por httpx; a
autorização por obra é aplicada na camada da API (o chamador já vem
autenticado por usuario_e_obra).

Fallback de desenvolvimento: se o Supabase não estiver configurado (ou a
tabela ainda não existir), lê o consolidado local data/rup_camada1.json —
assim a tela roda em dev antes da tabela ser criada em produção.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import httpx
from fastapi import HTTPException

_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
_KEY = os.getenv("SUPABASE_KEY", "")

_RAIZ = Path(__file__).resolve().parent.parent
_JSON_LOCAL = _RAIZ / "data" / "rup_camada1.json"

# Colunas expostas pela tela (inclui as do denominador, ainda nulas até o Sienge).
_SELECT = ("obra,fvs_codigo,fvs_nome,hh_total,dias_trabalhados,efetivo_medio_dia,"
           "n_pavimentos,pavimentos,hh_por_funcao,pct_compartilhado,"
           "unidade,qtd_executada,eap_referencia,eap_descricao,depara_status,"
           "rup_real,atualizado_em")


def _do_json(obra: str) -> list[dict]:
    if not _JSON_LOCAL.exists():
        return []
    dados = json.loads(_JSON_LOCAL.read_text(encoding="utf-8"))
    linhas = [r for r in dados.get("fvs", []) if r.get("obra") == obra]
    linhas.sort(key=lambda r: -(r.get("hh_total") or 0))
    return linhas


async def camada1(obra: str) -> list[dict]:
    """Hh por FVS da obra, maior consumo primeiro. Supabase → fallback JSON.

    Para as FVS com de-para confirmado, a quantidade executada e a RUP são
    recalculadas AO VIVO a partir da EAP atual (o número acompanha o avanço da
    obra, em vez de congelar no momento da confirmação).
    """
    if not (_URL and _KEY):
        return _enriquecer_rup(obra, _do_json(obra))
    base = f"{_URL}/rest/v1"
    headers = {"apikey": _KEY, "Authorization": f"Bearer {_KEY}"}
    params = {"obra": f"eq.{obra}", "order": "hh_total.desc", "select": _SELECT}
    try:
        async with httpx.AsyncClient(timeout=15) as cli:
            r = await cli.get(f"{base}/rup_hh_fvs", params=params, headers=headers)
        if r.status_code >= 400:
            return _enriquecer_rup(obra, _do_json(obra))  # tabela ainda não criada
        linhas = r.json() or _do_json(obra)
    except Exception:
        linhas = _do_json(obra)
    return _enriquecer_rup(obra, linhas)


def resumo(linhas: list[dict]) -> dict:
    """Totais da obra para os cartões do topo da tela."""
    hh = sum(l.get("hh_total") or 0 for l in linhas)
    com_rup = sum(1 for l in linhas if l.get("rup_real") is not None)
    confirmados = sum(1 for l in linhas if l.get("depara_status") == "confirmado")
    return {
        "fvs": len(linhas),
        "hh_total": round(hh, 1),
        "com_rup": com_rup,                 # quantas já têm denominador (Sienge)
        "aguardando_sienge": len(linhas) - com_rup,
        "depara_confirmados": confirmados,  # quantas FVS já amarradas na EAP
    }


# ── De-para FVS → EAP (Sienge) ───────────────────────────────────────────────

def _pid_da_obra(obra: str) -> int | None:
    from fvs_dashboard.core.data_manager import OBRAS
    cfg = OBRAS.get(obra)
    return cfg["prevision_id"] if cfg else None


def _eap_da_obra(obra: str) -> list[dict]:
    pid = _pid_da_obra(obra)
    if not pid:
        return []
    f = _RAIZ / "data" / f"eap_{pid}.json"
    if not f.exists():
        return []
    return json.loads(f.read_text(encoding="utf-8")).get("itens", [])


def _grupos_da_obra(obra: str) -> dict[str, dict]:
    """Serviços da EAP agrupados por descrição (quantidade já somada), por chave."""
    from rup.depara import agrupar_servicos
    return {g["descricao"]: g for g in agrupar_servicos(_eap_da_obra(obra))}


def _rup_de(hh: float | None, grupo: dict | None) -> dict:
    """Calcula qtd executada + RUP para uma FVS a partir do serviço amarrado."""
    if not grupo or not grupo.get("qtd_executada"):
        return {"qtd_executada": None, "unidade": grupo.get("unidade") if grupo else None,
                "rup_real": None}
    q = grupo["qtd_executada"]
    return {
        "qtd_executada": round(q, 2),
        "unidade": grupo.get("unidade"),
        "rup_real": round((hh or 0) / q, 3) if q else None,
    }


def _enriquecer_rup(obra: str, linhas: list[dict]) -> list[dict]:
    """Preenche qtd_executada/unidade/rup_real ao vivo nas FVS confirmadas."""
    confirmadas = [l for l in linhas if l.get("depara_status") == "confirmado"
                   and l.get("eap_descricao")]
    if not confirmadas:
        return linhas
    grupos = _grupos_da_obra(obra)
    for l in confirmadas:
        calc = _rup_de(l.get("hh_total"), grupos.get(l["eap_descricao"]))
        l.update(calc)
    return linhas


async def depara(obra: str) -> list[dict]:
    """
    Por FVS: o vínculo confirmado (com RUP ao vivo) + os melhores SERVIÇOS
    candidatos (agrupados, quantidade somada, com prévia de RUP). O humano
    confirma; nada é decidido só.
    """
    from rup.depara import sugerir_servicos, confianca

    linhas = await camada1(obra)
    grupos = list(_grupos_da_obra(obra).values())
    saida = []
    for l in linhas:
        hh = l.get("hh_total")
        nome = re.sub(r"^FVS\s+[\d.]+\s*-\s*", "", l.get("fvs_nome", ""))
        cands = sugerir_servicos(nome, grupos, 3) if grupos else []
        # anexa a prévia de RUP em cada candidato
        for c in cands:
            c["rup_previa"] = _rup_de(hh, c)["rup_real"]
        confirmado = None
        if l.get("depara_status") == "confirmado":
            confirmado = {
                "eap_descricao": l.get("eap_descricao"),
                "unidade": l.get("unidade"),
                "qtd_executada": l.get("qtd_executada"),
                "rup_real": l.get("rup_real"),
            }
        saida.append({
            "fvs_codigo": l["fvs_codigo"],
            "fvs_nome": l["fvs_nome"],
            "hh_total": hh,
            "status": l.get("depara_status") or "pendente",
            "confirmado": confirmado,
            "confianca": confianca(cands),
            "sugestoes": cands,
        })
    return saida


def _serie_mensal(obra: str) -> dict[str, dict]:
    """célula → {mês: {hh, producao}} — série mensal p/ análise por janela."""
    pid = _pid_da_obra(obra)
    f = _RAIZ / "data" / f"rup_mensal_{pid}.json" if pid else None
    if not f or not f.exists():
        return {}
    return json.loads(f.read_text(encoding="utf-8")).get("celulas", {})


async def hierarquia(obra: str, janela: str = "obra", so_monitorados: bool = True) -> dict:
    """
    Árvore Célula → Pacote com RUP consolidada (HH total ÷ produção total) e a
    faixa de referência do parceiro por célula. HH vem do de-para (confirmado
    quando houver, senão a melhor sugestão do matcher — marcado em `fonte_hh`).

    `janela` (mes_atual|mes_anterior|6m|12m|obra): quando ≠ obra, a RUP de cada
    célula é RECALCULADA só com os meses da janela (série mensal), com variação
    vs a janela anterior. A produção acumulada e o R$ em risco continuam do total.
    """
    import re as _re
    from collections import defaultdict
    from rup.depara import agrupar_servicos, sugerir_servicos
    from rup.hierarquia import producao_por_pacote, celula_de, pacote_de, montar
    from rup import referencia

    linhas = await camada1(obra)
    eap = _eap_da_obra(obra)
    prod = producao_por_pacote(eap)
    grupos = list(agrupar_servicos(eap))

    hh_pac: dict[tuple[str, str], float] = defaultdict(float)
    algum_confirmado = False
    for l in linhas:
        nome = _re.sub(r"^FVS\s+[\d.]+\s*-\s*", "", l.get("fvs_nome", ""))
        cel = celula_de(nome)
        if l.get("depara_status") == "confirmado" and l.get("eap_descricao"):
            pac = pacote_de(l["eap_descricao"])
            algum_confirmado = True
        else:
            cand = sugerir_servicos(nome, grupos, 1) if grupos else []
            pac = pacote_de(cand[0]["descricao"]) if cand else "outros"
        hh_pac[(cel, pac)] += l.get("hh_total") or 0

    arvore = montar(hh_pac, prod)

    if so_monitorados:
        from rup.hierarquia import CELULAS_MONITORADAS
        arvore = [c for c in arvore if c["celula"] in CELULAS_MONITORADAS]

    # Janela de tempo: recalcula a RUP de cada célula só com os meses da janela.
    if janela and janela != "obra":
        from rup import janela as _jan
        serie = _serie_mensal(obra)
        for c in arvore:
            jc = _jan.com_variacao(serie.get(c["celula"], {}), janela)
            c["rup"] = jc["rup"]
            c["hh"] = jc["hh"]
            c["producao"] = jc["producao"]
            c["rup_anterior"] = jc["rup_anterior"]
            c["variacao_abs"] = jc["variacao_abs"]
            c["variacao_pct"] = jc["variacao_pct"]
            c["tendencia"] = jc["tendencia"]

    bandas = referencia.bandas_por_disciplina()
    for c in arvore:
        b = bandas.get(c["celula"])
        c["banda"] = b
        c["status"] = referencia.status(c.get("rup"), b)
        for p in c["pacotes"]:
            p["status"] = referencia.status(p.get("rup"), b)
    arvore.sort(key=lambda c: -(c["hh"] or 0))

    dentro = sum(1 for c in arvore if c["status"] == "dentro")
    com_rup = sum(1 for c in arvore if c.get("rup") is not None)
    return {
        "obra": obra, "janela": janela,
        "resumo": {"celulas": len(arvore), "com_rup": com_rup, "dentro_faixa": dentro,
                   "fonte_hh": "confirmado" if algum_confirmado else "sugerido"},
        "celulas": arvore,
    }


async def confirmar(obra: str, fvs_codigo: str, grupo: dict) -> None:
    """
    Grava o vínculo FVS→SERVIÇO escolhido pelo revisor. Guarda a descrição do
    serviço (chave do grupo) + as referências Sienge somadas; a quantidade e a
    RUP são recalculadas ao vivo na leitura (não congelam).
    """
    if not (_URL and _KEY):
        raise HTTPException(503, "Confirmação exige Supabase configurado (a tabela "
                                 "rup_hh_fvs). Em dev o de-para é só leitura.")
    refs = grupo.get("refs") or []
    base = f"{_URL}/rest/v1"
    headers = {"apikey": _KEY, "Authorization": f"Bearer {_KEY}",
               "Content-Type": "application/json", "Prefer": "return=representation"}
    body = {
        "eap_descricao": grupo.get("descricao"),
        "eap_referencia": ",".join(str(r) for r in refs),
        "unidade": grupo.get("unidade"),
        "depara_status": "confirmado",
    }
    params = {"obra": f"eq.{obra}", "fvs_codigo": f"eq.{fvs_codigo}"}
    try:
        async with httpx.AsyncClient(timeout=20) as cli:
            r = await cli.patch(f"{base}/rup_hh_fvs", params=params, json=body, headers=headers)
    except Exception as exc:  # noqa: BLE001 — nunca deixa virar 502 cru
        raise HTTPException(502, f"Erro de conexão com o banco ao confirmar: {exc}")
    if r.status_code >= 400:
        raise HTTPException(502, f"Banco recusou a confirmação ({r.status_code}): {r.text[:140]}")
    linhas = r.json() if r.text else []
    if not linhas:
        raise HTTPException(409, "A tabela rup_hh_fvs ainda não tem esta FVS — é preciso "
                                 "rodar o coletor (coletar_rdo_efetivo.py --supabase) para "
                                 "popular a base antes de confirmar.")
