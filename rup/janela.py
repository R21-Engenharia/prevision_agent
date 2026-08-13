"""
rup/janela.py
=============
RUP por JANELA de tempo. A RUP é sempre RECALCULADA para a janela (Hh da janela
÷ produção da janela), nunca um filtro sobre a acumulada.

Janelas: mes_atual, mes_anterior, 6m, 12m, obra (+ estrutura pronta p/ custom via
lista de meses). Cada janela traz também a janela ANTERIOR comparável, para
variação (RUP menor = melhor produtividade).
"""
from __future__ import annotations

from datetime import date

JANELAS = ("mes_atual", "mes_anterior", "6m", "12m", "obra")
ROTULO = {
    "mes_atual": "Mês atual", "mes_anterior": "Mês anterior",
    "6m": "Últimos 6 meses", "12m": "Últimos 12 meses", "obra": "Obra inteira",
}


def _ym(y: int, m: int) -> str:
    return f"{y:04d}-{m:02d}"


def _desloca(ym: str, delta: int) -> str:
    y, m = map(int, ym.split("-"))
    idx = y * 12 + (m - 1) + delta
    return _ym(idx // 12, idx % 12 + 1)


def meses(janela: str, hoje: date | None = None,
          custom: list[str] | None = None) -> tuple[list[str] | None, list[str] | None]:
    """
    (meses_da_janela, meses_da_janela_anterior). None = todos os meses (obra).
    A janela anterior é o período imediatamente antes, de mesmo tamanho.
    """
    hoje = hoje or date.today()
    cur = _ym(hoje.year, hoje.month)
    if janela == "custom" and custom:
        return sorted(custom), None
    if janela == "mes_atual":
        return [cur], [_desloca(cur, -1)]
    if janela == "mes_anterior":
        a = _desloca(cur, -1)
        return [a], [_desloca(cur, -2)]
    if janela == "6m":
        return ([_desloca(cur, -i) for i in range(6)],
                [_desloca(cur, -i) for i in range(6, 12)])
    if janela == "12m":
        return ([_desloca(cur, -i) for i in range(12)],
                [_desloca(cur, -i) for i in range(12, 24)])
    return None, None  # obra


def rup_de(serie: dict[str, dict], janela_meses: list[str] | None) -> dict:
    """Hh/produção/RUP somando só os meses da janela (None = todos)."""
    ms = janela_meses if janela_meses is not None else list(serie.keys())
    hh = sum((serie.get(m) or {}).get("hh", 0.0) for m in ms)
    prod = sum((serie.get(m) or {}).get("producao", 0.0) for m in ms)
    return {"hh": round(hh, 1), "producao": round(prod, 2),
            "rup": round(hh / prod, 3) if (hh and prod) else None}


def com_variacao(serie: dict[str, dict], janela: str,
                 hoje: date | None = None, custom: list[str] | None = None) -> dict:
    """RUP da janela + da janela anterior + variação absoluta e percentual."""
    sel, ant = meses(janela, hoje, custom)
    atual = rup_de(serie, sel)
    anterior = rup_de(serie, ant) if ant is not None else {"rup": None}
    ra, rp = atual["rup"], anterior["rup"]
    var_abs = round(ra - rp, 3) if (ra is not None and rp) else None
    var_pct = round(100 * (ra - rp) / rp, 1) if (ra is not None and rp) else None
    return {
        **atual,
        "rup_anterior": rp,
        "variacao_abs": var_abs,
        "variacao_pct": var_pct,
        # tendência pela ótica da produtividade (RUP menor = melhor)
        "tendencia": ("piorou" if (var_abs or 0) > 0 else
                      "melhorou" if (var_abs or 0) < 0 else "estavel")
        if var_abs is not None else None,
    }
