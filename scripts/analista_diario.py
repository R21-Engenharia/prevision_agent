"""
scripts/analista_diario.py
==========================
Analista de Dados DIÁRIO — versão autônoma do agente `.claude/agents/analista-dados`,
para rodar na nuvem (GitHub Actions) todo dia útil às 8h e mandar por e-mail.

Fluxo (a regra de ouro vale igual: os MOTORES calculam, a IA só EXPLICA):
  1. Roda os motores determinísticos (custo de material + previsão de desembolso) por obra;
  2. Manda SÓ os números para a IA da Anthropic redigir o diagnóstico executivo;
  3. Monta o e-mail em HTML e envia pela esteira que já existe (agente.email);
  4. Salva uma cópia em data/reports/ (artefato do dia).

Reaproveita a infra existente: ANTHROPIC_API_KEY (mesma de agente/chat.py) e os
secrets de e-mail (SMTP_*/RESEND) do workflow enviar_relatorio.

Executar (a partir de prevision_agent/):
    python scripts/analista_diario.py            # envia
    python scripts/analista_diario.py --seco     # só imprime, não envia (teste)
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

sys.stdout.reconfigure(encoding="utf-8")

from agente.email import destinatarios_padrao, enviar
from api.custos_db import desembolso, material

OBRAS = ["Cape Town Residence", "Holmes Residence"]

SYSTEM = (
    "Você é o Analista de Dados da R21 Engenharia (planejamento e orçamento de obras). "
    "Recebe números JÁ CALCULADOS pelos motores determinísticos do sistema (custo de "
    "material, curva ABC, alertas de preço, previsão de desembolso). Sua função é "
    "EXPLICAR e PRIORIZAR — nunca recalcular nem inventar número. Se um dado vier "
    "faltando, diga que falta.\n\n"
    "Regras do diagnóstico:\n"
    "- Escreva em português, executivo, curto e priorizado (o que exige ação primeiro).\n"
    "- Traduza número em consequência ('R$ X vencidos = risco imediato de caixa').\n"
    "- Separe sempre MATERIAL de MÃO DE OBRA/contrato.\n"
    "- Sobre o desembolso: deixe claro que é o CAIXA TOTAL da obra (majoritariamente "
    "provisão/contrato de empreiteiro), não só os insumos da curva ABC.\n"
    "- Não dê recomendação de investimento; só prioridades operacionais de custo/prazo.\n"
    "- Saída em HTML SIMPLES (use apenas <h3>, <p>, <ul>, <li>, <b> — sem <html>, "
    "<head>, <style>, tabelas ou CSS). Comece direto pelo conteúdo."
)


def _numeros_da_obra(obra: str) -> dict:
    """Só o que os motores calculam — a IA recebe isto e não recalcula nada."""
    mat_mes = material(obra, top=20, janela="mes_atual")
    mat_obra = material(obra, top=12, janela="obra")
    des = desembolso(obra)

    def _resumo_mat(m: dict) -> dict:
        if not m.get("disponivel"):
            return {"disponivel": False, "mensagem": m.get("mensagem")}
        return {
            "disponivel": True,
            "total_comprado": m.get("total_comprado"),
            "n_insumos": m.get("n_insumos"),
            "abc_resumo": m.get("abc_resumo"),
            "grupos_top": (m.get("grupos") or [])[:6],
            "alertas": m.get("alertas") or [],
            "itens_top": [
                {"descricao": i.get("descricao"), "classe": i.get("classe"),
                 "comprado": i.get("total_valor"),
                 "tendencia": {k: i.get("tendencia", {}).get(k) for k in
                               ("variacao_pct", "variacao_primeira_pct", "direcao",
                                "primeira", "medio", "ultimo")}}
                for i in (m.get("itens") or [])[:12]
            ],
        }

    return {
        "material_mes_atual": _resumo_mat(mat_mes),
        "material_obra_inteira": _resumo_mat(mat_obra),
        "desembolso": des if des.get("disponivel") else {
            "disponivel": False, "mensagem": des.get("mensagem")},
    }


async def _diagnostico_ia(dados: dict) -> str:
    import os
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY não configurada.")
    from anthropic import AsyncAnthropic

    modelo = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
    client = AsyncAnthropic()
    prompt = (
        "Diagnóstico do dia para os gestores. Abaixo os números dos motores por obra "
        "(NÃO recalcule — interprete e priorize). Para cada obra, aponte: onde o "
        "dinheiro concentra (ABC/grupos), preços em risco (alertas), e risco de caixa "
        "(desembolso: vencidas e próximos 30 dias). Se houver algo crítico, destaque no "
        "topo. Seja breve.\n\n"
        f"```json\n{json.dumps(dados, ensure_ascii=False, indent=1)}\n```"
    )
    resp = await client.messages.create(
        model=modelo, max_tokens=2500, system=SYSTEM,
        messages=[{"role": "user", "content": prompt}])
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


def _html(corpo: str, dia: str) -> str:
    return f"""<!doctype html><html><body style="margin:0;background:#f4f4f5;padding:24px;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1c1c1e;">
<div style="max-width:680px;margin:0 auto;background:#fff;border:1px solid #e5e5e7;border-radius:14px;overflow:hidden;">
  <div style="background:#111827;color:#fff;padding:18px 24px;">
    <div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;opacity:.7;">R21 · Analista de Dados</div>
    <div style="font-size:19px;font-weight:700;margin-top:2px;">Diagnóstico do dia — {dia}</div>
  </div>
  <div style="padding:22px 24px;line-height:1.6;font-size:14px;">{corpo}</div>
  <div style="padding:14px 24px;border-top:1px solid #eee;color:#8a8a8e;font-size:11.5px;line-height:1.5;">
    Gerado automaticamente pelos motores determinísticos da R21; a IA apenas explica os números.
    Números são cálculo do sistema, não estimativa do modelo.
  </div>
</div></body></html>"""


def main() -> int:
    seco = "--seco" in sys.argv
    dia = date.today().strftime("%d/%m/%Y")

    dados = {}
    for obra in OBRAS:
        try:
            dados[obra] = _numeros_da_obra(obra)
        except Exception as exc:  # uma obra quebrada não derruba o relatório
            dados[obra] = {"erro": str(exc)}
            print(f"  aviso: {obra} falhou — {exc}", flush=True)

    corpo = asyncio.run(_diagnostico_ia(dados))
    html = _html(corpo, dia)

    # cópia em arquivo (artefato do dia)
    try:
        rep = _ROOT / "data" / "reports"
        rep.mkdir(parents=True, exist_ok=True)
        (rep / f"analista_{date.today().isoformat()}.html").write_text(html, encoding="utf-8")
    except OSError:
        pass

    if seco:
        print(corpo)
        return 0

    from agente.destinatarios import GESTORES
    dest = destinatarios_padrao() or GESTORES   # fallback: gestores (inclui você)
    if not dest:
        print("Sem destinatários — relatório salvo em arquivo, e-mail não enviado.")
        return 0
    assunto = f"[R21] Diagnóstico do dia — {dia}"
    res = enviar(dest, assunto, html)
    print(f"Enviado a {len(dest)} destinatário(s) · {res.get('via', res.get('id'))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
