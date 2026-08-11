"""
rup/depara.py
=============
De-para FVS → EAP (Sienge) por sugestão automática, discipline-aware.

O casamento ingênuo por descrição falha: "Execução de Forma" e "Execução de
Contrapiso" compartilham "execução de" e o SequenceMatcher cola os dois. Aqui a
pontuação é dominada pela DISCIPLINA (reboco, alvenaria, forma, armadura...),
resolvendo sinônimos entre as taxonomias (FVS "Reboco" ↔ Sienge "Revestimento
de Argamassa"). Sobreposição de palavras entra só como desempate.

Não decide nada sozinho: entrega os N melhores candidatos com score, para o
planejamento confirmar. Prefere itens "MOE" (mão de obra empreitada), que são
os que fazem sentido cruzar com Hh.
"""
from __future__ import annotations

import re
import unicodedata

# disciplina canônica -> gatilhos (aparecendo em FVS ou na EAP Sienge)
DISCIPLINAS: dict[str, list[str]] = {
    "reboco":          ["reboco", "emboco", "revestimento de argamassa", "argamassa"],
    "chapisco":        ["chapisco"],
    "alvenaria":       ["alvenaria", "bloco ceramico", "bloco de concreto", "vedacao"],
    "contrapiso":      ["contrapiso", "regularizacao de piso"],
    "pintura":         ["pintura", "massa corrida", "textura", "selador"],
    "ceramico":        ["ceramico", "porcelanato", "azulejo", "assentamento de piso",
                        "revestimento ceramico", "rejunte"],
    "forma":           ["forma", "forma de laje", "forma de pilar", "forma de viga",
                        "escoramento"],
    "armadura":        ["armadura", "armacao", "aco ca", "ferragem"],
    "concretagem":     ["concretagem", "concreto usinado", "lancamento de concreto"],
    "desforma":        ["desforma", "desmontagem de forma"],
    "gesso":           ["gesso", "forro de gesso", "drywall"],
    "impermeabilizacao": ["impermeabilizacao", "manta asfaltica", "argamassa polimerica"],
    "eletrica":        ["eletrica", "eletrico", "enfiacao", "cabeamento", "eletrodutos"],
    "hidro":           ["hidrossanitaria", "hidraulica", "hidro", "tubulacao",
                        "agua fria", "esgoto", "prumada hidraulica"],
    "gas":             ["gas glp", "rede de gas", " gas", "glp"],
    "contramarco":     ["contramarco"],
    "esquadria":       ["esquadria", "aluminio", "janela", "porta", "batente"],
    "forro":           ["forro"],
    "nicho":           ["nicho"],
    "shaft":           ["shaft"],
    "climatizacao":    ["climatizacao", "ar condicionado", "exaustao", "coifa", "ventilacao"],
    "impermeab_reservatorio": ["reservatorio", "caixa d'agua", "caixa dagua"],
    "calcada":         ["calcada", "passeio"],
    "pingadeira":      ["pingadeira", "granito"],
    "alisamento":      ["alisamento", "polimento", "polido"],
    "encunhamento":    ["encunhamento", "encunha"],
    "preventivo":      ["preventivo", "hidrante", "incendio", "sprinkler", "shp",
                        "combate a incendio"],
    "refratario":      ["refratario", "churrasqueira"],
    "elevador":        ["elevador"],
    "iluminacao":      ["iluminacao", "luminaria"],
}

_STOP = {
    "execucao", "de", "da", "do", "das", "dos", "e", "em", "para", "com", "moe",
    "a", "o", "as", "os", "no", "na", "nos", "nas", "1", "2", "3", "etapa",
    "servico", "inclui", "estimativa", "fvs", "obsoleto", "vazia", "vazio",
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]", " ", s.lower())


def _tokens(s: str) -> set[str]:
    return {t for t in _norm(s).split() if len(t) > 2 and t not in _STOP}


def disciplinas_de(texto: str) -> set[str]:
    n = " " + _norm(texto) + " "
    achadas = set()
    for disc, gatilhos in DISCIPLINAS.items():
        if any(g in n for g in gatilhos):
            achadas.add(disc)
    return achadas


def score(fvs_nome: str, eap_desc: str) -> tuple[float, set[str]]:
    """Pontua um par (FVS, item EAP). Disciplina domina; palavras desempatam."""
    d_fvs = disciplinas_de(fvs_nome)
    d_eap = disciplinas_de(eap_desc)
    comuns = d_fvs & d_eap

    t_fvs, t_eap = _tokens(fvs_nome), _tokens(eap_desc)
    overlap = len(t_fvs & t_eap) / max(1, len(t_fvs)) if t_fvs else 0.0

    # 3 pontos por disciplina em comum + até 1 ponto de sobreposição de palavras.
    s = 3.0 * len(comuns) + overlap
    return s, comuns


_FISICA = {"m2", "m3", "m", "kg", "un", "pto", "pt", "unid"}


def agrupar_servicos(eap: list[dict]) -> list[dict]:
    """
    Agrupa os itens da EAP por serviço (descrição idêntica), somando a quantidade
    executada e a orçada — porque splits do mesmo serviço (torres/blocos) têm
    descrição igual e devem ser somados (decisão de negócio do Elrik).
    """
    from collections import defaultdict
    g: dict[str, dict] = defaultdict(lambda: {
        "descricao": "", "qtd_executada": 0.0, "qtd_orcada": 0.0,
        "unidade": None, "refs": [], "mao_de_obra": False, "n_linhas": 0})
    for e in eap:
        d = e.get("descricao") or ""
        grp = g[d]
        grp["descricao"] = d
        if e.get("qtd_executada"):
            grp["qtd_executada"] += e["qtd_executada"]
        if e.get("qtd_orcada"):
            grp["qtd_orcada"] += e["qtd_orcada"]
        grp["unidade"] = e.get("unidade_sienge") or e.get("unidade") or grp["unidade"]
        if e.get("referencia_sienge"):
            grp["refs"].append(e["referencia_sienge"])
        grp["mao_de_obra"] = grp["mao_de_obra"] or bool(e.get("mao_de_obra"))
        grp["n_linhas"] += 1
    return list(g.values())


def sugerir_servicos(fvs_nome: str, grupos: list[dict], n: int = 3) -> list[dict]:
    """
    Top-N SERVIÇOS (grupos) candidatos para uma FVS. Além da disciplina, prefere
    fortemente linhas de mão de obra (MOE) com unidade física — que são as que
    fazem sentido no denominador da RUP (verba/material caem no fim).
    """
    ranked = []
    for grp in grupos:
        s, comuns = score(fvs_nome, grp["descricao"])
        if s <= 0:
            continue
        bonus = (1.5 if grp["mao_de_obra"] else 0.0)
        bonus += (0.8 if grp["unidade"] in _FISICA else -1.2)  # penaliza vb/mes/dia
        ranked.append({**grp, "score": round(s + bonus, 2), "disciplinas": sorted(comuns)})
    ranked.sort(key=lambda c: c["score"], reverse=True)
    return ranked[:n]


def sugerir(fvs_nome: str, eap: list[dict], n: int = 3) -> list[dict]:
    """
    Top-N candidatos da EAP para uma FVS. Itens MOE (mão de obra) primeiro no
    desempate. Cada candidato traz score, disciplinas casadas e a referência
    Sienge — mas a decisão é do humano.
    """
    ranked = []
    for item in eap:
        s, comuns = score(fvs_nome, item.get("descricao", ""))
        if s <= 0:
            continue
        ranked.append({
            "code": item.get("code"),
            "descricao": item.get("descricao"),
            "unidade": item.get("unidade"),
            "referencia_sienge": item.get("referencia_sienge"),
            "mao_de_obra": item.get("mao_de_obra", False),
            "score": round(s, 2),
            "disciplinas": sorted(comuns),
        })
    # ordena por score; empate favorece MOE e unidade física
    ranked.sort(key=lambda c: (c["score"], c["mao_de_obra"],
                               c["unidade"] in ("m2", "m3", "m", "un")), reverse=True)
    return ranked[:n]


def confianca(candidatos: list[dict]) -> str:
    """Rótulo de confiança do melhor candidato, para triagem do revisor."""
    if not candidatos:
        return "sem_candidato"
    top = candidatos[0]
    if not top["disciplinas"]:
        return "baixa"                      # casou só por palavra solta
    outros_mesma_disc = [c for c in candidatos[1:]
                         if set(c["disciplinas"]) & set(top["disciplinas"])
                         and c["score"] >= top["score"] - 0.5]
    if outros_mesma_disc:
        return "escolher"                   # disciplina certa, 2-3 sub-itens p/ escolher
    return "alta"
