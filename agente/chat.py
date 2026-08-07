"""
Assistente da Obra — chat com a Claude API.
===========================================
Responde perguntas do engenheiro usando EXCLUSIVAMENTE os dados da obra
(pendências), com o isolamento por obra garantido pela camada de API (o
chamador já veio validado por usuario_e_obra, e o contexto só traz a obra pedida).

Config (env):
    ANTHROPIC_API_KEY   obrigatória
    ANTHROPIC_MODEL     opcional (default claude-sonnet-5 — bom custo/qualidade
                        para consulta de dados; troque por claude-opus-5 para
                        respostas mais profundas, ou claude-haiku-4-5 p/ menor custo)
"""
from __future__ import annotations

import os

MODELO = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")

# Preço aproximado (US$/1M tokens) para estimar custo — só para o log.
_PRECO = {
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


def _pav(nome: str) -> str:
    import re
    m = re.match(r"^\d+\s*º", nome or "")
    return m.group(0).replace(" ", "") if m else (nome or "—")


def montar_contexto(obra: str, pendencias: list[dict]) -> str:
    """Renderização compacta das pendências para o system prompt."""
    obra_itens = [p for p in pendencias if not (p.get("causa_raiz") or {}).get("provavel_so_fvs")]
    fvs_itens = [p for p in pendencias if (p.get("causa_raiz") or {}).get("provavel_so_fvs")]
    obra_itens.sort(key=lambda p: -(p.get("impacto") or 0))

    def linha(p: dict) -> str:
        causa = p.get("causa_raiz") or {}
        jobs = ", ".join(j.get("name", "") for j in (causa.get("jobs_pendentes") or [])[:2])
        trava = causa.get("trava") or []
        partes = [
            f"- {p.get('servico')}",
            _pav(p.get("pavimento", "")),
            f"{(p.get('pct_real') or 0):.0f}%",
        ]
        if p.get("impacto"):
            partes.append(f"impacto {p.get('impacto')}")
        if jobs:
            partes.append(f"falta: {jobs}")
        if trava:
            partes.append("trava: " + "; ".join(
                f"{t.get('servico')} ({_pav(t.get('pavimento', ''))})" for t in trava[:3]))
        return " | ".join(partes)

    linhas_obra = "\n".join(linha(p) for p in obra_itens[:120])
    linhas_fvs = "\n".join(linha(p) for p in fvs_itens[:120])
    return (
        f"ATRASOS DE OBRA (serviços atrasados que travam o cronograma) — {len(obra_itens)}:\n"
        f"{linhas_obra or '(nenhum)'}\n\n"
        f"FVS PENDENTES (obra ~pronta, falta preencher a ficha) — {len(fvs_itens)}:\n"
        f"{linhas_fvs or '(nenhuma)'}"
    )


def _system(obra: str, contexto: str) -> str:
    return (
        f"Você é o Assistente da Obra {obra}, do Agente de Planejamento da R21 "
        f"(construção civil). Um engenheiro de planejamento faz perguntas e você "
        f"responde como um planejador experiente.\n\n"
        f"REGRAS (obrigatórias):\n"
        f"- Responda usando EXCLUSIVAMENTE os dados abaixo. Se a informação não "
        f"estiver nos dados, diga claramente que não há dados disponíveis — NUNCA invente.\n"
        f"- Você cobre APENAS a obra {obra}. Se perguntarem de outra obra, diga que "
        f"este assistente responde só sobre a {obra}.\n"
        f"- Seja direto e prático. Cite serviço, pavimento e números quando ajudar. "
        f"Prefira listas curtas a textões.\n"
        f"- Conceitos: 'atraso de obra' = serviço atrasado com a frente liberada, "
        f"que trava outros (impacto = nº de serviços travados a jusante). "
        f"'FVS pendente' = serviço fisicamente ~pronto, falta preencher a ficha de verificação.\n\n"
        f"DADOS DA OBRA {obra} (pendências abertas):\n{contexto}"
    )


async def responder(obra: str, pendencias: list[dict], pergunta: str,
                    historico: list[dict] | None = None) -> dict:
    """Devolve {resposta, tokens_entrada, tokens_saida, custo_usd, modelo}."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY não configurada.")
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic()
    mensagens = list(historico or []) + [{"role": "user", "content": pergunta}]
    kwargs = dict(
        model=MODELO,
        max_tokens=1500,
        system=_system(obra, montar_contexto(obra, pendencias)),
        messages=mensagens,
    )
    # Chat de consulta = resposta direta. Desliga o "raciocínio" (quando o modelo
    # suporta), que senão consome o orçamento de tokens e volta vazio.
    try:
        resp = await client.messages.create(thinking={"type": "disabled"}, **kwargs)
    except Exception:
        resp = await client.messages.create(**kwargs)  # modelo sem esse parâmetro

    texto = "".join(b.text for b in resp.content
                    if getattr(b, "type", "") == "text").strip()
    if not texto:
        texto = ("Não consegui gerar uma resposta agora (a IA retornou vazio). "
                 "Tente reformular a pergunta.")
    ent, sai = resp.usage.input_tokens, resp.usage.output_tokens
    pin, pout = _PRECO.get(MODELO, (3.0, 15.0))
    custo = (ent * pin + sai * pout) / 1_000_000
    return {"resposta": texto, "tokens_entrada": ent, "tokens_saida": sai,
            "custo_usd": round(custo, 5), "modelo": MODELO}
