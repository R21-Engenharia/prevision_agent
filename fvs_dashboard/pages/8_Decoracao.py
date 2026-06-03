"""
Pagina 8 — Decoracao
=====================
Cronograma executivo e indicadores das atividades de acabamento/decoracao.
Dados: cache Prevision (activities_raw + jobs_raw).
"""

from __future__ import annotations

import sys
from pathlib import Path
from datetime import date

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fvs_dashboard.core.decoracao_engine import (
    load_decoracao,
    compute_kpis,
    build_floor_gantt,
    build_discipline_summary,
    DISC_COLORS,
    STATUS_COLORS,
    DISCIPLINES,
)
from fvs_dashboard.core.data_manager import OBRAS

# ─── Helpers de UI ────────────────────────────────────────────────────────────

def _kpi(label: str, value: str, delta: str = "", color: str = "#C41230") -> str:
    delta_html = (
        f'<div style="font-size:11px;font-weight:600;color:{color};'
        f'margin-top:2px;">{delta}</div>'
        if delta else ""
    )
    return (
        f'<div style="background:#fff;border-radius:8px;padding:14px 18px;'
        f'border-top:3px solid {color};box-shadow:0 2px 8px rgba(0,0,0,0.06);">'
        f'<div style="font-size:10px;font-weight:700;color:#888;text-transform:uppercase;'
        f'letter-spacing:.5px;margin-bottom:4px;">{label}</div>'
        f'<div style="font-size:26px;font-weight:800;color:#1A1A1A;line-height:1">{value}</div>'
        f'{delta_html}'
        f'</div>'
    )


def _section(title: str) -> None:
    st.markdown(
        f'<div style="font-size:11px;font-weight:700;color:#C41230;'
        f'text-transform:uppercase;letter-spacing:1px;'
        f'margin:18px 0 8px 0;border-bottom:1px solid #E8E8E8;padding-bottom:4px;">'
        f'{title}</div>',
        unsafe_allow_html=True,
    )


# ─── Cache de dados ───────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def _cached_load(obra_key: str) -> pd.DataFrame:
    """obra_key: nome da obra ou 'Todas'."""
    obra = None if obra_key == "Todas as obras" else obra_key
    return load_decoracao(obra)


# ═══════════════════════════════════════════════════════════════════════════════
# PAGINA
# ═══════════════════════════════════════════════════════════════════════════════

# ─── Header ──────────────────────────────────────────────────────────────────
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
        Cronograma executivo · Pacotes Prevision · Dados: activities_raw + jobs_raw
    </div>
</div>
""", unsafe_allow_html=True)

# ─── Filtros ─────────────────────────────────────────────────────────────────
f1, f2, f3, f4 = st.columns([2, 2, 2, 2])

with f1:
    obra_sel = st.selectbox(
        "**Obra**",
        ["Todas as obras"] + list(OBRAS.keys()),
        key="dec_obra",
    )

# Carrega dados com cache
with st.spinner("Carregando atividades de decoracao..."):
    df_raw = _cached_load(obra_sel)

if df_raw.empty:
    st.warning("Nenhuma atividade de decoracao encontrada. Verifique se os caches Prevision estao atualizados.")
    st.stop()

# Filtros dependentes dos dados
disc_opts  = ["Todas"] + sorted(df_raw["discipline"].unique().tolist())
status_opts = ["Todos", "Finalizada", "Em andamento", "Nao iniciada", "Atrasada"]

with f2:
    disc_sel = st.selectbox("**Disciplina**", disc_opts, key="dec_disc")
with f3:
    status_sel = st.selectbox("**Status**", status_opts, key="dec_status")
with f4:
    today = date.today()
    date_range = st.date_input(
        "**Periodo**",
        value=(df_raw["start"].min(), df_raw["end"].max()),
        min_value=df_raw["start"].min(),
        max_value=df_raw["end"].max(),
        format="DD/MM/YYYY",
        key="dec_period",
    )

# Aplica filtros
df = df_raw.copy()
if disc_sel != "Todas":
    df = df[df["discipline"] == disc_sel]
if status_sel != "Todos":
    df = df[df["status"] == status_sel]
if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    df = df[(df["start"] >= date_range[0]) & (df["end"] <= date_range[1])]

if df.empty:
    st.info("Nenhuma atividade corresponde aos filtros selecionados.")
    st.stop()

# ─── KPIs ────────────────────────────────────────────────────────────────────
kpis = compute_kpis(df)

st.markdown("")
k1, k2, k3, k4, k5, k6 = st.columns(6)

with k1:
    st.markdown(_kpi("Total", str(kpis["total"]), color="#1A1A1A"), unsafe_allow_html=True)
with k2:
    pct_fin = f'{kpis["finalizada"] * 100 // kpis["total"]}%'
    st.markdown(_kpi("Finalizadas", str(kpis["finalizada"]),
                     delta=pct_fin, color="#27AE60"), unsafe_allow_html=True)
with k3:
    st.markdown(_kpi("Em Andamento", str(kpis["em_andamento"]),
                     color="#2980B9"), unsafe_allow_html=True)
with k4:
    st.markdown(_kpi("Nao Iniciadas", str(kpis["nao_iniciada"]),
                     color="#95A5A6"), unsafe_allow_html=True)
with k5:
    st.markdown(_kpi("Atrasadas", str(kpis["atrasada"]),
                     color="#C41230" if kpis["atrasada"] > 0 else "#95A5A6"),
                unsafe_allow_html=True)
with k6:
    st.markdown(_kpi("Avanco Medio", f'{kpis["pct_medio"]}%',
                     delta=f'{kpis["proximas_30d"]} iniciam em 30d',
                     color="#F6A623"), unsafe_allow_html=True)

st.markdown("<div style='margin-top:6px'></div>", unsafe_allow_html=True)
st.divider()

# ─── Cronograma Gantt ─────────────────────────────────────────────────────────
_section("Cronograma de Decoracao por Pavimento")

# Toggle de agrupamento
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

if gantt_mode == "Pavimento":
    gantt_df = build_floor_gantt(df)
    y_col    = "floor_short"
    cat_col  = "status"
    color_map = STATUS_COLORS
    hover_extra = {
        "n_ativs":    True,
        "pct_medio":  True,
        "disciplines": True,
        "floor_pos":  False,
        "obra":       True,
        "floor":      False,
    }
    sort_order = gantt_df.sort_values("floor_pos", ascending=False)["floor_short"].tolist()
else:
    # Agrupa por disciplina
    gantt_df = (
        df.groupby(["discipline", "status"])
        .agg(
            start_dt  = ("start_dt", "min"),
            end_dt    = ("end_dt",   "max"),
            n_ativs   = ("act_id",   "count"),
            pct_medio = ("pct",      "mean"),
        )
        .reset_index()
        .assign(pct_medio=lambda d: d["pct_medio"].round(1))
    )
    gantt_df["floor_short"] = gantt_df["discipline"]
    y_col     = "floor_short"
    cat_col   = "status"
    color_map = STATUS_COLORS
    hover_extra = {"n_ativs": True, "pct_medio": True}
    sort_order = list(DISCIPLINES.keys())[::-1]

# Calcula altura dinamica do Gantt
n_rows    = gantt_df[y_col].nunique()
gantt_h   = max(420, min(n_rows * 28 + 120, 1100))

fig_gantt = px.timeline(
    gantt_df,
    x_start        = "start_dt",
    x_end          = "end_dt",
    y              = y_col,
    color          = cat_col,
    color_discrete_map = color_map,
    hover_data     = hover_extra,
    height         = gantt_h,
    category_orders = {y_col: sort_order},
)

fig_gantt.update_layout(
    paper_bgcolor = "rgba(0,0,0,0)",
    plot_bgcolor  = "rgba(0,0,0,0)",
    margin        = dict(t=12, b=12, l=10, r=10),
    legend        = dict(
        orientation="h", yanchor="bottom", y=1.01,
        xanchor="left", x=0, font=dict(size=11),
        title_text="",
    ),
    xaxis = dict(
        title       = "",
        showgrid    = True,
        gridcolor   = "rgba(0,0,0,0.06)",
        tickformat  = "%b/%y",
        tickfont    = dict(size=11),
        rangeslider = dict(visible=True, thickness=0.04),
    ),
    yaxis = dict(
        title    = "",
        tickfont = dict(size=10),
        autorange= "reversed" if gantt_mode == "Pavimento" else True,
    ),
    hoverlabel = dict(bgcolor="#1A1A2E", font_color="#fff", font_size=12),
)

# Linha vertical de hoje
fig_gantt.add_vline(
    x          = pd.Timestamp(date.today()),
    line_width = 1.5,
    line_dash  = "dash",
    line_color = "#C41230",
    annotation = dict(
        text      = "Hoje",
        font_size = 10,
        font_color= "#C41230",
        yref      = "paper",
        y         = 1.01,
    ),
)

st.plotly_chart(fig_gantt, use_container_width=True,
                config={"displaylogo": False,
                        "toImageButtonOptions": {
                            "format": "png", "filename": "cronograma_decoracao",
                            "height": gantt_h, "width": 1400, "scale": 2,
                        }})

st.divider()

# ─── Segunda linha: distribuicao por disciplina + avanco por pavimento ────────
_section("Analise de Disciplinas e Avanco por Pavimento")

col_pie, col_bar = st.columns([1, 2])

with col_pie:
    disc_sum = build_discipline_summary(df)
    if not disc_sum.empty:
        fig_pie = go.Figure(go.Pie(
            labels = disc_sum["discipline"],
            values = disc_sum["total"],
            marker = dict(
                colors = [DISC_COLORS.get(d, "#95A5A6") for d in disc_sum["discipline"]],
                line   = dict(color="#fff", width=2),
            ),
            textinfo = "label+percent",
            textposition = "inside",
            insidetextorientation = "horizontal",
            textfont = dict(size=11, color="#fff"),
            outsidetextfont = dict(size=10, color="#444"),
            hovertemplate = "<b>%{label}</b><br>%{value} atividades (%{percent})<extra></extra>",
            sort = False,
            pull = [0.02] * len(disc_sum),
        ))
        fig_pie.update_layout(
            showlegend    = False,
            margin        = dict(t=6, b=6, l=6, r=6),
            paper_bgcolor = "rgba(0,0,0,0)",
            height        = 320,
        )
        st.plotly_chart(fig_pie, use_container_width=True,
                        config={"displaylogo": False})
    else:
        st.info("Sem dados de disciplina.")

with col_bar:
    # Avanco medio por pavimento (top 20 por floor_pos)
    floor_sum = (
        df.groupby(["floor_short", "floor_pos"])
        .agg(pct_medio=("pct", "mean"), n=("act_id", "count"))
        .reset_index()
        .sort_values("floor_pos")
        .head(20)
        .assign(pct_medio=lambda d: d["pct_medio"].round(1))
    )

    if not floor_sum.empty:
        fig_bar = go.Figure()
        fig_bar.add_trace(go.Bar(
            y          = floor_sum["floor_short"],
            x          = floor_sum["pct_medio"],
            orientation= "h",
            marker_color = [
                "#27AE60" if p >= 100 else
                "#2980B9" if p > 0   else
                "#BDC3C7"
                for p in floor_sum["pct_medio"]
            ],
            text       = floor_sum["pct_medio"].apply(lambda x: f"{x:.0f}%"),
            textposition= "outside",
            textfont   = dict(size=10),
            hovertemplate = "<b>%{y}</b><br>Avanco: %{x:.1f}%<extra></extra>",
        ))
        fig_bar.update_layout(
            xaxis = dict(
                title    = "% Avanco",
                range    = [0, 115],
                showgrid = True,
                gridcolor= "rgba(0,0,0,0.06)",
                ticksuffix="%",
            ),
            yaxis  = dict(tickfont=dict(size=10), autorange="reversed"),
            margin = dict(t=8, b=8, l=10, r=40),
            paper_bgcolor = "rgba(0,0,0,0)",
            plot_bgcolor  = "rgba(0,0,0,0)",
            height = 320,
        )
        # Linha de referencia 100%
        fig_bar.add_vline(x=100, line_dash="dot", line_color="#27AE60",
                          line_width=1, opacity=0.5)
        st.plotly_chart(fig_bar, use_container_width=True,
                        config={"displaylogo": False})
    else:
        st.info("Sem dados de pavimento.")

st.divider()

# ─── Tabela de detalhe ────────────────────────────────────────────────────────
with st.expander(f"Ver tabela de atividades ({len(df)} linhas)"):
    tbl = df[[
        "obra", "wbs", "floor_short", "discipline", "job_name",
        "start", "end", "duration", "pct", "status",
    ]].copy()
    tbl.columns = [
        "Obra", "WBS", "Pavimento", "Disciplina", "Servico",
        "Inicio", "Fim", "Duracao (d)", "% Avanco", "Status",
    ]

    # Colorir status
    def _color_row(row):
        c = STATUS_COLORS.get(row["Status"], "")
        bg = {
            "Finalizada":   "rgba(39,174,96,0.08)",
            "Em andamento": "rgba(41,128,185,0.08)",
            "Atrasada":     "rgba(196,18,48,0.08)",
        }.get(row["Status"], "")
        return [f"background-color:{bg}" if bg else ""] * len(row)

    st.dataframe(
        tbl.style.apply(_color_row, axis=1),
        use_container_width=True,
        hide_index=True,
    )
