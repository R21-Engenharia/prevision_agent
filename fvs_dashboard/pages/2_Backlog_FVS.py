"""
Pagina 2 — Backlog FVS
========================
Tabela completa filtravel com todos os pacotes liberados x status FVS.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
import pandas as pd

from fvs_dashboard.core.data_manager import DataManager
from fvs_dashboard.core.business import (
    STATUS_FINALIZADA, STATUS_EM_ANDAMENTO, STATUS_NAO_INICIADA, short_floor
)

dm: DataManager = st.session_state.dm
obra: str       = st.session_state.obra

st.title(f"Backlog FVS — {obra}")
st.caption("Todos os pacotes liberados e o status de cada FVS associada.")

# ── Dados ─────────────────────────────────────────────────────────────────────
with st.spinner("Carregando..."):
    try:
        df = dm.get_df(obra)
    except FileNotFoundError as e:
        st.error(f"Cache nao encontrado: {e}")
        st.stop()

if df.empty:
    st.warning("Nenhum pacote liberado encontrado.")
    st.stop()

# ── Filtros ───────────────────────────────────────────────────────────────────
st.markdown("### Filtros")
f1, f2, f3 = st.columns(3)

status_opts = ["Todos", "Nao Iniciada", "Em Andamento", "Finalizada"]
with f1:
    sel_status = st.selectbox("Status FVS", status_opts, index=0)

modelos_disponiveis = sorted(df["Modelo FVS"].unique().tolist())
with f2:
    sel_modelo = st.selectbox("Modelo FVS", ["Todos"] + modelos_disponiveis)

pavimentos_disp = sorted(df["Pavimento"].unique().tolist())
with f3:
    sel_pav = st.selectbox("Pavimento", ["Todos"] + pavimentos_disp)

# Aplica filtros
df_filt = df.copy()
if sel_status != "Todos":
    status_map_rev = {
        "Finalizada":   STATUS_FINALIZADA,
        "Em Andamento": STATUS_EM_ANDAMENTO,
        "Nao Iniciada": STATUS_NAO_INICIADA,
    }
    df_filt = df_filt[df_filt["status"] == status_map_rev[sel_status]]

if sel_modelo != "Todos":
    df_filt = df_filt[df_filt["Modelo FVS"] == sel_modelo]

if sel_pav != "Todos":
    df_filt = df_filt[df_filt["Pavimento"] == sel_pav]

# Ordenacao
df_filt = df_filt.sort_values(["_status_ord", "Pavimento", "Modelo FVS"])

st.caption(f"Exibindo **{len(df_filt)}** de **{len(df)}** FVS")
st.divider()

# ── Tabela ────────────────────────────────────────────────────────────────────
# Colunas para exibicao
display_cols = ["Pavimento", "WBS", "CF%", "Modelo FVS", "Local", "Status", "% Exec", "NC", "Data Insp."]

# Coloriza a coluna Status com st.dataframe column_config
def _status_color_map(status_label: str) -> str:
    """Retorna emoji indicador de status."""
    if status_label == "Finalizada":
        return "✅ Finalizada"
    if status_label == "Em Andamento":
        return "🟡 Em Andamento"
    if status_label == "Nao Iniciada":
        return "🔴 Nao Iniciada"
    return status_label

df_display = df_filt[display_cols].copy()
df_display["Status"] = df_display["Status"].apply(_status_color_map)

st.dataframe(
    df_display,
    use_container_width=True,
    hide_index=True,
    height=min(600, max(200, len(df_display) * 35 + 50)),
    column_config={
        "Pavimento":  st.column_config.TextColumn("Pavimento", width="small"),
        "WBS":        st.column_config.TextColumn("WBS", width="small"),
        "CF%":        st.column_config.TextColumn("CF%", width="small"),
        "Modelo FVS": st.column_config.TextColumn("Modelo FVS", width="large"),
        "Local":      st.column_config.TextColumn("Local", width="medium"),
        "Status":     st.column_config.TextColumn("Status", width="medium"),
        "% Exec":     st.column_config.TextColumn("% Exec", width="small"),
        "NC":         st.column_config.TextColumn("NC", width="small"),
        "Data Insp.": st.column_config.TextColumn("Data Insp.", width="small"),
    },
)

# ── Links InMeta ──────────────────────────────────────────────────────────────
df_links = df_filt[df_filt["Link InMeta"].str.len() > 0][["Modelo FVS", "Local", "Status", "Link InMeta"]].head(20)
if not df_links.empty:
    with st.expander(f"Links InMeta ({len(df_links)} inspecoes com link)"):
        for _, row in df_links.iterrows():
            status_em = "✅" if "Finaliz" in row["Status"] else ("🟡" if "Andamento" in row["Status"] else "🔴")
            st.markdown(
                f"{status_em} **{row['Modelo FVS'][:50]}** — {row['Local'][:30]}  "
                f"[Abrir no InMeta]({row['Link InMeta']})"
            )
