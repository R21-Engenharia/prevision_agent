"""
Corpo HTML do e-mail de pendências (Resend).
=============================================
100% table-based e estilos inline — à prova de Gmail/Outlook (nada de flex).
Estrutura: cabeçalho → resumo → DESTAQUES (o que trava mais) → por disciplina
→ tabelas (atrasos de obra / FVS pendentes) → rodapé.
"""
from __future__ import annotations

import datetime
import html as _html
import re

_ACCENT = "#C41230"
_OK = "#2F9E6A"
_INK = "#12151A"
_INK2 = "#363C44"
_MUTED = "#59616B"
_FAINT = "#8B939E"
_HAIR = "#E6E9ED"
_SOFT = "#FBEAED"
_OKSOFT = "#E9F6EF"
_ZEBRA = "#F6F7F9"


def _esc(s) -> str:
    return _html.escape(str(s or ""))


def _pav(nome: str) -> str:
    m = re.match(r"^\d+\s*º", nome or "")
    return m.group(0).replace(" ", "") if m else (nome or "—")


def _disc(servico: str) -> str:
    return servico.split("|")[0].strip() if servico and "|" in servico else "Outros"


def _cell(txt, extra="") -> str:
    return (f'<td style="padding:8px 12px;border-bottom:1px solid {_HAIR};'
            f'font-size:13px;color:{_INK};{extra}">{txt}</td>')


# ── Blocos ────────────────────────────────────────────────────────────────────

def _destaques(itens: list[dict]) -> str:
    """Top 3 gargalos com os serviços reais que travam."""
    top = sorted(itens, key=lambda p: -(p.get("impacto") or 0))[:3]
    top = [p for p in top if (p.get("impacto") or 0) > 0]
    if not top:
        return ""
    cards = ""
    for p in top:
        trava = (p.get("causa_raiz") or {}).get("trava") or []
        exemplos = ", ".join(
            f'{_esc(t.get("servico"))} <span style="color:{_FAINT}">{_pav(t.get("pavimento",""))}</span>'
            for t in trava[:2])
        cards += f"""
        <tr><td style="padding:0 0 8px 0">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                 style="background:{_SOFT};border-radius:10px">
            <tr>
              <td style="padding:12px 14px;border-left:4px solid {_ACCENT};border-radius:10px">
                <div style="font-size:14px;font-weight:700;color:{_INK}">
                  {_esc(p.get("servico"))}
                  <span style="font-weight:400;color:{_MUTED};font-size:12px"> · {_pav(p.get("pavimento",""))} · {(p.get("pct_real") or 0):.0f}%</span>
                </div>
                <div style="font-size:12px;color:{_ACCENT};font-weight:600;margin-top:3px">
                  trava {p.get("impacto")} serviços a jusante
                </div>
                {f'<div style="font-size:11.5px;color:{_MUTED};margin-top:4px">segura: {exemplos}</div>' if exemplos else ''}
              </td>
            </tr>
          </table>
        </td></tr>"""
    return f"""
    <tr><td style="padding:20px 0 4px 0">
      <div style="font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;
                  color:{_ACCENT};margin-bottom:10px">⚠ Prioridade — atacar primeiro</div>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0">{cards}</table>
    </td></tr>"""


def _por_disciplina(itens: list[dict], cor: str) -> str:
    d: dict[str, int] = {}
    for p in itens:
        k = _disc(p.get("servico", ""))
        d[k] = d.get(k, 0) + 1
    if not d:
        return ""
    tops = sorted(d.items(), key=lambda x: -x[1])[:6]
    chips = ""
    for nome, n in tops:
        chips += (f'<td style="padding:0 6px 6px 0"><span style="display:inline-block;'
                  f'background:{_ZEBRA};border:1px solid {_HAIR};border-radius:7px;'
                  f'padding:4px 10px;font-size:12px;color:{_INK2}">'
                  f'<b>{_esc(nome)}</b> <span style="color:{cor};font-weight:700">{n}</span></span></td>')
    return f"""
    <tr><td style="padding:14px 0 2px 0">
      <div style="font-size:12px;color:{_MUTED};margin-bottom:8px">Por disciplina</div>
      <table role="presentation" cellpadding="0" cellspacing="0"><tr>{chips}</tr></table>
    </td></tr>"""


def _tabela(titulo: str, cor: str, itens: list[dict], impacto: bool) -> str:
    if not itens:
        return ""
    col3 = "Trava" if impacto else "Avanço"
    linhas = ""
    for i, p in enumerate(itens[:12]):
        bg = _ZEBRA if i % 2 else "#FFFFFF"
        causa = p.get("causa_raiz") or {}
        jobs = causa.get("jobs_pendentes") or []
        falta = _esc(", ".join(j.get("name", "") for j in jobs[:2]) or "—")
        val = (f'<b style="color:{cor}">{p.get("impacto") or 0}</b>'
               if impacto else f'{(p.get("pct_real") or 0):.0f}%')
        linhas += (
            f'<tr style="background:{bg}">'
            + _cell(_esc(p.get("servico")), "font-weight:600")
            + _cell(_pav(p.get("pavimento", "")), f"font-size:12px;color:{_MUTED};white-space:nowrap")
            + _cell(val, "text-align:center;white-space:nowrap")
            + _cell(falta, f"font-size:12px;color:{_MUTED}")
            + '</tr>')
    extra = (f'<div style="font-size:11.5px;color:{_FAINT};margin-top:8px">'
             f'+ {len(itens) - 12} na planilha em anexo</div>' if len(itens) > 12 else '')
    return f"""
    <tr><td style="padding:22px 0 0 0">
      <div style="font-size:15px;font-weight:700;color:{_INK}">
        <span style="display:inline-block;width:9px;height:9px;border-radius:2px;background:{cor};
                     vertical-align:middle;margin-right:7px"></span>{_esc(titulo)}
        <span style="font-weight:400;color:{_MUTED};font-size:13px"> · {len(itens)}</span></div>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
             style="border:1px solid {_HAIR};border-radius:9px;overflow:hidden;margin-top:10px">
        <tr style="background:{_INK}">
          <th align="left" style="padding:8px 12px;font-size:11px;color:#fff;font-weight:600">Serviço</th>
          <th align="left" style="padding:8px 12px;font-size:11px;color:#fff;font-weight:600">Pav.</th>
          <th align="center" style="padding:8px 12px;font-size:11px;color:#fff;font-weight:600">{col3}</th>
          <th align="left" style="padding:8px 12px;font-size:11px;color:#fff;font-weight:600">O que falta</th>
        </tr>
        {linhas}
      </table>
      {extra}
    </td></tr>"""


def _stat(valor, rotulo, cor, bg) -> str:
    return (f'<td width="50%" style="padding:0 6px" valign="top">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="background:{bg};border-radius:10px"><tr><td style="padding:14px 16px">'
            f'<div style="font-size:28px;font-weight:700;color:{cor};line-height:1">{valor}</div>'
            f'<div style="font-size:11.5px;color:{_MUTED};margin-top:4px">{rotulo}</div>'
            f'</td></tr></table></td>')


def build_email_html(obra: str, pendencias: list[dict]) -> tuple[str, dict]:
    obra_itens, fvs_itens = [], []
    for p in pendencias:
        (fvs_itens if (p.get("causa_raiz") or {}).get("provavel_so_fvs") else obra_itens).append(p)
    obra_itens.sort(key=lambda p: -(p.get("impacto") or 0))
    fvs_itens.sort(key=lambda p: (p.get("pavimento") or ""))
    travados = sum(p.get("impacto") or 0 for p in obra_itens)
    hoje = datetime.date.today().strftime("%d/%m/%Y")

    corpo = (
        _destaques(obra_itens)
        + _por_disciplina(obra_itens, _ACCENT)
        + _tabela("Atrasos de obra", _ACCENT, obra_itens, True)
        + _tabela("Pendências de FVS", _OK, fvs_itens, False)
    )

    html = f"""\
<body style="margin:0;background:#EEF0F3;padding:24px 12px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">
<table role="presentation" width="640" cellpadding="0" cellspacing="0"
       style="max-width:640px;font-family:-apple-system,'Segoe UI',Roboto,Arial,sans-serif">
  <tr><td style="background:{_INK};border-radius:12px 12px 0 0;padding:20px 24px">
    <div style="font-size:18px;font-weight:700;color:#fff;letter-spacing:-.01em">
      R21 <span style="color:{_ACCENT}">·</span> Agente do Planejamento</div>
    <div style="font-size:11.5px;color:#9AA2AC;margin-top:3px;letter-spacing:.02em">
      MONITORAMENTO DE OBRAS</div>
  </td></tr>
  <tr><td style="background:#fff;border:1px solid {_HAIR};border-top:none;
                 border-radius:0 0 12px 12px;padding:22px 24px">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
      <td style="font-size:13.5px;color:{_MUTED}">
        <b style="color:{_INK};font-size:15px">{_esc(obra)}</b></td>
      <td align="right" style="font-size:12px;color:{_FAINT}">{hoje}</td>
    </tr></table>

    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
           style="margin:16px -6px 0"><tr>
      {_stat(len(obra_itens), 'atrasos de obra', _ACCENT, _SOFT)}
      {_stat(len(fvs_itens), 'FVS pendentes', _OK, _OKSOFT)}
    </tr></table>
    <div style="font-size:12px;color:{_MUTED};margin-top:10px;text-align:center">
      {travados} serviços travados no total</div>

    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      {corpo}
    </table>

    <div style="font-size:11px;color:{_FAINT};margin-top:24px;border-top:1px solid {_HAIR};
                padding-top:14px;line-height:1.5">
      Relatório automático do <b style="color:{_MUTED}">Agente Inteligente de Priorização</b>.
      A planilha completa (todos os itens) segue em anexo.
    </div>
  </td></tr>
</table>
</td></tr></table>
</body>"""
    return html, {"atrasos": len(obra_itens), "fvs": len(fvs_itens), "travados": travados}
