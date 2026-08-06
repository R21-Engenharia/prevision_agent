"""
Perguntas automáticas por tipo de pendência.
=============================================
A pergunta muda conforme a CAUSA — é o que separa cobrança útil de cobrança
burra. Um serviço com a frente liberada leva "por que a equipe não avançou?";
um que espera predecessor leva a pergunta apontando o gargalo, não a equipe.

Estes templates são o ponto de partida (origem="template"). Na Fase 5, a IA
pode gerar variações contextuais (origem="ia"), mas a base determinística
existe sem depender de LLM nenhum.
"""
from __future__ import annotations


def perguntas_para(categoria: str, ctx: dict) -> list[str]:
    """Devolve as perguntas para uma pendência, já preenchidas com o contexto."""
    gerador = _TEMPLATES.get(categoria)
    if not gerador:
        return ["Qual a situação atual deste serviço e a previsão de conclusão?"]
    return [p.format(**ctx) for p in gerador]


# ctx disponível: wbs, servico, pavimento, predecessor, pred_pct, impacto,
#                 pct_real, pct_esperado
_TEMPLATES: dict[str, list[str]] = {
    # Frente liberada (predecessores prontos) e mesmo assim atrasou → é a equipe.
    "atraso_proprio": [
        "O serviço {wbs} está em {pct_real:.0f}% (esperado {pct_esperado:.0f}%) com a "
        "frente totalmente liberada — todos os predecessores concluídos. Por que não avançou?",
        "Há algum impedimento além da frente de trabalho? (material, projeto, mão de obra)",
        "Este atraso está travando {impacto} serviço(s) na sequência. Qual a previsão de conclusão?",
        "É necessário reforço de equipe ou replanejamento do cronograma?",
    ],
    # Feito antes do predecessor → risco de retrabalho.
    "fora_sequencia": [
        "O serviço {wbs} está em {pct_real:.0f}% mas seu predecessor {predecessor} está em "
        "apenas {pred_pct:.0f}%. Confirmar que a execução fora de sequência não gera retrabalho.",
        "A dependência com {predecessor} é física (a execução exige) ou apenas lógica no cronograma?",
        "Houve liberação formal para executar {wbs} antes de {predecessor}?",
    ],
    # Vinha andando e parou.
    "parada": [
        "O serviço {wbs} vinha avançando e estagnou. O que causou a parada?",
        "Está aguardando material, aprovação, ou houve realocação da equipe?",
        "Qual a data prevista para retomar?",
    ],
    # Não-conformidade pendente.
    "nc_critica": [
        "O serviço {wbs} tem não-conformidade(s) pendente(s) de tratamento. Qual o plano de correção?",
        "Existe impedimento para o tratamento da NC?",
        "Qual a previsão de reinspeção?",
    ],
    # Pendência envelhecida.
    "aging": [
        "O serviço {wbs} está pendente há muito tempo sem conclusão. Qual o status real em campo?",
        "Há algum bloqueio que não está registrado no sistema?",
        "Qual a previsão de encerramento?",
    ],
}
