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
from fastapi import Header, HTTPException, Query

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


async def _perfil_do_usuario(email: str, token: str) -> tuple[str, list | None]:
    """
    Le (papel, obras) do e-mail na tabela authorized_emails.

    Usa o proprio token do usuario no Authorization para respeitar o RLS.
    Na duvida, devolve ("viewer", []) — nega privilegio E acesso a obras
    (fail-closed): sem conseguir ler o perfil, o usuario nao ve obra nenhuma.
    obras = None significa "todas" (padrao de admin / usuario sem restricao).
    """
    try:
        async with httpx.AsyncClient(timeout=10) as cli:
            r = await cli.get(
                f"{_SUPABASE_URL}/rest/v1/authorized_emails",
                params={"email": f"eq.{email}", "select": "role,obras"},
                headers={"Authorization": f"Bearer {token}", "apikey": _SUPABASE_KEY},
            )
        if r.status_code != 200:
            return ("viewer", [])
        linhas = r.json() or []
    except Exception:
        return ("viewer", [])
    if not linhas:
        return ("viewer", [])
    row = linhas[0]
    papel = "admin" if str(row.get("role", "")).lower() == "admin" else "viewer"
    obras = row.get("obras")
    return (papel, obras if isinstance(obras, list) else None)


def _obra_permitida(papel: str, obras: list | None, obra: str) -> bool:
    """Admin ou obras=None (sem restricao) veem tudo; senao, so as listadas."""
    if papel == "admin" or obras is None:
        return True
    return obra in obras


async def usuario_admin(authorization: str | None = Header(default=None)) -> str:
    """
    Como usuario_atual, mas exige role=admin — 403 caso contrario.
    Use em rotas de controle (ex.: disparar coleta de dados).
    """
    if _DEV_SEM_AUTH:
        return "dev@local"

    email = await usuario_atual(authorization)
    token = authorization.split(" ", 1)[1].strip()  # ja validado acima
    papel, _obras = await _perfil_do_usuario(email, token)
    if papel != "admin":
        raise HTTPException(403, "Acao restrita a administradores.")
    return email


async def usuario_e_obra(
    obra: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
) -> str:
    """
    Valida o token E o acesso a obra pedida (isolamento multi-tenant).
    Viewer so acessa a(s) sua(s) obra(s); admin ve tudo. 403 caso contrario.
    Use em toda rota de dados que recebe `obra`.
    """
    if _DEV_SEM_AUTH:
        return "dev@local"

    email = await usuario_atual(authorization)
    token = authorization.split(" ", 1)[1].strip()
    papel, obras = await _perfil_do_usuario(email, token)
    if obra and not _obra_permitida(papel, obras, obra):
        raise HTTPException(403, "Voce nao tem acesso a esta obra.")
    return email
