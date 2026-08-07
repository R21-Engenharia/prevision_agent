"""
Envio de e-mail — SMTP (caixa própria) ou Resend.
==================================================
Dois caminhos, escolhidos pelo ambiente:

  SMTP (recomendado p/ e-mails internos, SEM DNS)
    SMTP_HOST   ex.: smtp.gmail.com  (Google Workspace) / smtp.office365.com
    SMTP_PORT   587 (default)
    SMTP_USER   a caixa que envia, ex.: agente@r21empreendimentos.com
    SMTP_PASS   SENHA DE APLICATIVO (não a senha normal)

  Resend (precisa domínio verificado p/ enviar a terceiros)
    RESEND_API_KEY

Comum:
  EMAIL_REMETENTE      "R21 Agente <agente@r21empreendimentos.com>" (default: SMTP_USER)
  EMAIL_DESTINATARIOS  lista separada por vírgula
"""
from __future__ import annotations

import base64
import os
import smtplib
from email.message import EmailMessage

import httpx

_RESEND = "https://api.resend.com/emails"
_REMETENTE_PADRAO = "R21 Agente <onboarding@resend.dev>"


def destinatarios_padrao() -> list[str]:
    return [e.strip() for e in os.getenv("EMAIL_DESTINATARIOS", "").split(",") if e.strip()]


def _remetente(fallback: str) -> str:
    return os.getenv("EMAIL_REMETENTE") or fallback


def enviar(
    destinatarios: list[str],
    assunto: str,
    html: str,
    anexos: list[tuple[str, bytes]] | None = None,
) -> dict:
    """Envia via SMTP se configurado, senão Resend. `anexos` = [(nome, bytes)]."""
    if not destinatarios:
        raise RuntimeError("Sem destinatários.")
    if os.getenv("SMTP_HOST"):
        return _via_smtp(destinatarios, assunto, html, anexos)
    if os.getenv("RESEND_API_KEY"):
        return _via_resend(destinatarios, assunto, html, anexos)
    raise RuntimeError("Configure SMTP_* (recomendado) ou RESEND_API_KEY.")


# ── SMTP ──────────────────────────────────────────────────────────────────────

def _via_smtp(destinatarios, assunto, html, anexos) -> dict:
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "")
    senha = os.getenv("SMTP_PASS", "")
    if not (user and senha):
        raise RuntimeError("SMTP_USER/SMTP_PASS não definidos.")

    msg = EmailMessage()
    msg["From"] = _remetente(user)
    msg["To"] = ", ".join(destinatarios)
    msg["Subject"] = assunto
    msg.set_content("Este relatório é em HTML — use um cliente que exiba HTML.")
    msg.add_alternative(html, subtype="html")
    for nome, dados in (anexos or []):
        msg.add_attachment(dados, maintype="application",
                           subtype="octet-stream", filename=nome)

    with smtplib.SMTP(host, port, timeout=30) as s:
        s.starttls()
        s.login(user, senha)
        s.send_message(msg)
    return {"id": "smtp", "via": "smtp"}


# ── Resend ────────────────────────────────────────────────────────────────────

def _via_resend(destinatarios, assunto, html, anexos) -> dict:
    key = os.getenv("RESEND_API_KEY", "").strip()
    payload: dict = {"from": _remetente(_REMETENTE_PADRAO), "to": destinatarios,
                     "subject": assunto, "html": html}
    if anexos:
        payload["attachments"] = [
            {"filename": n, "content": base64.b64encode(d).decode("ascii")}
            for n, d in anexos]
    r = httpx.post(_RESEND, json=payload, timeout=30,
                   headers={"Authorization": f"Bearer {key}",
                            "Content-Type": "application/json"})
    if r.status_code >= 400:
        try:
            msg = (r.json() or {}).get("message") or r.text
        except Exception:
            msg = r.text
        raise RuntimeError(f"Resend HTTP {r.status_code}: {msg}")
    return r.json()
