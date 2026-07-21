"""
Pagina 3 — Pendentes (NAO_INICIADA)
=====================================
FVS ainda nao abertas no InMeta — acao imediata necessaria.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
import pandas as pd

from fvs_dashboard.core.data_manager import DataManager
from fvs_dashboard.core.business import STATUS_NAO_INICIADA
from fvs_dashboard.ui import theme as ui

dm: DataManager = st.session_state.dm
obra: str       = st.session_state.obra

ui.page_header(
    "Pendentes",
    eyebrow=obra,
    subtitle="FVS ainda não abertas no InMeta — ação imediata necessária.",
)

# ── Dados ─────────────────────────────────────────────────────────────────────
with st.spinner("Carregando..."):
    try:
        df = dm.get_df(obra)
    except FileNotFoundError as e:
        st.error(f"Cache nao encontrado: {e}")
        st.stop()

df_pend = df[df["status"] == STATUS_NAO_INICIADA].copy()
df_pend = df_pend.sort_values(["Modelo FVS", "Pavimento"])

total_pend = len(df_pend)

# ── Banner de urgencia ────────────────────────────────────────────────────────
if total_pend == 0:
    st.success("Todas as FVS ja foram abertas no InMeta.", icon="✅")
    st.stop()

st.error(
    f"**{total_pend} FVS** nao foram abertas no InMeta para pacotes com execucao 100%.",
    icon="🚨"
)
st.caption(
    "Estas FVS precisam ser abertas manualmente no InMeta para iniciar a verificacao de servico."
)
st.divider()

# ── Filtro por modelo ─────────────────────────────────────────────────────────
modelos = sorted(df_pend["Modelo FVS"].unique().tolist())
sel_mod = st.selectbox("Filtrar por Modelo FVS", ["Todos"] + modelos)
if sel_mod != "Todos":
    df_pend = df_pend[df_pend["Modelo FVS"] == sel_mod]

st.caption(f"Exibindo **{len(df_pend)}** de **{total_pend}** FVS pendentes")

# ── Agrupado por modelo ───────────────────────────────────────────────────────
grupos = df_pend.groupby("Modelo FVS", sort=True)

for modelo_nome, grupo in grupos:
    count = len(grupo)
    with st.expander(f"**{modelo_nome}**  —  {count} FVS pendentes", expanded=(count <= 5)):
        # Tabela do grupo
        cols_show = ["Pavimento", "WBS", "CF%", "Local"]
        st.dataframe(
            grupo[cols_show].reset_index(drop=True),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Pavimento": st.column_config.TextColumn("Pavimento", width="small"),
                "WBS":       st.column_config.TextColumn("WBS", width="small"),
                "CF%":       st.column_config.TextColumn("CF%", width="small"),
                "Local":     st.column_config.TextColumn("Local", width="medium"),
            },
        )

st.divider()

# ── Tabela completa ───────────────────────────────────────────────────────────
with st.expander("Ver tabela completa de pendentes"):
    cols_full = ["Pavimento", "WBS", "CF%", "Modelo FVS", "Local"]
    st.dataframe(
        df_pend[cols_full].reset_index(drop=True),
        use_container_width=True,
        hide_index=True,
        height=min(500, len(df_pend) * 35 + 50),
    )
