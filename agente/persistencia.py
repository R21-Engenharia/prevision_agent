"""
Persistência das Pendências Inteligentes no Supabase.
=====================================================
Grava com DEDUP: a mesma pendência aberta (obra + wbs + categoria) não é
recriada. Se já existe e mudou (impacto/percentuais), atualiza; se é nova,
insere + gera as perguntas + registra o evento "criada" no histórico.

Nada é sobrescrito de forma destrutiva — respostas e histórico só acumulam.
Requer SUPABASE_URL e SUPABASE_KEY no ambiente (mesmas do snapshot diário).
"""
from __future__ import annotations

import os
import re

from agente.motor import Pendencia
from agente.perguntas import perguntas_para

try:
    from supabase import create_client
    _HAS = True
except ImportError:
    _HAS = False


def _cliente():
    url, key = os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_KEY", "")
    if not (_HAS and url and key):
        raise RuntimeError(
            "Supabase não configurado (defina SUPABASE_URL/SUPABASE_KEY e "
            "instale supabase>=2.0.0).")
    return create_client(url, key)


def _mapa_regras(cli) -> dict[str, int]:
    """categoria -> rule_id (para ligar a pendência à regra que a gerou)."""
    r = cli.table("priority_rules").select("id, codigo").execute()
    return {row["codigo"]: row["id"] for row in (r.data or [])}


def _pav_curto(nome: str) -> str:
    m = re.match(r"^\d+\s*º", nome or "")
    return m.group(0).replace(" ", "") if m else (nome or "")


def _ctx(p: Pendencia) -> dict:
    trava = p.causa_raiz.get("trava", []) or []
    travados = ""
    if trava:
        amostra = ", ".join(
            f"{t.get('servico') or '?'} ({_pav_curto(t.get('pavimento', ''))})"
            for t in trava[:3])
        travados = f" — como {amostra}"
    return {
        "wbs": p.wbs_code, "servico": p.servico or p.wbs_code, "pavimento": p.pavimento or "—",
        "pct_real": p.pct_real, "pct_esperado": p.pct_esperado, "impacto": p.impacto,
        "predecessor": p.causa_raiz.get("predecessor_wbs", ""),
        "predecessor_servico": p.causa_raiz.get("predecessor_servico") or "o serviço anterior",
        "pred_pct": p.causa_raiz.get("pred_pct", 0),
        "travados": travados,
    }


ABERTAS = ("aberta", "respondida", "em_tratamento")


def salvar_pendencias(obra: str, pendencias: list[Pendencia]) -> int:
    """Insere/atualiza as pendências da obra. Devolve quantas foram tocadas."""
    cli = _cliente()
    regras = _mapa_regras(cli)

    # Dedup do lote: o WBS pode repetir entre "partes" da atividade, mas a
    # pendência é única por (obra, wbs, categoria). Mantém a de maior peso.
    unicas: dict[tuple, Pendencia] = {}
    for p in pendencias:
        k = (p.wbs_code, p.categoria)
        atual = unicas.get(k)
        if atual is None or (p.severidade, p.impacto) > (atual.severidade, atual.impacto):
            unicas[k] = p
    pendencias = list(unicas.values())

    # Pendências já abertas desta obra, indexadas por (wbs, categoria)
    r = (cli.table("pendencias")
         .select("id, wbs_code, categoria, impacto, pct_real, status")
         .eq("obra", obra).in_("status", list(ABERTAS)).execute())
    existentes = {(x["wbs_code"], x["categoria"]): x for x in (r.data or [])}

    tocadas = 0
    for p in pendencias:
        chave = (p.wbs_code, p.categoria)
        registro = {
            "obra": obra, "wbs_code": p.wbs_code, "activity_id": p.activity_id,
            "servico": p.servico, "pavimento": p.pavimento,
            "rule_id": regras.get(p.categoria),
            "categoria": p.categoria, "causa_raiz": p.causa_raiz,
            "impacto": p.impacto, "severidade": p.severidade,
            "pct_real": p.pct_real, "pct_esperado": p.pct_esperado,
        }

        atual = existentes.pop(chave, None)
        if atual is None:
            # Nova pendência
            novo = cli.table("pendencias").insert(registro).execute().data[0]
            pid = novo["id"]
            perguntas = perguntas_para(p.categoria, _ctx(p))
            if perguntas:
                cli.table("pendencia_perguntas").insert([
                    {"pendencia_id": pid, "texto": q, "ordem": i, "origem": "template"}
                    for i, q in enumerate(perguntas)
                ]).execute()
            _historico(cli, pid, obra, "criada", {"categoria": p.categoria, "impacto": p.impacto})
            tocadas += 1
        elif atual["impacto"] != p.impacto or abs((atual["pct_real"] or 0) - p.pct_real) > 0.5:
            # Mudou o quadro — atualiza sem apagar histórico
            cli.table("pendencias").update({
                "impacto": p.impacto, "pct_real": p.pct_real,
                "pct_esperado": p.pct_esperado, "causa_raiz": p.causa_raiz,
            }).eq("id", atual["id"]).execute()
            _historico(cli, atual["id"], obra, "status_alterado",
                       {"impacto_novo": p.impacto, "pct_real_novo": p.pct_real})
            tocadas += 1

    # O que sobrou em `existentes` não foi mais detectado → resolvido em campo.
    for (_wbs, _cat), x in existentes.items():
        cli.table("pendencias").update(
            {"status": "resolvida", "encerrada_em": "now()"}).eq("id", x["id"]).execute()
        _historico(cli, x["id"], obra, "encerrada", {"motivo": "não mais detectada"})

    return tocadas


def _historico(cli, pendencia_id: int, obra: str, evento: str, detalhe: dict) -> None:
    cli.table("pendencia_historico").insert({
        "pendencia_id": pendencia_id, "obra": obra, "evento": evento,
        "detalhe": detalhe, "usuario_email": "",  # vazio = ação automática do agente
    }).execute()
