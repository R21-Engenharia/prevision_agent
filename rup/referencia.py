"""
rup/referencia.py
=================
Banco de RUP de referência do parceiro (mín/méd/máx por pacote), agregado por
disciplina/célula para comparar com a nossa RUP real.

O parceiro tem ~29 pacotes (ALVENARIA tem 5 variantes, REVESTIMENTO ARGAMASSADO
tem INTERNO/EXTERNO...). Como a nossa célula é a disciplina, agregamos a faixa
por disciplina: mín = menor mín, máx = maior máx, méd = média das médias. Assim
cada célula ganha uma faixa de referência coerente.
"""
from __future__ import annotations

import json
from statistics import median
from pathlib import Path

_REF = Path(__file__).resolve().parent.parent / "data" / "rup_referencia.json"


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def bandas_por_disciplina() -> dict[str, dict]:
    """disciplina -> {min, med, max, pacotes:[nomes do parceiro]}."""
    from rup.depara import disciplinas_de
    if not _REF.exists():
        return {}
    pacotes = json.loads(_REF.read_text(encoding="utf-8")).get("pacotes", [])
    agrup: dict[str, dict] = {}
    for p in pacotes:
        mn, md, mx = _num(p.get("min")), _num(p.get("med")), _num(p.get("max"))
        if mn is None or mx is None:
            continue
        for disc in disciplinas_de(p.get("pacote", "")) or {"outros"}:
            a = agrup.setdefault(disc, {"mins": [], "meds": [], "maxs": [], "pacotes": []})
            a["mins"].append(mn)
            a["maxs"].append(mx)
            if md is not None:
                a["meds"].append(md)
            a["pacotes"].append(p.get("pacote"))
    out = {}
    for disc, a in agrup.items():
        # Mediana das variantes = faixa TÍPICA da disciplina, sem ser puxada pelos
        # extremos (ex.: Alvenaria Sical mín 0,3 x Maciço máx 2,6 daria 0,3-2,6,
        # inútil). A mediana traz 0,51-0,98, que é a alvenaria comum.
        out[disc] = {
            "min": round(median(a["mins"]), 2),
            "max": round(median(a["maxs"]), 2),
            "med": round(median(a["meds"]), 2) if a["meds"] else None,
            "pacotes": a["pacotes"],
        }
    return out


def status(rup: float | None, banda: dict | None) -> str:
    """dentro | acima | abaixo | sem_rup | sem_ref."""
    if rup is None:
        return "sem_rup"
    if not banda:
        return "sem_ref"
    if rup < banda["min"]:
        return "abaixo"
    if rup > banda["max"]:
        return "acima"
    return "dentro"
