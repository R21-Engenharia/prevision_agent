"""
Corpo HTML do e-mail de pendências (Resend).
=============================================
HTML "email-safe": estilos inline, tabelas para layout. Resumo consolidado
por obra — atrasos de obra (foco impacto) e FVS pendentes (foco preencher).
"""
from __future__ import annotations

import datetime
import html as _html

_ACCENT = "#C41230"
_OK = "#2F9E6A"
_INK = "#12151A"
_MUTED = "#59616B"
_HAIR = "#E6E9ED"


def _esc(s) -> str:
    return _html.escape(str(s or ""))


def _pav_curto(nome: str) -> str:
    import re
    m = re.match(r"^\d+\s*º", nome or "")
    return m.group(0).replace(" ", "") if m else (nome or "")


def _linha(p: dict, cor: str, mostra_impacto: bool) -> str:
    causa = p.get("causa_raiz") or {}
    jobs = causa.get("jobs_pendentes") or []
    falta = ", ".join(j.get("name", "") for j in jobs[:2]) or "—"
    destaque = (f'<b style="color:{cor}">trava {p.get("impacto") or 0}</b>'
                if mostra_impacto else f'{(p.get("pct_real") or 0):.0f}%')
    return (
        '<tr>'
        f'<td style="padding:7px 10px;border-bottom:1px solid {_HAIR};font-size:13px;color:{_INK}">'
        f'{_esc(p.get("servico"))}</td>'
        f'<td style="padding:7px 10px;border-bottom:1px solid {_HAIR};font-size:12px;color:{_MUTED}">'
        f'{_esc(_pav_curto(p.get("pavimento", "")))}</td>'
        f'<td style="padding:7px 10px;border-bottom:1px solid {_HAIR};font-size:12px;'
        f'text-align:center">{destaque}</td>'
        f'<td style="padding:7px 10px;border-bottom:1px solid {_HAIR};font-size:12px;color:{_MUTED}">'
        f'{_esc(falta)}</td>'
        '</tr>'
    )


def _bloco(titulo: str, subtitulo: str, cor: str, itens: list[dict],
           mostra_impacto: bool) -> str:
    if not itens:
        return ""
    linhas = "".join(_linha(p, cor, mostra_impacto) for p in itens[:12])
    col3 = "Trava" if mostra_impacto else "Avanço"
    return f"""
    <div style="margin:22px 0 6px">
      <div style="font-size:15px;font-weight:700;color:{_INK}">{_esc(titulo)}
        <span style="font-weight:400;color:{_MUTED};font-size:12px"> · {len(itens)}</span></div>
      <div style="font-size:12px;color:{_MUTED};margin:2px 0 10px">{_esc(subtitulo)}</div>
      <table style="width:100%;border-collapse:collapse;border:1px solid {_HAIR};border-radius:8px">
        <tr style="background:{_INK}">
          <th style="padding:7px 10px;text-align:left;font-size:11px;color:#fff">Serviço</th>
          <th style="padding:7px 10px;text-align:left;font-size:11px;color:#fff">Pav.</th>
          <th style="padding:7px 10px;text-align:center;font-size:11px;color:#fff">{col3}</th>
          <th style="padding:7px 10px;text-align:left;font-size:11px;color:#fff">O que falta</th>
        </tr>
        {linhas}
      </table>
    </div>"""


def build_email_html(obra: str, pendencias: list[dict]) -> tuple[str, dict]:
    """Devolve (html, resumo{atrasos, fvs}). Ordena atrasos por impacto."""
    obra_itens, fvs_itens = [], []
    for p in pendencias:
        if (p.get("causa_raiz") or {}).get("provavel_so_fvs"):
            fvs_itens.append(p)
        else:
            obra_itens.append(p)
    obra_itens.sort(key=lambda p: -(p.get("impacto") or 0))
    fvs_itens.sort(key=lambda p: (p.get("pavimento") or ""))
    hoje = datetime.date.today().strftime("%d/%m/%Y")

    corpo = _bloco("Atrasos de obra", "serviços que travam o cronograma — priorizados por impacto",
                   _ACCENT, obra_itens, True)
    corpo += _bloco("Pendências de FVS", "obra ~pronta, falta preencher a ficha",
                    _OK, fvs_itens, False)

    html = f"""
    <div style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;max-width:680px;
                margin:0 auto;color:{_INK}">
      <div style="background:{_INK};border-radius:12px 12px 0 0;padding:18px 22px">
        <div style="font-size:17px;font-weight:700;color:#fff">R21 · Agente do Planejamento</div>
        <div style="font-size:12px;color:#B9C0C9;margin-top:2px">Monitoramento de obras</div>
      </div>
      <div style="border:1px solid {_HAIR};border-top:none;border-radius:0 0 12px 12px;padding:22px">
        <div style="font-size:14px;color:{_MUTED}">Obra: <b style="color:{_INK}">{_esc(obra)}</b>
          &nbsp;·&nbsp; {hoje}</div>
        <div style="display:flex;gap:12px;margin:16px 0">
          <div style="flex:1;background:#FBEAED;border-radius:10px;padding:12px 14px">
            <div style="font-size:26px;font-weight:700;color:{_ACCENT}">{len(obra_itens)}</div>
            <div style="font-size:11px;color:{_MUTED}">atrasos de obra</div></div>
          <div style="flex:1;background:#E9F6EF;border-radius:10px;padding:12px 14px">
            <div style="font-size:26px;font-weight:700;color:{_OK}">{len(fvs_itens)}</div>
            <div style="font-size:11px;color:{_MUTED}">FVS pendentes</div></div>
        </div>
        {corpo}
        <div style="font-size:11px;color:#8B939E;margin-top:22px;border-top:1px solid {_HAIR};
                    padding-top:12px">
          Relatório automático do Agente Inteligente. A planilha completa segue em anexo.
        </div>
      </div>
    </div>"""
    return html, {"atrasos": len(obra_itens), "fvs": len(fvs_itens)}
