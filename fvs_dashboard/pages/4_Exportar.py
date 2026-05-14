"""
Pagina 4 — Exportar
====================
Botoes de download: Excel completo + PDF resumo operacional.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
import datetime

from fvs_dashboard.core.data_manager import DataManager
from fvs_dashboard.core.exporter import export_excel, export_pdf

dm: DataManager = st.session_state.dm
obra: str       = st.session_state.obra

st.title(f"Exportar — {obra}")
st.caption("Gere relatorios em Excel ou PDF com os dados atuais.")

# ── Dados ─────────────────────────────────────────────────────────────────────
with st.spinner("Preparando dados..."):
    try:
        rows = dm.get_rows(obra)
        kpis = dm.get_kpis(obra)
    except FileNotFoundError as e:
        st.error(f"Cache nao encontrado: {e}")
        st.stop()

today_str = datetime.date.today().strftime("%Y%m%d")
obra_slug  = obra.replace(" ", "_").replace("/", "-")

st.divider()

# ── Opcoes ────────────────────────────────────────────────────────────────────
st.markdown("### Opcoes")
include_fin = st.checkbox("Incluir FVS Finalizadas", value=True,
                           help="Se desmarcado, exporta apenas FVS Em Andamento e Nao Iniciadas.")

st.divider()

# ── Preview ───────────────────────────────────────────────────────────────────
rows_export = rows if include_fin else [r for r in rows if r["status"] != "FINALIZADA"]

c1, c2, c3 = st.columns(3)
c1.metric("FVS no relatorio", len(rows_export))
c2.metric("Pacotes liberados", kpis["total_lib"])
c3.metric("Nao Iniciadas",    kpis["nao_iniciada"])

st.markdown("**Preview das primeiras linhas:**")
import pandas as pd
df_prev = pd.DataFrame(rows_export[:10])
if not df_prev.empty:
    df_prev_show = df_prev[["floor", "wbs", "modelo", "local", "status", "pct_exec", "nc"]].copy()
    df_prev_show.columns = ["Pavimento", "WBS", "Modelo FVS", "Local", "Status", "% Exec", "NC"]
    df_prev_show["Status"] = df_prev_show["Status"].map({
        "FINALIZADA": "✅ Finalizada",
        "EM_ANDAMENTO": "🟡 Em Andamento",
        "NAO_INICIADA": "🔴 Nao Iniciada",
    }).fillna(df_prev_show["Status"])
    st.dataframe(df_prev_show, use_container_width=True, hide_index=True)

st.divider()

# ── Botoes de download ────────────────────────────────────────────────────────
st.markdown("### Downloads")

col_xl, col_pdf = st.columns(2)

with col_xl:
    st.markdown("#### Excel Completo")
    st.caption("4 abas: Resumo, Backlog, Pendentes, Por Modelo FVS")
    with st.spinner("Gerando Excel..."):
        try:
            xlsx_bytes = export_excel(
                rows=rows_export,
                kpis=kpis,
                obra=obra,
                include_finalizadas=include_fin,
            )
            st.download_button(
                label="⬇️ Baixar Excel",
                data=xlsx_bytes,
                file_name=f"FVS_{obra_slug}_{today_str}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                type="primary",
            )
        except Exception as e:
            st.error(f"Erro ao gerar Excel: {e}")

with col_pdf:
    st.markdown("#### PDF Resumo Operacional")
    st.caption("2 paginas: KPIs + tabela de FVS nao iniciadas")
    with st.spinner("Gerando PDF..."):
        try:
            pdf_bytes = export_pdf(
                rows=rows_export,
                kpis=kpis,
                obra=obra,
            )
            st.download_button(
                label="⬇️ Baixar PDF",
                data=pdf_bytes,
                file_name=f"FVS_Resumo_{obra_slug}_{today_str}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        except Exception as e:
            st.error(f"Erro ao gerar PDF: {e}")

st.divider()
ages = dm.cache_age(obra)
st.caption(f"Dados: Prevision {ages['prevision']} | InMeta {ages['inmeta']}")
