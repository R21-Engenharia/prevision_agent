"""
rup/custo_mo.py
===============
Custo mensal e diário de mão de obra própria — memorial de cálculo R21.

Sem arredondamento intermediário; arredonda só na saída (2 casas). O BDI de MO
é parâmetro (default 0,25) — vem de Parâmetros Financeiros e entra no fim.

Colaborador sem custo financeiro (SC e LC ambos zero/branco) é DESCONSIDERADO
(custo_mes = None) — nunca gera divisão por zero nem número inventado.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date

BDI_MO_PADRAO = 0.25
DIAS_MES = 21

# ── Parâmetros por função: TR (anos), DD (dias doença/mês), TI (taxa incerteza) ──
_PARAMS: dict[str, tuple[float, float, float]] = {
    "analista financeiro": (2, 0.5, 0.010),
    "analista de engenharia": (2, 0.5, 0.005),
    "auxiliar financeiro": (2, 0.5, 0.010),
    "auxiliar administrativo": (2, 0.5, 0.010),
    "comprador": (2, 0.5, 0.030),
    "gerente de rh": (5, 0.5, 0.005),
    "analista de rh": (3, 0.5, 0.005),
    "mestre de obras": (3, 0.5, 0.005),
    "motorista": (3, 0.5, 0.005),
    "almoxarife": (3, 0.5, 0.020),
    "operador de grua": (2, 0.5, 0.030),
    "sinaleiro": (2, 0.5, 0.030),
    "guincheiro": (2, 0.5, 0.020),
    "armador": (2, 1.0, 0.030),
    "carpinteiro": (2, 1.0, 0.030),
    "pintor": (1.5, 1.5, 0.030),
    "pedreiro": (2, 1.0, 0.030),
    "meio oficial": (1.5, 1.0, 0.030),
    "servente": (0.5, 2.0, 0.050),
    "zelador": (1, 2.0, 0.050),
}
_PARAMS_PADRAO = (2, 1.0, 0.030)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.lower()).strip()


def params_funcao(func: str) -> tuple[float, float, float]:
    """(TR, DD, TI) da função; default (2; 1; 3%) se não constar na tabela."""
    return _PARAMS.get(_norm(func), _PARAMS_PADRAO)


def _inss(sc: float) -> float:
    if sc <= 1621.00:
        return sc * 0.075
    if sc <= 2902.85:
        return 121.58 + (sc - 1621.00) * 0.09
    if sc <= 4354.27:
        return 236.94 + (sc - 2902.85) * 0.12
    if sc <= 8475.55:
        return 411.11 + (sc - 4354.27) * 0.14
    return 988.09


def _irrf(sc: float, inss: float) -> float:
    ded = max(inss, 607.20)
    base = max(0.0, sc - ded)
    if base <= 2428.80:
        irtab = 0.0
    elif base <= 2826.65:
        irtab = (base - 2428.80) * 0.075
    elif base <= 3751.05:
        irtab = 29.84 + (base - 2826.65) * 0.15
    elif base <= 4664.68:
        irtab = 168.50 + (base - 3751.05) * 0.225
    else:
        irtab = 374.07 + (base - 4664.68) * 0.275
    red = 0.0 if sc > 7350.00 else min(irtab, max(0.0, 978.62 - 0.133145 * sc))
    return max(0.0, irtab - red)


def _tempo_casa(da: date | str | None, hoje: date) -> float:
    if not da:
        return 0.0
    if isinstance(da, str):
        try:
            da = date.fromisoformat(da[:10])
        except ValueError:
            return 0.0
    if da > hoje:
        return 0.0
    return (hoje - da).days / 365.0


def calcular(sc: float, lc: float, va: float, ob: float,
             da: date | str | None, func: str,
             bdi: float = BDI_MO_PADRAO, hoje: date | None = None) -> dict:
    """
    Custo mês/dia + memória de cálculo de um colaborador. Retorna
    {"desconsiderado": True} quando não há custo financeiro (SC e LC zerados).
    """
    sc = float(sc or 0)
    lc = float(lc or 0)
    va = float(va or 0)
    ob = float(ob or 0)
    if sc <= 0 and lc <= 0:
        return {"desconsiderado": True, "custo_mes": None, "custo_dia": None}

    hoje = hoje or date.today()
    tr, dd, ti = params_funcao(func)
    t = _tempo_casa(da, hoje)
    tref = max(t, tr)

    inss = _inss(sc)
    irrf = _irrf(sc, inss)

    # Encargos patronais
    p13 = sc / 12
    pfer = sc / 12
    pterco = sc / 36
    baseenc = sc + p13 + pfer + pterco
    fgts = baseenc * 0.08
    insspat = baseenc * 0.288
    enc = p13 + pfer + pterco + fgts + insspat

    # Rescisão (dispensa sem justa causa, aviso indenizado), horizonte TREF
    dias_aviso = min(90, 30 + 3 * int(tref))
    aviso = sc / 30 * dias_aviso
    proj_aviso = (sc / 12 + sc / 12 + sc / 36) * dias_aviso / 30
    fgts_aviso = (aviso + proj_aviso) * 0.08
    decimo = sc
    decimo_12 = sc / 12
    if tref > 2.2:
        ferias = sc * (tref - 2)
    elif tref > 1.2:
        ferias = sc * (tref - 1)
    else:
        ferias = sc * tref
    ferias_12 = sc / 12
    terco = ferias / 3
    terco_12 = (sc / 12) / 3
    multa_fgts = (tref * fgts * 12 + fgts_aviso) * 0.40
    rescisao_total = (aviso + proj_aviso + fgts_aviso + decimo + decimo_12
                      + ferias + ferias_12 + terco + terco_12 + multa_fgts)
    resc_mes = 0.0 if tref == 0 else rescisao_total / (tref * 12)

    # Custo sem riscos
    if lc == 0:
        custo = sc + va + ob + enc + resc_mes
    else:
        custo = lc + inss + irrf + va + ob + enc + resc_mes

    # Riscos
    doenca = custo / 20 * dd
    incertezas = (lc * 0.55 + custo * ti) if sc == 0 else custo * ti
    custo_total_mes = custo + doenca + incertezas

    custo_mes = custo_total_mes * (1 + bdi)
    custo_dia = custo_mes / DIAS_MES

    r2 = lambda x: round(x, 2)  # noqa: E731
    return {
        "desconsiderado": False,
        "tempo_casa": round(t, 2), "tref": round(tref, 2),
        "inss": r2(inss), "irrf": r2(irrf), "encargos": r2(enc),
        "dias_aviso": dias_aviso, "rescisao_total": r2(rescisao_total),
        "rescisao_mes": r2(resc_mes), "custo_sem_riscos": r2(custo),
        "doenca": r2(doenca), "incertezas": r2(incertezas),
        "custo_total_mes": r2(custo_total_mes),
        "bdi": bdi, "custo_mes": r2(custo_mes), "custo_dia": r2(custo_dia),
    }
