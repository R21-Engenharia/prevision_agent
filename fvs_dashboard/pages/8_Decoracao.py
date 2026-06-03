"""
Pagina 8 — Decoracao
=====================
Cronograma executivo e indicadores das atividades de acabamento/decoracao.
Dados: cache Prevision (activities_raw + jobs_raw).

Funcionalidades:
- Filtros: obra, disciplina, status, periodo, pavimentos especificos
- Gantt interativo (por pavimento ou disciplina)
- Alertas de atividades com prazo vencido e 0% de avanco
- Exportacao PDF A4 paisagem (Gantt + pizza + barras)
"""

from __future__ import annotations

import copy
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fvs_dashboard.core.decoracao_engine import (
    DISC_COLORS,
    DISCIPLINES,
    STATUS_COLORS,
    build_discipline_summary,
    build_floor_gantt,
    compute_kpis,
    load_decoracao,
)
from fvs_dashboard.core.data_manager import OBRAS

# ─── Helpers de UI ────────────────────────────────────────────────────────────

def _kpi(label: str, value: str, delta: str = "", color: str = "#C41230") -> str:
    delta_html = (
        f'<div style="font-size:11px;font-weight:600;color:{color};margin-top:2px;">{delta}</div>'
        if delta else ""
    )
    return (
        f'<div style="background:#fff;border-radius:8px;padding:14px 18px;'
        f'border-top:3px solid {color};box-shadow:0 2px 8px rgba(0,0,0,0.06);">'
        f'<div style="font-size:10px;font-weight:700;color:#888;text-transform:uppercase;'
        f'letter-spacing:.5px;margin-bottom:4px;">{label}</div>'
        f'<div style="font-size:26px;font-weight:800;color:#1A1A1A;line-height:1">{value}</div>'
        f'{delta_html}</div>'
    )


def _section(title: str) -> None:
    st.markdown(
        f'<div style="font-size:11px;font-weight:700;color:#C41230;text-transform:uppercase;'
        f'letter-spacing:1px;margin:18px 0 8px 0;border-bottom:1px solid #E8E8E8;'
        f'padding-bottom:4px;">{title}</div>',
        unsafe_allow_html=True,
    )


# ─── PDF ──────────────────────────────────────────────────────────────────────

def _export_pdf_decoracao(
    fig_gantt: go.Figure,
    fig_pie: go.Figure | None,
    fig_bar: go.Figure | None,
    kpis: dict,
    alertas_df: pd.DataFrame,
    obra_sel: str,
    gantt_mode: str,
    n_floors: int,
    n_ativs: int,
) -> bytes:
    """Gera PDF A4 paisagem com Gantt + graficos + alertas."""
    import io as _io
    from reportlab.lib import colors as rlc
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.platypus import (
        HRFlowable, Image as RLImage, Paragraph, SimpleDocTemplate,
        Spacer, Table, TableStyle,
    )

    # ── render em paralelo ────────────────────────────────────────────────────
    LW, LH = landscape(A4)
    M      = 1.2 * cm
    use_w  = LW - 2 * M   # ~814 pt
    use_h  = LH - 2 * M   # ~540 pt

    gantt_h_px = min(max(n_floors * 22 + 100, 350), 700)
    jobs = {
        "gantt": (fig_gantt, int(use_w * 3.2), int(gantt_h_px * 3)),
    }
    if fig_pie is not None:
        jobs["pie"] = (fig_pie, 700, 580)
    if fig_bar is not None:
        jobs["bar"] = (fig_bar, 1300, 580)

    rendered: dict[str, bytes] = {}
    with ThreadPoolExecutor(max_workers=len(jobs)) as ex:
        def _render(fig, w, h):
            f = copy.deepcopy(fig)
            f.update_layout(paper_bgcolor="white", plot_bgcolor="white")
            return pio.to_image(f, format="png", width=w, height=h, scale=2)

        fs = {ex.submit(_render, fig, w, h): key for key, (fig, w, h) in jobs.items()}
        for fut in as_completed(fs):
            rendered[fs[fut]] = fut.result()

    # ── estilos ───────────────────────────────────────────────────────────────
    C_RED   = rlc.HexColor("#C41230")
    C_DARK  = rlc.HexColor("#1A1A2E")
    C_GRAY  = rlc.HexColor("#666666")
    C_LGRAY = rlc.HexColor("#DDDDDD")
    C_GREEN = rlc.HexColor("#27AE60")
    C_ORANGE= rlc.HexColor("#F6A623")

    def _ps(nm, **kw): return ParagraphStyle(nm, **kw)

    sty_title   = _ps("t",  fontSize=16, fontName="Helvetica-Bold", textColor=C_RED,  spaceAfter=2)
    sty_sub     = _ps("s",  fontSize=8,  fontName="Helvetica",      textColor=C_GRAY, spaceAfter=4)
    sty_section = _ps("sc", fontSize=10, fontName="Helvetica-Bold", textColor=C_DARK, spaceBefore=6, spaceAfter=3)
    sty_footer  = _ps("f",  fontSize=6,  fontName="Helvetica",      textColor=C_GRAY, alignment=TA_CENTER)
    sty_cell_c  = _ps("cc", fontSize=7,  fontName="Helvetica",      textColor=C_GRAY, alignment=TA_CENTER)
    sty_cell_v  = _ps("cv", fontSize=14, fontName="Helvetica-Bold", textColor=C_DARK, alignment=TA_CENTER)
    sty_alert   = _ps("al", fontSize=7,  fontName="Helvetica",      textColor=C_GRAY)

    # ── documento ─────────────────────────────────────────────────────────────
    buf = _io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        leftMargin=M, rightMargin=M, topMargin=M, bottomMargin=M,
        title="Decoracao e Acabamentos",
        author="R21 Empreendimentos",
    )

    story = []

    # cabecalho
    story.append(Paragraph("Decoracao e Acabamentos — Cronograma Executivo", sty_title))
    story.append(Paragraph(
        f"<b>{obra_sel}</b>  ·  {n_floors} pavimentos  ·  {n_ativs} atividades  ·  "
        f"Agrupado por: {gantt_mode}  ·  Gerado em {date.today().strftime('%d/%m/%Y')}",
        sty_sub,
    ))
    story.append(HRFlowable(width="100%", thickness=2, color=C_RED, spaceAfter=6))

    # KPIs como tabela
    kpi_labels = ["Total", "Finalizadas", "Em Andamento", "Nao Iniciadas", "Atrasadas", "Avanco Medio"]
    kpi_values = [
        str(kpis.get("total", 0)),
        str(kpis.get("finalizada", 0)),
        str(kpis.get("em_andamento", 0)),
        str(kpis.get("nao_iniciada", 0)),
        str(kpis.get("atrasada", 0)),
        f'{kpis.get("pct_medio", 0)}%',
    ]
    kpi_colors = [C_DARK, C_GREEN, rlc.HexColor("#2980B9"),
                  rlc.HexColor("#95A5A6"), C_RED, C_ORANGE]
    kw = use_w / 6

    def _kpi_cell(label, value, color):
        return Table(
            [[Paragraph(value, _ps("kv", fontSize=18, fontName="Helvetica-Bold",
                                   textColor=color, alignment=TA_CENTER))],
             [Paragraph(label, sty_cell_c)]],
            colWidths=[kw - 0.4*cm],
            style=TableStyle([
                ("ALIGN", (0,0), (-1,-1), "CENTER"),
                ("TOPPADDING", (0,0), (-1,-1), 2),
                ("BOTTOMPADDING", (0,0), (-1,-1), 2),
            ]),
        )

    kpi_row = Table(
        [[_kpi_cell(l, v, c) for l, v, c in zip(kpi_labels, kpi_values, kpi_colors)]],
        colWidths=[kw] * 6,
        style=TableStyle([
            ("ALIGN",  (0,0), (-1,-1), "CENTER"),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("BOX",    (0,0), (-1,-1), 0.5, C_LGRAY),
            ("INNERGRID", (0,0), (-1,-1), 0.3, C_LGRAY),
            ("BACKGROUND", (0,0), (-1,-1), rlc.HexColor("#F8F9FA")),
            ("TOPPADDING",    (0,0), (-1,-1), 6),
            ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ]),
    )
    story.append(kpi_row)
    story.append(Spacer(1, 0.3*cm))

    # Gantt
    story.append(Paragraph("Cronograma", sty_section))
    if "gantt" in rendered:
        gantt_pt_h = (use_h * 0.52)
        story.append(RLImage(_io.BytesIO(rendered["gantt"]), width=use_w, height=gantt_pt_h))

    # Graficos secundarios
    if "pie" in rendered or "bar" in rendered:
        story.append(Spacer(1, 0.2*cm))
        story.append(HRFlowable(width="100%", thickness=1, color=C_LGRAY, spaceAfter=4))
        story.append(Paragraph("Distribuicao por Disciplina e Avanco por Pavimento", sty_section))

        pie_w = use_w * 0.33
        bar_w = use_w * 0.65
        chart_h = use_h * 0.22

        cells = []
        if "pie" in rendered:
            cells.append(RLImage(_io.BytesIO(rendered["pie"]), width=pie_w, height=chart_h))
        else:
            cells.append(Paragraph("", sty_cell_c))

        if "bar" in rendered:
            cells.append(RLImage(_io.BytesIO(rendered["bar"]), width=bar_w, height=chart_h))
        else:
            cells.append(Paragraph("", sty_cell_c))

        chart_row = Table([cells], colWidths=[pie_w + 0.4*cm, bar_w],
                          style=TableStyle([("VALIGN", (0,0), (-1,-1), "TOP")]))
        story.append(chart_row)

    # Alertas
    if not alertas_df.empty:
        story.append(Spacer(1, 0.2*cm))
        story.append(HRFlowable(width="100%", thickness=1, color=C_RED, spaceAfter=4))
        story.append(Paragraph(
            f"Alertas — {len(alertas_df)} atividades com prazo vencido (0% avanco)",
            _ps("al_h", fontSize=9, fontName="Helvetica-Bold", textColor=C_RED),
        ))
        al_data = [["WBS", "Pavimento", "Servico", "Inicio Previsto", "Dias em Atraso"]]
        for _, row in alertas_df.head(15).iterrows():
            al_data.append([
                row.get("wbs", ""),
                row.get("floor_short", "")[:28],
                row.get("job_name", "")[:35],
                str(row.get("start", "")),
                str(row.get("dias_atraso", "")),
            ])
        al_table = Table(al_data, colWidths=[1.5*cm, 5*cm, 6*cm, 3*cm, 2.5*cm])
        al_table.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,0), C_RED),
            ("TEXTCOLOR",     (0,0), (-1,0), rlc.white),
            ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",      (0,0), (-1,-1), 6),
            ("ROWBACKGROUNDS",(0,1), (-1,-1), [rlc.HexColor("#FFF5F5"), rlc.white]),
            ("GRID",          (0,0), (-1,-1), 0.3, C_LGRAY),
            ("TOPPADDING",    (0,0), (-1,-1), 3),
            ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ]))
        story.append(al_table)

    # rodape
    story.append(Spacer(1, 0.2*cm))
    story.append(HRFlowable(width="100%", thickness=1, color=C_LGRAY))
    story.append(Paragraph(
        "R21 Empreendimentos  ·  FVS Dashboard  ·  Fonte: Prevision (activities_raw + jobs_raw)",
        sty_footer,
    ))

    doc.build(story)
    buf.seek(0)
    return buf.read()


# ─── Cache de dados ───────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def _cached_load(obra_key: str) -> pd.DataFrame:
    obra = None if obra_key == "Todas as obras" else obra_key
    return load_decoracao(obra)


# ═══════════════════════════════════════════════════════════════════════════════
# PAGINA
# ═══════════════════════════════════════════════════════════════════════════════

st.markdown("""
<div style="background:linear-gradient(135deg,#1A1A2E 0%,#16213E 60%,#0F3460 100%);
    padding:20px 28px 16px;border-radius:12px;margin-bottom:22px;
    border-left:5px solid #C41230;">
    <div style="font-size:11px;font-weight:700;color:#C41230;
        text-transform:uppercase;letter-spacing:2px;margin-bottom:6px;">
        R21 Empreendimentos
    </div>
    <div style="font-size:24px;font-weight:800;color:#fff;letter-spacing:-.3px;">
        🏛️ Decoracao &amp; Acabamentos
    </div>
    <div style="font-size:12px;color:rgba(255,255,255,0.6);margin-top:5px;">
        Cronograma executivo · Pacotes Prevision · activities_raw + jobs_raw
    </div>
</div>
""", unsafe_allow_html=True)

# ─── Filtros — linha 1 ────────────────────────────────────────────────────────
f1, f2, f3, f4 = st.columns([2, 2, 2, 2])

with f1:
    obra_sel = st.selectbox(
        "**Obra**",
        ["Todas as obras"] + list(OBRAS.keys()),
        key="dec_obra",
    )

with st.spinner("Carregando atividades de decoracao..."):
    df_raw = _cached_load(obra_sel)

if df_raw.empty:
    st.warning("Nenhuma atividade encontrada. Verifique se os caches Prevision estao atualizados.")
    st.stop()

today = date.today()
disc_opts   = ["Todas"]  + sorted(df_raw["discipline"].unique().tolist())
status_opts = ["Todos", "Finalizada", "Em andamento", "Nao iniciada", "Atrasada"]

with f2:
    disc_sel = st.selectbox("**Disciplina**", disc_opts, key="dec_disc")
with f3:
    status_sel = st.selectbox("**Status**", status_opts, key="dec_status")
with f4:
    date_range = st.date_input(
        "**Periodo**",
        value=(df_raw["start"].min(), df_raw["end"].max()),
        min_value=df_raw["start"].min(),
        max_value=df_raw["end"].max(),
        format="DD/MM/YYYY",
        key="dec_period",
    )

# ─── Filtros — linha 2: pavimentos especificos ────────────────────────────────
# Ordena pavimentos por floor_pos para facilitar a selecao
_floor_order = (
    df_raw[["floor", "floor_pos"]]
    .drop_duplicates()
    .sort_values("floor_pos")["floor"]
    .tolist()
)
floor_sel = st.multiselect(
    "**Pavimentos especificos**  *(deixe em branco para todos)*",
    options=_floor_order,
    default=[],
    placeholder="Todos os pavimentos",
    key="dec_floors",
)

# ─── Aplica filtros ───────────────────────────────────────────────────────────
df = df_raw.copy()
if disc_sel != "Todas":
    df = df[df["discipline"] == disc_sel]
if status_sel != "Todos":
    df = df[df["status"] == status_sel]
if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    df = df[(df["start"] >= date_range[0]) & (df["end"] <= date_range[1])]
if floor_sel:
    df = df[df["floor"].isin(floor_sel)]

if df.empty:
    st.info("Nenhuma atividade corresponde aos filtros selecionados.")
    st.stop()

# ─── KPIs ─────────────────────────────────────────────────────────────────────
kpis = compute_kpis(df)
st.markdown("")

k1, k2, k3, k4, k5, k6 = st.columns(6)
with k1:
    st.markdown(_kpi("Total", str(kpis["total"]), color="#1A1A1A"), unsafe_allow_html=True)
with k2:
    pct_fin = f'{kpis["finalizada"] * 100 // max(kpis["total"], 1)}%'
    st.markdown(_kpi("Finalizadas", str(kpis["finalizada"]), delta=pct_fin, color="#27AE60"),
                unsafe_allow_html=True)
with k3:
    st.markdown(_kpi("Em Andamento", str(kpis["em_andamento"]), color="#2980B9"),
                unsafe_allow_html=True)
with k4:
    st.markdown(_kpi("Nao Iniciadas", str(kpis["nao_iniciada"]), color="#95A5A6"),
                unsafe_allow_html=True)
with k5:
    _at_color = "#C41230" if kpis["atrasada"] > 0 else "#95A5A6"
    st.markdown(_kpi("Atrasadas", str(kpis["atrasada"]), color=_at_color),
                unsafe_allow_html=True)
with k6:
    st.markdown(_kpi("Avanco Medio", f'{kpis["pct_medio"]}%',
                     delta=f'{kpis["proximas_30d"]} iniciam em 30d', color="#F6A623"),
                unsafe_allow_html=True)

st.markdown("<div style='margin-top:6px'></div>", unsafe_allow_html=True)
st.divider()

# ─── Cronograma Gantt ─────────────────────────────────────────────────────────
_section("Cronograma de Decoracao")

g_col1, g_col2 = st.columns([3, 1])
with g_col2:
    gantt_mode = st.radio(
        "Agrupar por",
        ["Pavimento", "Disciplina"],
        horizontal=True,
        key="dec_gantt_mode",
        label_visibility="collapsed",
    )
with g_col1:
    st.caption(
        f"**{len(df['floor'].unique())} pavimentos** · "
        f"**{len(df)}** atividades · "
        f"Periodo: {df['start'].min().strftime('%d/%m/%y')} – {df['end'].max().strftime('%d/%m/%y')}"
    )

# Monta dados do Gantt
if gantt_mode == "Pavimento":
    gantt_df    = build_floor_gantt(df)
    y_col       = "floor_short"
    cat_col     = "status"
    color_map   = STATUS_COLORS
    hover_extra = {
        "n_ativs": True, "pct_medio": True, "disciplines": True,
        "floor_pos": False, "obra": True, "floor": False,
    }
    sort_order = gantt_df.sort_values("floor_pos", ascending=False)["floor_short"].tolist()
else:
    gantt_df = (
        df.groupby(["discipline", "status"])
        .agg(start_dt=("start_dt","min"), end_dt=("end_dt","max"),
             n_ativs=("act_id","count"), pct_medio=("pct","mean"))
        .reset_index()
        .assign(pct_medio=lambda d: d["pct_medio"].round(1))
    )
    gantt_df["floor_short"] = gantt_df["discipline"]
    y_col       = "floor_short"
    cat_col     = "status"
    color_map   = STATUS_COLORS
    hover_extra = {"n_ativs": True, "pct_medio": True}
    sort_order  = list(DISCIPLINES.keys())[::-1]

n_rows  = gantt_df[y_col].nunique()
gantt_h = max(420, min(n_rows * 28 + 120, 1100))

fig_gantt = px.timeline(
    gantt_df,
    x_start=       "start_dt",
    x_end=         "end_dt",
    y=             y_col,
    color=         cat_col,
    color_discrete_map=color_map,
    hover_data=    hover_extra,
    height=        gantt_h,
    category_orders={y_col: sort_order},
)
fig_gantt.update_layout(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(t=12, b=12, l=10, r=10),
    legend=dict(orientation="h", yanchor="bottom", y=1.01,
                xanchor="left", x=0, font=dict(size=11), title_text=""),
    xaxis=dict(title="", showgrid=True, gridcolor="rgba(0,0,0,0.06)",
               tickformat="%b/%y", tickfont=dict(size=11),
               rangeslider=dict(visible=True, thickness=0.04)),
    yaxis=dict(title="", tickfont=dict(size=10),
               autorange="reversed" if gantt_mode == "Pavimento" else True),
    hoverlabel=dict(bgcolor="#1A1A2E", font_color="#fff", font_size=12),
)
fig_gantt.add_vline(
    x=today.isoformat(),
    line_width=1.5,
    line_dash="dash",
    line_color="#C41230",
    annotation_text="Hoje",
    annotation_font_size=10,
    annotation_font_color="#C41230",
    annotation_position="top right",
)

st.plotly_chart(fig_gantt, use_container_width=True,
                config={"displaylogo": False,
                        "toImageButtonOptions": {
                            "format": "png", "filename": "cronograma_decoracao",
                            "height": gantt_h, "width": 1400, "scale": 2}})
st.divider()

# ─── Disciplinas + Avanco por pavimento ───────────────────────────────────────
_section("Analise de Disciplinas e Avanco por Pavimento")

col_pie, col_bar = st.columns([1, 2])

disc_sum  = build_discipline_summary(df)
floor_sum = (
    df.groupby(["floor_short", "floor_pos"])
    .agg(pct_medio=("pct","mean"), n=("act_id","count"))
    .reset_index().sort_values("floor_pos").head(20)
    .assign(pct_medio=lambda d: d["pct_medio"].round(1))
)

# Constroi figuras antes de renderizar (precisamos delas para o PDF)
fig_pie = None
if not disc_sum.empty:
    fig_pie = go.Figure(go.Pie(
        labels=disc_sum["discipline"], values=disc_sum["total"],
        marker=dict(colors=[DISC_COLORS.get(d,"#95A5A6") for d in disc_sum["discipline"]],
                    line=dict(color="#fff", width=2)),
        textinfo="label+percent", textposition="inside",
        insidetextorientation="horizontal",
        textfont=dict(size=11, color="#fff"),
        outsidetextfont=dict(size=10, color="#444"),
        hovertemplate="<b>%{label}</b><br>%{value} atividades (%{percent})<extra></extra>",
        sort=False, pull=[0.02]*len(disc_sum),
    ))
    fig_pie.update_layout(showlegend=False, margin=dict(t=6,b=6,l=6,r=6),
                          paper_bgcolor="rgba(0,0,0,0)", height=320)

fig_bar = None
if not floor_sum.empty:
    fig_bar = go.Figure()
    fig_bar.add_trace(go.Bar(
        y=floor_sum["floor_short"], x=floor_sum["pct_medio"],
        orientation="h",
        marker_color=["#27AE60" if p>=100 else "#2980B9" if p>0 else "#BDC3C7"
                      for p in floor_sum["pct_medio"]],
        text=floor_sum["pct_medio"].apply(lambda x: f"{x:.0f}%"),
        textposition="outside", textfont=dict(size=10),
        hovertemplate="<b>%{y}</b><br>Avanco: %{x:.1f}%<extra></extra>",
    ))
    fig_bar.update_layout(
        xaxis=dict(title="% Avanco", range=[0,115], showgrid=True,
                   gridcolor="rgba(0,0,0,0.06)", ticksuffix="%"),
        yaxis=dict(tickfont=dict(size=10), autorange="reversed"),
        margin=dict(t=8,b=8,l=10,r=40),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=320,
    )
    fig_bar.add_vline(x=100, line_dash="dot", line_color="#27AE60",
                      line_width=1, opacity=0.5)

with col_pie:
    if fig_pie is not None:
        st.plotly_chart(fig_pie, use_container_width=True, config={"displaylogo": False})
    else:
        st.info("Sem dados de disciplina.")

with col_bar:
    if fig_bar is not None:
        st.plotly_chart(fig_bar, use_container_width=True, config={"displaylogo": False})
    else:
        st.info("Sem dados de pavimento.")

st.divider()

# ─── Alertas ──────────────────────────────────────────────────────────────────
_section("Alertas — Atividades com Prazo Vencido e 0% de Avanco")

alertas = df[
    (df["start"] <= today) &
    (df["pct"] == 0)
].copy()
alertas["dias_atraso"] = alertas["start"].apply(lambda d: (today - d).days)
alertas = alertas.sort_values("dias_atraso", ascending=False)

if alertas.empty:
    st.success("Nenhuma atividade com prazo vencido sem inicio. Tudo dentro do esperado.")
else:
    # Banner de alerta
    n_a     = len(alertas)
    max_at  = int(alertas["dias_atraso"].max())
    avg_at  = int(alertas["dias_atraso"].mean())
    st.markdown(
        f"""<div style="background:rgba(196,18,48,0.06);border-left:4px solid #C41230;
            border-radius:8px;padding:12px 18px;margin-bottom:12px;">
            <div style="font-size:15px;font-weight:800;color:#C41230;">
                ⚠️ {n_a} atividade{"s" if n_a>1 else ""} deveria{"m" if n_a>1 else ""} ter iniciado
            </div>
            <div style="font-size:12px;color:#555;margin-top:4px;">
                Atraso maximo: <b>{max_at} dias</b> &nbsp;·&nbsp;
                Atraso medio: <b>{avg_at} dias</b> &nbsp;·&nbsp;
                Pavimentos afetados: <b>{alertas['floor'].nunique()}</b>
            </div>
        </div>""",
        unsafe_allow_html=True,
    )

    # Tabela de alertas
    tbl_a = alertas[[
        "obra", "wbs", "floor_short", "discipline", "job_name", "start", "dias_atraso",
    ]].copy()
    tbl_a.columns = ["Obra", "WBS", "Pavimento", "Disciplina", "Servico", "Inicio Previsto", "Dias em Atraso"]

    def _color_atraso(row):
        dias = row["Dias em Atraso"]
        bg = (
            "rgba(196,18,48,0.15)"  if dias > 30 else
            "rgba(230,126,34,0.12)" if dias > 14 else
            "rgba(243,156,18,0.10)"
        )
        return [f"background-color:{bg}"] * len(row)

    st.dataframe(
        tbl_a.style.apply(_color_atraso, axis=1),
        use_container_width=True,
        hide_index=True,
        height=min(len(alertas) * 35 + 38, 400),
    )

st.divider()

# ─── PDF Export ───────────────────────────────────────────────────────────────
_section("Exportar PDF")

pdf_c1, pdf_c2 = st.columns([1, 1])
with pdf_c1:
    if st.button("📄 Gerar PDF do Cronograma", type="primary", use_container_width=True):
        with st.spinner("Renderizando graficos em paralelo e montando PDF..."):
            try:
                pdf_bytes = _export_pdf_decoracao(
                    fig_gantt   = fig_gantt,
                    fig_pie     = fig_pie,
                    fig_bar     = fig_bar,
                    kpis        = kpis,
                    alertas_df  = alertas,
                    obra_sel    = obra_sel,
                    gantt_mode  = gantt_mode,
                    n_floors    = len(df["floor"].unique()),
                    n_ativs     = len(df),
                )
                st.session_state["dec_pdf"] = pdf_bytes
                st.success("PDF pronto — clique em **Baixar PDF** ao lado.")
            except Exception as _e:
                st.error(f"Erro ao gerar PDF: {_e}")

with pdf_c2:
    if "dec_pdf" in st.session_state:
        fname = f"decoracao_{obra_sel.replace(' ','_')}_{date.today()}.pdf"
        st.download_button(
            "⬇️ Baixar PDF",
            data=st.session_state["dec_pdf"],
            file_name=fname,
            mime="application/pdf",
            use_container_width=True,
        )

st.divider()

# ─── Tabela de detalhe ────────────────────────────────────────────────────────
with st.expander(f"Ver tabela de atividades ({len(df)} linhas)"):
    tbl = df[["obra","wbs","floor_short","discipline","job_name",
              "start","end","duration","pct","status"]].copy()
    tbl.columns = ["Obra","WBS","Pavimento","Disciplina","Servico",
                   "Inicio","Fim","Duracao (d)","% Avanco","Status"]

    def _color_row(row):
        bg = {
            "Finalizada":   "rgba(39,174,96,0.08)",
            "Em andamento": "rgba(41,128,185,0.08)",
            "Atrasada":     "rgba(196,18,48,0.08)",
        }.get(row["Status"], "")
        return [f"background-color:{bg}" if bg else ""] * len(row)

    st.dataframe(tbl.style.apply(_color_row, axis=1),
                 use_container_width=True, hide_index=True)
