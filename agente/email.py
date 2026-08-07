"""
Envio de e-mail via Resend.
===========================
Camada fina sobre a API do Resend (https://resend.com). Sem SDK — httpx direto.

Config (env):
    RESEND_API_KEY        obrigatória (re_...)
    EMAIL_REMETENTE       ex.: "R21 Agente <agente@seudominio.com.br>"
                          (default usa o domínio de teste do Resend)
    EMAIL_DESTINATARIOS   lista separada por vírgula (fallback quando não passada)
"""
from __future__ import annotations

import base64
import os

import httpx

_ENDPOINT = "https://api.resend.com/emails"
_REMETENTE_PADRAO = "R21 Agente <onboarding@resend.dev>"


def destinatarios_padrao() -> list[str]:
    bruto = os.getenv("EMAIL_DESTINATARIOS", "")
    return [e.strip() for e in bruto.split(",") if e.strip()]


def enviar(
    destinatarios: list[str],
    assunto: str,
    html: str,
    anexos: list[tuple[str, bytes]] | None = None,
) -> dict:
    """
    Envia um e-mail. `anexos` = [(nome_arquivo, bytes)]. Devolve {"id": ...}.
    Levanta RuntimeError se não configurado, httpx.HTTPStatusError em falha.
    """
    key = os.getenv("RESEND_API_KEY", "").strip()
    if not key:
        raise RuntimeError("RESEND_API_KEY não definida.")
    if not destinatarios:
        raise RuntimeError("Sem destinatários.")

    payload: dict = {
        "from": os.getenv("EMAIL_REMETENTE") or _REMETENTE_PADRAO,
        "to": destinatarios,
        "subject": assunto,
        "html": html,
    }
    if anexos:
        payload["attachments"] = [
            {"filename": nome, "content": base64.b64encode(dados).decode("ascii")}
            for nome, dados in anexos
        ]

    r = httpx.post(
        _ENDPOINT, json=payload,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()
