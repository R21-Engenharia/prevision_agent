"""
Protecao da API — valida o token Supabase enviado pelo frontend.
=================================================================
Sem isto, publicar o app seria teatro de seguranca: a tela teria login mas
qualquer um leria os dados chamando a API direto.

Modo de operacao:
  - SUPABASE_URL + SUPABASE_KEY definidos  -> exige Bearer token valido
  - FVS_DEV_NO_AUTH=1                      -> libera geral (SO para dev local)
  - nenhum dos dois                        -> bloqueia tudo (falha visivel,
                                              em vez de expor dados calado)
"""
from __future__ import annotations

import os
import time

import httpx
from fastapi import Header, HTTPException

_SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
_SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
_DEV_SEM_AUTH = os.getenv("FVS_DEV_NO_AUTH", "").strip().lower() in {"1", "true", "sim"}

# Cache de tokens ja validados: token -> (email, expira_em)
# Evita uma ida ao Supabase a cada requisicao.
_CACHE: dict[str, tuple[str, float]] = {}
_TTL_CACHE = 300  # 5 minutos


def auth_configurada() -> bool:
    return bool(_SUPABASE_URL and _SUPABASE_KEY)


def descrever_modo() -> str:
    if _DEV_SEM_AUTH:
        return "ABERTA (FVS_DEV_NO_AUTH=1) — use apenas em desenvolvimento"
    if auth_configurada():
        return "protegida por Supabase"
    return "BLOQUEADA — defina SUPABASE_URL/SUPABASE_KEY ou FVS_DEV_NO_AUTH=1"


async def _validar_no_supabase(token: str) -> str:
    """Consulta o Supabase e devolve o e-mail do dono do token."""
    async with httpx.AsyncClient(timeout=10) as cli:
        r = await cli.get(
            f"{_SUPABASE_URL}/auth/v1/user",
            headers={"Authorization": f"Bearer {token}", "apikey": _SUPABASE_KEY},
        )
    if r.status_code != 200:
        raise HTTPException(401, "Token invalido ou expirado.")
    email = (r.json() or {}).get("email") or ""
    if not email:
        raise HTTPException(401, "Token sem e-mail associado.")
    return email.lower()


async def usuario_atual(authorization: str | None = Header(default=None)) -> str:
    """
    Dependencia do FastAPI: devolve o e-mail autenticado.
    Use com  Depends(usuario_atual)  nas rotas que expoem dados.
    """
    if _DEV_SEM_AUTH:
        return "dev@local"

    if not auth_configurada():
        raise HTTPException(
            503,
            "API sem autenticacao configurada. Defina SUPABASE_URL e SUPABASE_KEY "
            "(ou FVS_DEV_NO_AUTH=1 para desenvolvimento local).",
        )

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Autenticacao obrigatoria.")

    token = authorization.split(" ", 1)[1].strip()
    agora = time.time()

    em_cache = _CACHE.get(token)
    if em_cache and em_cache[1] > agora:
        return em_cache[0]

    email = await _validar_no_supabase(token)
    _CACHE[token] = (email, agora + _TTL_CACHE)

    # Limpeza preguicosa das entradas vencidas
    if len(_CACHE) > 256:
        for k, (_e, exp) in list(_CACHE.items()):
            if exp <= agora:
                _CACHE.pop(k, None)

    return email
