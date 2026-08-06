"""
Motor de análise causal — gera Pendências Inteligentes.
========================================================
Não trata "atrasado" como estado, e sim como sintoma com causa:

  atraso_proprio  — atrasado com TODOS os predecessores concluídos (frente
                    liberada). É a raiz: cabe cobrar a equipe.
  fora_sequencia  — avançou antes de um predecessor (risco de retrabalho).
  atraso_herdado  — atrasado só porque um predecessor está incompleto. NÃO
                    vira pendência própria: é contabilizado como IMPACTO da
                    raiz. Abrir pendência aqui seria cobrar quem não tem culpa.

Impacto (raio) = quantos serviços a jusante, também atrasados, dependem da
raiz — direta ou transitivamente. Prioridade = impacto, não dias de atraso.

As regras (limiares) vêm de fora (`regras`), espelhando a tabela
`priority_rules` do banco — configurável sem tocar aqui.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field


@dataclass
class Pendencia:
    obra: str
    wbs_code: str
    activity_id: str
    categoria: str
    severidade: int
    pct_real: float
    pct_esperado: float
    impacto: int = 0
    causa_raiz: dict = field(default_factory=dict)
    servico: str = ""
    pavimento: str = ""


# Limiares padrão (espelham priority_rules). Sobrescreva passando `regras`.
REGRAS_PADRAO = {
    "atraso_proprio": {"gap_min": 5, "severidade": 5},
    "atraso_herdado": {"gap_min": 5, "pred_incompleto": 99},
    "fora_sequencia": {"avanco_min": 10, "gap_pred": 20, "severidade": 4},
}


def _num(x) -> float:
    return float(x) if isinstance(x, (int, float)) else 0.0


def _pavimento_de(wbs: str) -> str:
    # WBS no padrão "21.54" → pavimento "21". Só um rótulo amigável.
    return wbs.split(".", 1)[0] if wbs and "." in wbs else ""


def analisar(dados: dict, obra: str, regras: dict | None = None) -> list[Pendencia]:
    """
    dados: {"activities": {id: {wbs,pct,exp,start}}, "edges": {succ_id: [(pred_id, op, lag)]}}
    Devolve a lista de Pendências (raízes: próprio + fora de sequência).
    """
    r = regras or REGRAS_PADRAO
    acts = dados["activities"]
    edges = dados["edges"]  # succ -> [(pred, op, lag)]

    gap = r.get("atraso_proprio", {}).get("gap_min", 5)
    concluido = r.get("atraso_herdado", {}).get("pred_incompleto", 99)
    avanco_min = r.get("fora_sequencia", {}).get("avanco_min", 10)
    gap_pred = r.get("fora_sequencia", {}).get("gap_pred", 20)

    # Adjacência direta pred -> [succ] e grau de saída
    frente = defaultdict(list)          # pred_id -> [succ_id]
    for succ_id, preds in edges.items():
        for pred_id, _op, _lag in preds:
            frente[pred_id].append(succ_id)

    def atrasada(a: dict) -> bool:
        return _num(a.get("exp")) - _num(a.get("pct")) > gap

    # Classificação bruta
    proprio_ids: list[str] = []
    fora_seq: list[tuple] = []
    for aid, a in acts.items():
        preds = edges.get(aid, [])
        real = _num(a.get("pct"))

        # fora de sequência: avançou com predecessor muito atrás
        for pred_id, _op, _lag in preds:
            p = acts.get(pred_id)
            if p and real > avanco_min and _num(p.get("pct")) < real - gap_pred:
                fora_seq.append((aid, pred_id, real, _num(p.get("pct"))))
                break

        if not atrasada(a):
            continue
        preds_incompletos = [pid for pid, _o, _l in preds
                             if acts.get(pid) and _num(acts[pid].get("pct")) < concluido]
        if preds and preds_incompletos:
            continue  # herdado — não abre pendência própria
        proprio_ids.append(aid)   # frente liberada (ou sem predecessor) e atrasado

    proprio_set = set(proprio_ids)

    def raio_impacto(raiz: str) -> int:
        """Sucessores a jusante, também atrasados, alcançáveis a partir da raiz."""
        visto, fila, n = set(), deque([raiz]), 0
        while fila:
            cur = fila.popleft()
            for succ in frente.get(cur, []):
                if succ in visto:
                    continue
                visto.add(succ)
                s = acts.get(succ)
                if s and atrasada(s):
                    n += 1
                    fila.append(succ)   # a cadeia continua a jusante
        return n

    pend: list[Pendencia] = []

    for aid in proprio_ids:
        a = acts[aid]
        wbs = a.get("wbs", "")
        pend.append(Pendencia(
            obra=obra, wbs_code=wbs, activity_id=aid,
            categoria="atraso_proprio",
            severidade=r.get("atraso_proprio", {}).get("severidade", 5),
            pct_real=_num(a.get("pct")), pct_esperado=_num(a.get("exp")),
            impacto=raio_impacto(aid),
            servico="", pavimento=_pavimento_de(wbs),
            causa_raiz={"frente_liberada": True},
        ))

    for aid, pred_id, real, pred_pct in fora_seq:
        a = acts[aid]
        wbs = a.get("wbs", "")
        pred_wbs = acts.get(pred_id, {}).get("wbs", "?")
        pend.append(Pendencia(
            obra=obra, wbs_code=wbs, activity_id=aid,
            categoria="fora_sequencia",
            severidade=r.get("fora_sequencia", {}).get("severidade", 4),
            pct_real=real, pct_esperado=_num(a.get("exp")),
            impacto=0, servico="", pavimento=_pavimento_de(wbs),
            causa_raiz={"predecessor_wbs": pred_wbs, "pred_pct": pred_pct},
        ))

    # Mais crítico primeiro: severidade, depois raio de impacto.
    pend.sort(key=lambda p: (p.severidade, p.impacto), reverse=True)
    return pend
