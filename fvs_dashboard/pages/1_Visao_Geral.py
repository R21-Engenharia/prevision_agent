"""
Pagina 1 — Visao Geral
========================
KPIs + grafico de distribuicao + top modelos pendentes.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd

from fvs_dashboard.core.data_manager import DataManager
from fvs_dashboard.core.business import STATUS_FINALIZADA, STATUS_EM_ANDAMENTO, STATUS_NAO_INICIADA
from fvs_dashboard.ui import theme as ui

dm: DataManager = st.session_state.dm
obra: str       = st.session_state.obra

ui.page_header(
    "Visão Geral",
    eyebrow=obra,
    subtitle="Indicadores operacionais de FVS para pacotes liberados.",
    chip="Pacotes liberados",
)

# ── Carrega dados ─────────────────────────────────────────────────────────────
with st.spinner("Carregando dados..."):
    try:
        kpis     = dm.get_kpis(obra)
        top_mods = dm.get_top_modelos(obra, n=10)
        df       = dm.get_df(obra)
    except FileNotFoundError as e:
        st.error(f"Cache nao encontrado: {e}\n\nExecute a coleta de dados primeiro.")
        st.stop()

# ── KPI Cards ─────────────────────────────────────────────────────────────────
ui.section("Indicadores")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Pacotes Liberados", kpis["total_lib"])
c2.metric("Total FVS",         kpis["total_fvs"])

with c3:
    st.metric(
        "Finalizadas",
        kpis["finalizada"],
        delta=f"{kpis['pct_finalizada']}%",
        delta_color="normal",
    )
with c4:
    st.metric(
        "Em Andamento",
        kpis["em_andamento"],
        delta=f"{kpis['pct_em_andamento']}%",
        delta_color="off",
    )
with c5:
    nao_i = kpis["nao_iniciada"]
    st.metric(
        "Nao Iniciadas",
        nao_i,
        delta=f"{kpis['pct_nao_iniciada']}%",
        delta_color="inverse" if nao_i > 0 else "off",
    )

st.divider()

# ── Grafico de distribuicao ───────────────────────────────────────────────────
col_graf, col_nc = st.columns([2, 1])

with col_graf:
    ui.section("Distribuição por Status")
    labels  = ["Finalizada", "Em Andamento", "Não Iniciada"]
    values  = [kpis["finalizada"], kpis["em_andamento"], kpis["nao_iniciada"]]
    colors_ = [ui.STATUS["fin"], ui.STATUS["and"], ui.STATUS["nao"]]
    pull_   = [0, 0, 0.06 if kpis["nao_iniciada"] > 0 else 0]

    fig = go.Figure(go.Pie(
        labels=labels,
        values=values,
        marker=dict(colors=colors_, line=dict(color="#ffffff", width=2)),
        pull=pull_,
        hole=0.5,
        textinfo="label+percent",
        textfont_size=12,
        hovertemplate="%{label}: %{value} FVS (%{percent})<extra></extra>",
    ))
    fig.update_layout(**ui.plotly_layout(height=280, legend=False,
                                         margin=dict(l=20, r=20, t=20, b=20)))
    st.plotly_chart(fig, use_container_width=True, config=ui.PLOTLY_CONFIG)

with col_nc:
    ui.section("Não-Conformidades")
    nc_total = kpis["nc_total"]
    fvs_nc   = sum(1 for r in dm.get_rows(obra) if r["nc"] > 0)

    st.metric("NC abertas (total)", nc_total)
    st.metric("FVS com NC",         fvs_nc)

    if nc_total > 0:
        st.markdown("")
        st.warning(f"{fvs_nc} FVS possuem nao-conformidades pendentes.", icon="⚠️")
    else:
        st.success("Nenhuma NC aberta.", icon="✅")

st.divider()

# ── Top Modelos ───────────────────────────────────────────────────────────────
ui.section("Top Modelos FVS com Pendências")

if not top_mods.empty:
    # Grafico de barras empilhadas horizontais
    fig2 = go.Figure()
    fig2.add_trace(go.Bar(
        name="Finalizada",
        y=top_mods["Modelo FVS"].str[:45],
        x=top_mods["Finalizada"],
        orientation="h",
        marker_color=ui.STATUS["fin"],
        hovertemplate="%{y}<br>Finalizada: %{x}<extra></extra>",
    ))
    fig2.add_trace(go.Bar(
        name="Em Andamento",
        y=top_mods["Modelo FVS"].str[:45],
        x=top_mods["Em_Andamento"],
        orientation="h",
        marker_color=ui.STATUS["and"],
        hovertemplate="%{y}<br>Em Andamento: %{x}<extra></extra>",
    ))
    fig2.add_trace(go.Bar(
        name="Não Iniciada",
        y=top_mods["Modelo FVS"].str[:45],
        x=top_mods["Nao_Iniciada"],
        orientation="h",
        marker_color=ui.STATUS["nao"],
        hovertemplate="%{y}<br>Não Iniciada: %{x}<extra></extra>",
    ))
    fig2.update_layout(**ui.plotly_layout(
        height=max(300, len(top_mods) * 32),
        barmode="stack",
        xaxis_title="Quantidade de FVS",
    ))
    st.plotly_chart(fig2, use_container_width=True, config=ui.PLOTLY_CONFIG)

    # Tabela resumo
    with st.expander("Ver tabela detalhada"):
        display_cols = ["Modelo FVS", "Total", "Finalizada", "Em_Andamento", "Nao_Iniciada", "NC"]
        rename_map   = {"Em_Andamento": "Em Andamento", "Nao_Iniciada": "Nao Iniciada"}
        st.dataframe(
            top_mods[display_cols].rename(columns=rename_map),
            use_container_width=True,
            hide_index=True,
        )
else:
    st.info("Nenhum dado disponivel. Verifique se os caches estao presentes.")
