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
def _post_sienge(cc: int, tipo_id: int, doc: str, resource_id: int,
                 quantidade: float, unidade: str, dia: str) -> httpx.Response:
    sng = SiengeClient()
    payload = {
        "costCenterId": cc, "movementTypeId": tipo_id, "documentId": doc,
        "movementDate": dia,
        "items": [{"resourceId": int(resource_id), "quantity": float(quantidade),
                   "unitOfMeasure": unidade}],
    }
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


async def _gravar(obra: str, operacao: str, tipo_id: int, doc: str,
                  resource_id: str, quantidade: float, usuario: str,
                  descricao: str, unidade: str, estorno_de: int | None = None) -> dict:
    cfg = OBRAS[obra]
    dia = date.today().isoformat()
    r = await asyncio.to_thread(_post_sienge, cfg["cc"], tipo_id, doc,
                                resource_id, quantidade, unidade, dia)
    ok = 200 <= r.status_code < 300
    mov_id = _extrair_id(r) if ok else None
    try:
        corpo = r.json()
    except Exception:  # noqa: BLE001
        corpo = {"texto": r.text[:400]}

    registro = {
        "usuario": usuario, "obra": obra, "resource_id": str(resource_id),
        "descricao": descricao, "operacao": operacao, "movement_type_id": tipo_id,
        "quantidade": quantidade, "unidade": unidade, "document_id": doc,
        "movement_date": dia, "sienge_status": r.status_code,
        "sienge_movement_id": mov_id, "sienge_resposta": corpo,
        "estorno_de": estorno_de,
    }
    aud = await _auditar(registro)

    if not ok:
        # devolve o erro exato do Sienge para o usuário entender e corrigir
        raise HTTPException(status_code=422, detail={
            "mensagem": "O Sienge recusou a movimentação.",
            "sienge_status": r.status_code, "sienge_resposta": corpo,
            "auditoria": aud})
    return {"ok": True, "sienge_status": r.status_code,
            "sienge_movement_id": mov_id, "auditoria": aud, "movement_date": dia}


# ── operações públicas (chamadas pelas rotas admin) ───────────────────────────
async def baixa(obra: str, resource_id: str, quantidade: float, usuario: str) -> dict:
    return await _mov(obra, "baixa", resource_id, quantidade, usuario)


async def entrada(obra: str, resource_id: str, quantidade: float, usuario: str) -> dict:
    return await _mov(obra, "entrada", resource_id, quantidade, usuario)


async def _mov(obra: str, operacao: str, resource_id: str,
               quantidade: float, usuario: str) -> dict:
    if obra not in OBRAS:
        raise HTTPException(400, "Obra desconhecida.")
    if not quantidade or float(quantidade) <= 0:
        raise HTTPException(400, "Quantidade deve ser maior que zero.")
    insumo = _insumo(OBRAS[obra]["pid"], resource_id)
    if not insumo:
        raise HTTPException(404, "Insumo não encontrado no estoque desta obra.")
    saldo = float(insumo.get("saldo") or 0)
    if operacao == "baixa" and float(quantidade) > saldo + 1e-6:
        raise HTTPException(400, {
            "mensagem": f"Baixa ({quantidade}) maior que o saldo em estoque ({saldo} "
                        f"{insumo.get('unidade_base')}). Verifique a quantidade.",
            "saldo": saldo})
    tipo_id, doc = OP[operacao]
    r = await _gravar(obra, operacao, tipo_id, doc, resource_id, float(quantidade),
                      usuario, insumo.get("descricao"), insumo.get("unidade_base"))
    delta = -float(quantidade) if operacao == "baixa" else float(quantidade)
    r["saldo_anterior"] = round(saldo, 3)
    r["saldo_estimado"] = round(saldo + delta, 3)
    r["descricao"] = insumo.get("descricao")
    r["unidade"] = insumo.get("unidade_base")
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
    r = await _gravar(orig["obra"], "estorno", tipo_id, doc, orig["resource_id"],
                      float(orig["quantidade"]), usuario, orig.get("descricao"),
                      orig.get("unidade"), estorno_de=auditoria_id)
    await _marcar_estornado(auditoria_id)
    r["estornou"] = auditoria_id
    r["descricao"] = orig.get("descricao")
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
