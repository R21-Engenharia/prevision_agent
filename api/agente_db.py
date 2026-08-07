"""
Acesso às tabelas do Agente Inteligente no Supabase (via REST).
===============================================================
A API não usa o cliente supabase-py aqui — fala direto com o PostgREST por
httpx, no mesmo estilo do api/auth.py. RLS está aberto (agente_service_all),
então a autorização por obra é aplicada na camada da API (o chamador já vem
autenticado por usuario_atual).
"""
from __future__ import annotations

import os

import httpx
from fastapi import HTTPException

_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
_KEY = os.getenv("SUPABASE_KEY", "")


def _cfg() -> tuple[str, dict]:
    if not (_URL and _KEY):
        raise HTTPException(503, "Banco do agente não configurado (SUPABASE_URL/KEY).")
    base = f"{_URL}/rest/v1"
    headers = {"apikey": _KEY, "Authorization": f"Bearer {_KEY}",
               "Content-Type": "application/json"}
    return base, headers


async def _get(path: str, params: dict) -> list[dict]:
    base, headers = _cfg()
    async with httpx.AsyncClient(timeout=15) as cli:
        r = await cli.get(f"{base}/{path}", params=params, headers=headers)
    if r.status_code >= 400:
        raise HTTPException(502, f"Falha ao ler {path} ({r.status_code}).")
    return r.json()


async def _post(path: str, body, prefer: str = "return=representation") -> list[dict]:
    base, headers = _cfg()
    async with httpx.AsyncClient(timeout=15) as cli:
        r = await cli.post(f"{base}/{path}", json=body,
                           headers={**headers, "Prefer": prefer})
    if r.status_code >= 400:
        raise HTTPException(502, f"Falha ao gravar em {path} ({r.status_code}).")
    return r.json() if r.text else []


async def _patch(path: str, params: dict, body: dict) -> None:
    base, headers = _cfg()
    async with httpx.AsyncClient(timeout=15) as cli:
        r = await cli.patch(f"{base}/{path}", params=params, json=body, headers=headers)
    if r.status_code >= 400:
        raise HTTPException(502, f"Falha ao atualizar {path} ({r.status_code}).")


# ── Consultas ────────────────────────────────────────────────────────────────

async def listar(obra: str, status: str | None, categoria: str | None) -> list[dict]:
    p = {"obra": f"eq.{obra}", "order": "severidade.desc,impacto.desc",
         "select": "id,wbs_code,servico,categoria,severidade,impacto,pct_real,pct_esperado,"
                   "status,pavimento,causa_raiz,responsavel_nome,detectada_em"}
    if status:
        p["status"] = f"eq.{status}"
    if categoria:
        p["categoria"] = f"eq.{categoria}"
    return await _get("pendencias", p)


async def detalhe(pendencia_id: int, obra: str) -> dict:
    ped = await _get("pendencias", {"id": f"eq.{pendencia_id}", "obra": f"eq.{obra}", "limit": "1"})
    if not ped:
        raise HTTPException(404, "Pendência não encontrada.")
    perguntas = await _get("pendencia_perguntas",
                           {"pendencia_id": f"eq.{pendencia_id}", "order": "ordem.asc",
                            "select": "id,texto,ordem,origem"})
    respostas = await _get("pendencia_respostas",
                           {"pendencia_id": f"eq.{pendencia_id}", "order": "respondida_em.asc",
                            "select": "id,pergunta_id,usuario_nome,texto,respondida_em"})
    historico = await _get("pendencia_historico",
                           {"pendencia_id": f"eq.{pendencia_id}", "order": "ocorrido_em.asc",
                            "select": "evento,detalhe,usuario_email,ocorrido_em"})
    return {**ped[0], "perguntas": perguntas, "respostas": respostas, "historico": historico}


async def dashboard(obra: str) -> dict:
    rows = await _get("pendencias", {"obra": f"eq.{obra}", "status": "in.(aberta,respondida,em_tratamento)",
                                     "select": "categoria,severidade,impacto"})
    por_cat: dict[str, int] = {}
    criticas = 0
    impacto_total = 0
    for r in rows:
        por_cat[r["categoria"]] = por_cat.get(r["categoria"], 0) + 1
        if (r.get("severidade") or 0) >= 4:
            criticas += 1
        impacto_total += r.get("impacto") or 0
    return {"obra": obra, "abertas": len(rows), "criticas": criticas,
            "impacto_total": impacto_total, "por_categoria": por_cat}


# ── Escrita ──────────────────────────────────────────────────────────────────

async def log_email(obra: str, dest: list[str], assunto: str, provider_id: str,
                    status: str, erro: str = "") -> None:
    """Registra o envio (ou tentativa) na tabela emails_enviados."""
    try:
        await _post("emails_enviados", {
            "obra": obra, "tipo": "manual", "destinatarios": dest, "assunto": assunto,
            "provider_id": provider_id, "status": status, "erro": erro[:400],
        }, prefer="return=minimal")
    except Exception:
        pass


async def log_ia(obra: str, email: str, r: dict) -> None:
    """Registra o uso de IA (tokens + custo) — não interrompe a resposta se falhar."""
    try:
        await _post("ia_logs", {
            "obra": obra, "tipo": "chat", "usuario_email": email,
            "modelo": r.get("modelo", ""), "tokens_entrada": r.get("tokens_entrada", 0),
            "tokens_saida": r.get("tokens_saida", 0), "custo_usd": r.get("custo_usd", 0),
            "sucesso": True,
        }, prefer="return=minimal")
    except Exception:
        pass


async def responder(pendencia_id: int, obra: str, email: str, nome: str,
                    texto: str, pergunta_id: int | None) -> dict:
    ped = await _get("pendencias", {"id": f"eq.{pendencia_id}", "obra": f"eq.{obra}", "limit": "1"})
    if not ped:
        raise HTTPException(404, "Pendência não encontrada.")
    reg = {"pendencia_id": pendencia_id, "obra": obra, "usuario_email": email,
           "usuario_nome": nome, "texto": texto}
    if pergunta_id:
        reg["pergunta_id"] = pergunta_id
    nova = (await _post("pendencia_respostas", reg))[0]
    # marca como respondida (não sobrescreve nada — só muda o status corrente)
    if ped[0]["status"] == "aberta":
        await _patch("pendencias", {"id": f"eq.{pendencia_id}"}, {"status": "respondida"})
    await _post("pendencia_historico", {
        "pendencia_id": pendencia_id, "obra": obra, "evento": "respondida",
        "detalhe": {"resposta_id": nova["id"]}, "usuario_email": email})
    return nova
