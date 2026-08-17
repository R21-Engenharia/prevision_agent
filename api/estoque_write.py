"""
api/estoque_write.py — ESCRITA de movimentações de estoque.
===========================================================
Camada ACTION do módulo de estoque: grava movimentações no Sienge
(POST /stock-movements) e registra a TRILHA DE AUDITORIA no Supabase.

É escrita em PRODUÇÃO — por isso: só admin nas rotas, validação antes de gravar,
confirmação no front, e todo movimento fica auditado (quem, o quê, quando, retorno
do Sienge). Estorno = movimento compensatório na direção oposta.

Mapa de tipos (Sienge): 1 Compra · 2 Consumo · 4 Devolução · 8 Venda
                        9 Inicialização Entrada Avulsa · 10 Inicialização Saída Avulsa
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import date
from pathlib import Path

import httpx
from fastapi import HTTPException

from rup.sienge_client import SiengeClient

_RAIZ = Path(__file__).resolve().parent.parent
_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
_KEY = os.getenv("SUPABASE_KEY", "")

# obra -> project_id (snapshot) + costCenterId/buildingId do Sienge
OBRAS = {"Cape Town Residence": {"pid": 10223, "cc": 23},
         "Holmes Residence": {"pid": 18992, "cc": 13}}

# operação -> (movementTypeId, documentId)
OP = {"baixa": (2, "REQ"), "entrada": (9, "AJE")}
# estorno: inverte a direção do tipo original
TIPO_ESTORNO = {2: (9, "EST"), 1: (10, "EST"), 9: (10, "EST"), 10: (9, "EST")}


# ── snapshot local (para validar saldo/unidade/descrição) ─────────────────────
def _insumo(pid: int, resource_id: str) -> dict | None:
    f = _RAIZ / "data" / f"estoque_{pid}.json"
    if not f.exists():
        return None
    dados = json.loads(f.read_text(encoding="utf-8"))
    return (dados.get("insumos") or {}).get(str(resource_id))


# ── auditoria (Supabase) — best-effort: nunca derruba a gravação no Sienge ─────
async def _auditar(registro: dict) -> dict:
    if not (_URL and _KEY):
        return {"ok": False, "motivo": "Supabase não configurado"}
    base = f"{_URL}/rest/v1/estoque_movimentos"
    headers = {"apikey": _KEY, "Authorization": f"Bearer {_KEY}",
               "Content-Type": "application/json", "Prefer": "return=representation"}
    try:
        async with httpx.AsyncClient(timeout=15) as cli:
            r = await cli.post(base, json=registro, headers=headers)
        if r.status_code >= 400:
            return {"ok": False, "motivo": f"HTTP {r.status_code}: {r.text[:160]}"}
        linha = (r.json() or [{}])[0] if r.text else {}
        return {"ok": True, "id": linha.get("id")}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "motivo": str(exc)[:160]}


async def _buscar_auditoria(auditoria_id: int) -> dict | None:
    if not (_URL and _KEY):
        return None
    base = f"{_URL}/rest/v1/estoque_movimentos"
    headers = {"apikey": _KEY, "Authorization": f"Bearer {_KEY}"}
    async with httpx.AsyncClient(timeout=15) as cli:
        r = await cli.get(base, params={"id": f"eq.{auditoria_id}", "select": "*"},
                          headers=headers)
    if r.status_code >= 400 or not r.json():
        return None
    return r.json()[0]


async def _marcar_estornado(auditoria_id: int) -> None:
    if not (_URL and _KEY):
        return
    base = f"{_URL}/rest/v1/estoque_movimentos"
    headers = {"apikey": _KEY, "Authorization": f"Bearer {_KEY}",
               "Content-Type": "application/json", "Prefer": "return=minimal"}
    try:
        async with httpx.AsyncClient(timeout=15) as cli:
            await cli.patch(base, params={"id": f"eq.{auditoria_id}"},
                            json={"estornado": True}, headers=headers)
    except Exception:  # noqa: BLE001
        pass


# ── gravação no Sienge ────────────────────────────────────────────────────────
def _post_sienge(cc: int, tipo_id: int, doc: str, items: list[dict],
                 dia: str) -> httpx.Response:
    """Uma movimentação no Sienge com uma ou VÁRIAS linhas (items)."""
    sng = SiengeClient()
    payload = {"costCenterId": cc, "movementTypeId": tipo_id, "documentId": doc,
               "movementDate": dia, "items": items}
    return sng.post("stock-movements", json=payload)


def _extrair_id(r: httpx.Response) -> str | None:
    loc = r.headers.get("location") or r.headers.get("Location")
    if loc:
        return loc.rstrip("/").split("/")[-1]
    try:
        body = r.json()
    except Exception:  # noqa: BLE001
        return None
    if isinstance(body, dict):
        for k in ("id", "movementId", "movementNumber"):
            if body.get(k) is not None:
                return str(body[k])
    return None


async def _gravar_multi(obra: str, operacao: str, tipo_id: int, doc: str,
                        validados: list[dict], usuario: str,
                        estorno_de: int | None = None) -> dict:
    """Uma movimentação no Sienge com N linhas; audita uma linha por item."""
    cfg = OBRAS[obra]
    dia = date.today().isoformat()
    items_payload = [{"resourceId": int(v["resource_id"]),
                      "quantity": float(v["quantidade"]),
                      "unitOfMeasure": v["unidade"]} for v in validados]
    r = await asyncio.to_thread(_post_sienge, cfg["cc"], tipo_id, doc,
                                items_payload, dia)
    ok = 200 <= r.status_code < 300
    try:
        corpo = r.json()
    except Exception:  # noqa: BLE001
        corpo = {"texto": r.text[:400]}
    if not ok:
        # nada foi gravado — devolve o erro exato do Sienge para o usuário corrigir
        raise HTTPException(status_code=422, detail={
            "mensagem": "O Sienge recusou a movimentação.",
            "sienge_status": r.status_code, "sienge_resposta": corpo})

    mov_id = _extrair_id(r)
    itens_out = []
    for v in validados:
        aud = await _auditar({
            "usuario": usuario, "obra": obra, "resource_id": str(v["resource_id"]),
            "descricao": v.get("descricao"), "operacao": operacao,
            "movement_type_id": tipo_id, "quantidade": v["quantidade"],
            "unidade": v.get("unidade"), "document_id": doc, "movement_date": dia,
            "sienge_status": r.status_code, "sienge_movement_id": mov_id,
            "sienge_resposta": corpo, "estorno_de": estorno_de})
        itens_out.append({"descricao": v.get("descricao"), "quantidade": v["quantidade"],
                          "unidade": v.get("unidade"), "auditoria": aud})
    return {"ok": True, "sienge_status": r.status_code, "sienge_movement_id": mov_id,
            "movement_date": dia, "itens": itens_out}


# ── operações públicas (chamadas pelas rotas admin) ───────────────────────────
async def baixa(obra: str, itens: list[dict], usuario: str) -> dict:
    return await _mov_multi(obra, "baixa", itens, usuario)


async def entrada(obra: str, itens: list[dict], usuario: str) -> dict:
    return await _mov_multi(obra, "entrada", itens, usuario)


async def _mov_multi(obra: str, operacao: str, itens: list[dict],
                     usuario: str) -> dict:
    if obra not in OBRAS:
        raise HTTPException(400, "Obra desconhecida.")
    if not itens:
        raise HTTPException(400, "Nenhum insumo na lista.")
    pid = OBRAS[obra]["pid"]
    validados = []
    for it in itens:
        rid = it.get("resource_id")
        q = float(it.get("quantidade") or 0)
        insumo = _insumo(pid, rid)
        if not insumo:
            raise HTTPException(404, f"Insumo {rid} não encontrado no estoque.")
        if q <= 0:
            raise HTTPException(400, f"Quantidade inválida para {insumo.get('descricao')}.")
        saldo = float(insumo.get("saldo") or 0)
        if operacao == "baixa" and q > saldo + 1e-6:
            raise HTTPException(400, {
                "mensagem": f"{insumo.get('descricao')}: baixa ({q}) maior que o saldo "
                            f"({saldo} {insumo.get('unidade_base')})."})
        validados.append({"resource_id": rid, "quantidade": q,
                          "descricao": insumo.get("descricao"),
                          "unidade": insumo.get("unidade_base")})
    tipo_id, doc = OP[operacao]
    r = await _gravar_multi(obra, operacao, tipo_id, doc, validados, usuario)
    r["n_itens"] = len(validados)
    return r


async def estornar(auditoria_id: int, usuario: str) -> dict:
    orig = await _buscar_auditoria(auditoria_id)
    if not orig:
        raise HTTPException(404, "Movimento original não encontrado na auditoria.")
    if orig.get("estornado"):
        raise HTTPException(400, "Este movimento já foi estornado.")
    if orig.get("estorno_de"):
        raise HTTPException(400, "Não é possível estornar um estorno.")
    if int(orig.get("sienge_status") or 0) not in range(200, 300):
        raise HTTPException(400, "O movimento original não foi gravado com sucesso.")
    tipo_orig = int(orig["movement_type_id"])
    if tipo_orig not in TIPO_ESTORNO:
        raise HTTPException(400, f"Tipo {tipo_orig} não tem estorno definido.")
    tipo_id, doc = TIPO_ESTORNO[tipo_orig]
    validados = [{"resource_id": orig["resource_id"], "quantidade": float(orig["quantidade"]),
                  "descricao": orig.get("descricao"), "unidade": orig.get("unidade")}]
    r = await _gravar_multi(orig["obra"], "estorno", tipo_id, doc, validados,
                            usuario, estorno_de=auditoria_id)
    await _marcar_estornado(auditoria_id)
    r["estornou"] = auditoria_id
    return r


async def historico(obra: str, limite: int = 30) -> dict:
    """Movimentações manuais registradas (para a UI mostrar e permitir estorno)."""
    if not (_URL and _KEY):
        return {"disponivel": False, "movimentos": []}
    base = f"{_URL}/rest/v1/estoque_movimentos"
    headers = {"apikey": _KEY, "Authorization": f"Bearer {_KEY}"}
    async with httpx.AsyncClient(timeout=15) as cli:
        r = await cli.get(base, headers=headers, params={
            "obra": f"eq.{obra}", "order": "criado_em.desc", "limit": str(limite),
            "select": "id,criado_em,usuario,operacao,descricao,quantidade,unidade,"
                      "sienge_status,sienge_movement_id,estornado,estorno_de"})
    if r.status_code >= 400:
        return {"disponivel": False, "movimentos": [], "erro": r.status_code}
    return {"disponivel": True, "movimentos": r.json()}
