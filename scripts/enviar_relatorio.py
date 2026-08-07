"""
Envia o relatório de pendências por e-mail (Resend).
=====================================================
Consolidado por obra: HTML resumido + planilhas Excel em anexo. Roda agendado
(semanal) ou à mão. Registra cada envio em emails_enviados.

Executar (a partir de prevision_agent/):
    python scripts/enviar_relatorio.py                 # todas as obras
    python scripts/enviar_relatorio.py "Holmes Residence"

Config (env / .env):
    SUPABASE_URL, SUPABASE_KEY   leitura das pendências + log
    RESEND_API_KEY               envio
    EMAIL_REMETENTE              "R21 Agente <agente@dominio>"
    EMAIL_DESTINATARIOS          lista separada por vírgula
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

from agente.destinatarios import destinatarios
from agente.email import destinatarios_padrao, enviar
from agente.report_html import build_email_html
from api.report_agente import build_pendencias_report

OBRAS = ["Cape Town Residence", "Holmes Residence"]
_ABERTAS = "in.(aberta,respondida,em_tratamento)"


def _sb() -> tuple[str, dict]:
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_KEY", "")
    if not (url and key):
        raise RuntimeError("SUPABASE_URL/KEY não definidos.")
    return f"{url}/rest/v1", {"apikey": key, "Authorization": f"Bearer {key}",
                              "Content-Type": "application/json"}


def fetch_pendencias(obra: str) -> list[dict]:
    base, h = _sb()
    r = httpx.get(f"{base}/pendencias", headers=h, timeout=20, params={
        "obra": f"eq.{obra}", "status": _ABERTAS,
        "select": "servico,pavimento,categoria,impacto,pct_real,status,causa_raiz",
    })
    r.raise_for_status()
    return r.json()


def log_email(obra: str, dest: list[str], assunto: str,
              provider_id: str, status: str, erro: str = "") -> None:
    base, h = _sb()
    try:
        httpx.post(f"{base}/emails_enviados", headers={**h, "Prefer": "return=minimal"},
                   timeout=15, json={
                       "obra": obra, "tipo": "consolidado_semanal", "destinatarios": dest,
                       "assunto": assunto, "provider_id": provider_id or "",
                       "status": status, "erro": erro[:400]})
    except Exception as exc:
        print(f"  (aviso: falha ao registrar log: {exc})", flush=True)


def main() -> int:
    alvos = [sys.argv[1]] if len(sys.argv) > 1 else OBRAS

    falhas = 0
    for obra in alvos:
        # Roteamento por obra (engenharia da obra + gestores); EMAIL_DESTINATARIOS
        # sobrescreve tudo, se definido.
        dest = destinatarios_padrao() or destinatarios(obra)
        if not dest:
            print(f"{obra}: sem destinatários configurados — pulando.")
            continue
        pend = fetch_pendencias(obra)
        if not pend:
            print(f"{obra}: sem pendências — nada a enviar.")
            continue
        html, resumo = build_email_html(obra, pend)
        so_fvs = [p for p in pend if (p.get("causa_raiz") or {}).get("provavel_so_fvs")]
        obra_p = [p for p in pend if not (p.get("causa_raiz") or {}).get("provavel_so_fvs")]
        anexos = [
            ("atrasos_obra.xlsx", build_pendencias_report(obra, "obra", obra_p)),
            ("fvs_pendentes.xlsx", build_pendencias_report(obra, "fvs", so_fvs)),
        ]
        assunto = (f"[R21] Pendências — {obra}: {resumo['atrasos']} atrasos de obra, "
                   f"{resumo['fvs']} FVS")
        try:
            res = enviar(dest, assunto, html, anexos=anexos)
            log_email(obra, dest, assunto, res.get("id", ""), "enviado")
            print(f"{obra}: enviado a {len(dest)} destinatário(s) · id {res.get('id')}")
        except Exception as exc:
            falhas += 1
            log_email(obra, dest, assunto, "", "falhou", str(exc))
            print(f"{obra}: FALHOU — {exc}")

    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
