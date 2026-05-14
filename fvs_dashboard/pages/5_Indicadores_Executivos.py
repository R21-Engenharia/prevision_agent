"""
Pagina 5 — Indicadores Executivos / Auditoria Temporal
========================================================
Visao executiva com historico de snapshots, KPIs por periodo,
graficos de evolucao, aging e alertas criticos.
"""

import sys
import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from fvs_dashboard.core.data_manager import DataManager
from fvs_dashboard.core.business import STATUS_FINALIZADA, STATUS_EM_ANDAMENTO, STATUS_NAO_INICIADA

dm: DataManager = st.session_state.dm
obra: str       = st.session_state.obra

# ── Paleta de cores corporativa ───────────────────────────────────────────────
COR_AZUL     = "#2F5597"
COR_VERDE    = "#375623"
COR_AMARELO  = "#7F6000"
COR_VERMELHO = "#C00000"
COR_CINZA    = "#6b7fa3"
BG_VERDE     = "#E2EFDA"
BG_AMARELO   = "#FFEB9C"
BG_VERMELHO  = "#FFC7CE"

STATUS_COR = {
    STATUS_FINALIZADA:   COR_VERDE,
    STATUS_EM_ANDAMENTO: COR_AMARELO,
    STATUS_NAO_INICIADA: COR_VERMELHO,
}
STATUS_LABEL = {
    STATUS_FINALIZADA:   "Finalizada",
    STATUS_EM_ANDAMENTO: "Em Andamento",
    STATUS_NAO_INICIADA: "Nao Iniciada",
}

# ── Cabecalho ─────────────────────────────────────────────────────────────────
st.markdown(f"""
<div style="background:linear-gradient(135deg,{COR_AZUL},{COR_AZUL}cc);
     padding:18px 24px;border-radius:10px;margin-bottom:1.2rem;">
  <h2 style="color:white;margin:0;font-size:20px;font-weight:700;">
    Indicadores Executivos — {obra}
  </h2>
  <p style="color:#b0c4e8;margin:4px 0 0;font-size:13px;">
    Auditoria temporal de qualidade | Evolucao historica de FVS
  </p>
</div>
""", unsafe_allow_html=True)

# ── Carrega historico ─────────────────────────────────────────────────────────
with st.spinner("Carregando historico de snapshots..."):
    history = dm.load_history(obra)

if history.empty:
    st.warning(
        "Nenhum snapshot historico disponivel. "
        "Clique em **Atualizar InMeta** na sidebar para gerar o primeiro snapshot.",
        icon="📅"
    )
    st.stop()

snap_info = dm.snapshot_info(obra)
n_dias    = snap_info["n_snapshots"]
oldest    = snap_info["oldest"]
latest    = snap_info["latest"]

# ── Filtros ───────────────────────────────────────────────────────────────────
st.markdown("### Filtros")
col_per, col_st, col_mod = st.columns([2, 1, 2])

with col_per:
    today      = datetime.date.today()
    periodo_opts = ["Ultimo mes", "Ultimo trimestre", "Ultimo semestre", "Todo historico", "Personalizado"]
    sel_periodo = st.selectbox("Periodo", periodo_opts, index=3 if n_dias < 30 else 0)

    if sel_periodo == "Ultimo mes":
        date_start = today - datetime.timedelta(days=30)
        date_end   = today
    elif sel_periodo == "Ultimo trimestre":
        date_start = today - datetime.timedelta(days=90)
        date_end   = today
    elif sel_periodo == "Ultimo semestre":
        date_start = today - datetime.timedelta(days=180)
        date_end   = today
    elif sel_periodo == "Todo historico":
        date_start = history["date_snapshot"].min()
        date_end   = today
    else:
        c1p, c2p = st.columns(2)
        date_start = c1p.date_input("De", value=today - datetime.timedelta(days=30))
        date_end   = c2p.date_input("Ate", value=today)

with col_st:
    status_opts = ["Todos", "Finalizada", "Em Andamento", "Nao Iniciada"]
    sel_status  = st.selectbox("Status", status_opts)

with col_mod:
    modelos_disp = ["Todos"] + sorted(history["modelo"].unique().tolist())
    sel_modelo   = st.selectbox("Modelo FVS", modelos_disp)

# Aplica filtros ao historico
hist_filt = history[
    (history["date_snapshot"] >= date_start) &
    (history["date_snapshot"] <= date_end)
].copy()

if sel_status != "Todos":
    status_map = {"Finalizada": STATUS_FINALIZADA, "Em Andamento": STATUS_EM_ANDAMENTO, "Nao Iniciada": STATUS_NAO_INICIADA}
    hist_filt = hist_filt[hist_filt["status"] == status_map[sel_status]]

if sel_modelo != "Todos":
    hist_filt = hist_filt[hist_filt["modelo"] == sel_modelo]

# Snapshot mais recente no periodo (para KPIs do estado atual)
latest_date = hist_filt["date_snapshot"].max() if not hist_filt.empty else None
hist_latest = hist_filt[hist_filt["date_snapshot"] == latest_date] if latest_date else pd.DataFrame()

st.caption(
    f"Periodo: {date_start} a {date_end}  |  "
    f"Snapshots disponíveis: {n_dias} dias  |  "
    f"Mais antigo: {oldest}  |  Mais recente: {latest}"
)
st.divider()

# ── KPIs Executivos ───────────────────────────────────────────────────────────
st.markdown("### Indicadores do Periodo")

# Calcula sobre o ultimo snapshot do periodo (estado atual do periodo)
if hist_latest.empty:
    for col in st.columns(5):
        col.metric("—", "—")
else:
    total_fvs  = len(hist_latest)
    finalizada  = (hist_latest["status"] == STATUS_FINALIZADA).sum()
    em_and      = (hist_latest["status"] == STATUS_EM_ANDAMENTO).sum()
    nao_inic    = (hist_latest["status"] == STATUS_NAO_INICIADA).sum()
    nc_total    = hist_latest["nc"].sum()

    # FVS novas no periodo (apareceram pela primeira vez)
    novas_no_periodo = hist_filt[
        (hist_filt["date_first_seen"] >= date_start) &
        (hist_filt["date_first_seen"] <= date_end)
    ]["date_first_seen"].nunique()

    # Criticas: NAO_INICIADA ha mais de 7 dias
    criticas    = ((hist_latest["status"] == STATUS_NAO_INICIADA) &
                   (hist_latest["dias_pendente"] > 7)).sum()

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("FVS Liberadas", total_fvs,
              help="Total de FVS no ultimo snapshot do periodo")
    c2.metric("Finalizadas", int(finalizada),
              delta=f"{100*finalizada/max(total_fvs,1):.0f}%",
              delta_color="normal")
    c3.metric("Em Andamento", int(em_and),
              delta=f"{100*em_and/max(total_fvs,1):.0f}%",
              delta_color="off")
    c4.metric("Nao Iniciadas", int(nao_inic),
              delta=f"{100*nao_inic/max(total_fvs,1):.0f}%",
              delta_color="inverse" if nao_inic > 0 else "off")
    c5.metric("Criticas >7d", int(criticas),
              delta="urgentes" if criticas > 0 else "ok",
              delta_color="inverse" if criticas > 0 else "off",
              help="FVS NAO_INICIADA ha mais de 7 dias")
    c6.metric("NC Abertas", int(nc_total),
              delta_color="inverse" if nc_total > 0 else "off")

st.divider()

# ── Graficos: Evolucao + Distribuicao ────────────────────────────────────────
col_evol, col_pizza = st.columns([3, 2])

with col_evol:
    st.markdown("### Evolucao Temporal")
    if n_dias < 2:
        st.info("O grafico de evolucao precisar de pelo menos 2 snapshots. Continue atualizando diariamente.")
    else:
        # Agrupa por data + status → contagem
        evol = (
            history.groupby(["date_snapshot", "status"])
            .size()
            .reset_index(name="count")
        )
        fig_evol = go.Figure()
        for status_key, label, cor in [
            (STATUS_FINALIZADA,   "Finalizada",   COR_VERDE),
            (STATUS_EM_ANDAMENTO, "Em Andamento", COR_AMARELO),
            (STATUS_NAO_INICIADA, "Nao Iniciada", COR_VERMELHO),
        ]:
            sub = evol[evol["status"] == status_key]
            if not sub.empty:
                fig_evol.add_trace(go.Scatter(
                    x=sub["date_snapshot"].astype(str),
                    y=sub["count"],
                    mode="lines+markers",
                    name=label,
                    line=dict(color=cor, width=2),
                    marker=dict(size=6),
                    hovertemplate=f"{label}: %{{y}}<extra></extra>",
                ))
        fig_evol.update_layout(
            height=300,
            margin=dict(l=10, r=10, t=10, b=30),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(showgrid=False, tickfont=dict(size=10)),
            yaxis=dict(showgrid=True, gridcolor="#e8edf5", tickfont=dict(size=10)),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            hovermode="x unified",
        )
        st.plotly_chart(fig_evol, use_container_width=True)

with col_pizza:
    st.markdown("### Distribuicao Atual")
    if not hist_latest.empty:
        counts = hist_latest["status"].value_counts()
        labels  = [STATUS_LABEL.get(s, s) for s in counts.index]
        values  = counts.values.tolist()
        colors_ = [STATUS_COR.get(s, COR_CINZA) for s in counts.index]
        pull_   = [0.05 if s == STATUS_NAO_INICIADA else 0 for s in counts.index]

        fig_pie = go.Figure(go.Pie(
            labels=labels, values=values,
            marker_colors=colors_, pull=pull_,
            hole=0.45,
            textinfo="percent+value",
            textfont=dict(size=11),
            hovertemplate="%{label}: %{value}<extra></extra>",
        ))
        fig_pie.update_layout(
            height=300,
            margin=dict(l=10, r=10, t=10, b=10),
            paper_bgcolor="rgba(0,0,0,0)",
            showlegend=True,
            legend=dict(orientation="v", font=dict(size=11)),
        )
        st.plotly_chart(fig_pie, use_container_width=True)

st.divider()

# ── Aging ─────────────────────────────────────────────────────────────────────
col_aging, col_sla = st.columns([2, 1])

with col_aging:
    st.markdown("### Aging — FVS Pendentes")
    if hist_latest.empty:
        st.info("Sem dados.")
    else:
        # Filtra apenas NAO_INICIADA e EM_ANDAMENTO para aging
        pend = hist_latest[hist_latest["status"].isin([STATUS_NAO_INICIADA, STATUS_EM_ANDAMENTO])].copy()
        if pend.empty:
            st.success("Nenhuma FVS pendente no periodo.", icon="✅")
        else:
            aging_order = ["0-3d", "4-7d", "8-14d", ">14d"]
            aging_grp = (
                pend.groupby(["faixa_aging", "status"])
                .size()
                .reset_index(name="count")
            )
            fig_aging = go.Figure()
            for status_key, label, cor in [
                (STATUS_NAO_INICIADA, "Nao Iniciada", COR_VERMELHO),
                (STATUS_EM_ANDAMENTO, "Em Andamento", COR_AMARELO),
            ]:
                sub = aging_grp[aging_grp["status"] == status_key]
                if not sub.empty:
                    # Garante ordem das faixas
                    sub = sub.set_index("faixa_aging").reindex(aging_order, fill_value=0).reset_index()
                    fig_aging.add_trace(go.Bar(
                        name=label,
                        x=sub["faixa_aging"],
                        y=sub["count"],
                        marker_color=cor,
                        hovertemplate=f"{label} %{{x}}: %{{y}}<extra></extra>",
                    ))
            fig_aging.update_layout(
                barmode="stack",
                height=260,
                margin=dict(l=10, r=10, t=10, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(showgrid=False),
                yaxis=dict(showgrid=True, gridcolor="#e8edf5"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
            )
            st.plotly_chart(fig_aging, use_container_width=True)

with col_sla:
    st.markdown("### SLA Operacional")
    if not hist_latest.empty:
        # Dias medio para iniciar (EM_ANDAMENTO)
        em_and_rows = hist_latest[hist_latest["status"] == STATUS_EM_ANDAMENTO]
        sla_iniciar = em_and_rows["dias_pendente"].mean() if not em_and_rows.empty else None

        # Dias medio das criticas (NAO_INICIADA)
        nao_rows = hist_latest[hist_latest["status"] == STATUS_NAO_INICIADA]
        sla_pend  = nao_rows["dias_pendente"].mean() if not nao_rows.empty else None

        if sla_iniciar is not None:
            st.metric("Media dias ate iniciar", f"{sla_iniciar:.1f}d",
                      help="Media de dias entre liberacao e inicio da FVS")
        else:
            st.metric("Media dias ate iniciar", "—")

        if sla_pend is not None:
            st.metric("Media dias pendentes", f"{sla_pend:.1f}d",
                      help="Media de dias das FVS ainda nao iniciadas")
            if sla_pend > 7:
                st.error(f"Media acima de 7 dias!", icon="⚠️")
        else:
            st.metric("Media dias pendentes", "—")

        st.metric(
            "% Nao iniciadas criticas",
            f"{100*criticas/max(total_fvs,1):.0f}%" if not hist_latest.empty else "—",
            help="FVS NAO_INICIADA ha mais de 7 dias",
        )

st.divider()

# ── Top Modelos com Pendencias ────────────────────────────────────────────────
st.markdown("### Top Modelos FVS — Pendencias")

if not hist_latest.empty:
    top = (
        hist_latest[hist_latest["status"].isin([STATUS_NAO_INICIADA, STATUS_EM_ANDAMENTO])]
        .groupby("modelo")
        .agg(
            Nao_Iniciada = ("status", lambda s: (s == STATUS_NAO_INICIADA).sum()),
            Em_Andamento  = ("status", lambda s: (s == STATUS_EM_ANDAMENTO).sum()),
        )
        .assign(Total=lambda df: df["Nao_Iniciada"] + df["Em_Andamento"])
        .sort_values("Total", ascending=True)
        .tail(12)
        .reset_index()
    )
    if top.empty:
        st.success("Nenhuma pendencia no periodo.", icon="✅")
    else:
        fig_top = go.Figure()
        fig_top.add_trace(go.Bar(
            name="Nao Iniciada",
            y=top["modelo"].str[:50],
            x=top["Nao_Iniciada"],
            orientation="h",
            marker_color=COR_VERMELHO,
            hovertemplate="%{y}<br>Nao Iniciada: %{x}<extra></extra>",
        ))
        fig_top.add_trace(go.Bar(
            name="Em Andamento",
            y=top["modelo"].str[:50],
            x=top["Em_Andamento"],
            orientation="h",
            marker_color=COR_AMARELO,
            hovertemplate="%{y}<br>Em Andamento: %{x}<extra></extra>",
        ))
        fig_top.update_layout(
            barmode="stack",
            height=max(280, len(top) * 30),
            margin=dict(l=10, r=10, t=10, b=10),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(showgrid=True, gridcolor="#e8edf5"),
            yaxis=dict(showgrid=False),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig_top, use_container_width=True)

st.divider()

# ── Alertas Criticos ──────────────────────────────────────────────────────────
st.markdown("### Alertas Criticos")

if hist_latest.empty:
    st.info("Sem dados para alertas.")
else:
    alertas_criticos = hist_latest[
        (hist_latest["status"] == STATUS_NAO_INICIADA) &
        (hist_latest["dias_pendente"] > 7)
    ].sort_values("dias_pendente", ascending=False)

    alertas_nc = hist_latest[hist_latest["nc"] > 0].sort_values("nc", ascending=False)

    if alertas_criticos.empty and alertas_nc.empty:
        st.success("Nenhum alerta critico no momento.", icon="✅")
    else:
        if not alertas_criticos.empty:
            st.error(
                f"**{len(alertas_criticos)} FVS nao iniciadas ha mais de 7 dias** — requer acao imediata.",
                icon="🚨"
            )
            df_crit = alertas_criticos[["floor", "wbs", "modelo", "local", "dias_pendente"]].copy()
            df_crit.columns = ["Pavimento", "WBS", "Modelo FVS", "Local", "Dias Pendente"]
            df_crit["Pavimento"] = df_crit["Pavimento"].str.split("|").str[0].str.strip().str[:22]
            st.dataframe(
                df_crit.head(20),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Dias Pendente": st.column_config.NumberColumn("Dias", format="%d d"),
                }
            )

        if not alertas_nc.empty:
            st.warning(
                f"**{len(alertas_nc)} FVS com nao-conformidades abertas** ({alertas_nc['nc'].sum()} NC total).",
                icon="⚠️"
            )
            with st.expander("Ver FVS com NC"):
                df_nc = alertas_nc[["floor", "wbs", "modelo", "local", "status", "nc", "data_ins"]].copy()
                df_nc.columns = ["Pavimento", "WBS", "Modelo FVS", "Local", "Status", "NC", "Data Insp."]
                df_nc["Status"] = df_nc["Status"].map(STATUS_LABEL).fillna(df_nc["Status"])
                st.dataframe(df_nc, use_container_width=True, hide_index=True)
