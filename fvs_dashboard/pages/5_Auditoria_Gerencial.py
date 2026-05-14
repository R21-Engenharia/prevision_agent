"""
Pagina 5 — Auditoria Gerencial
================================
Modulo de auditoria operacional e gerencial com visao temporal completa.
Substitui a pagina Indicadores Executivos (Fase 7).

Fontes de dados:
  - inmeta_inspections_raw.json: 1.760 inspecoes (nov/2024 - mai/2026)
    dataInspecao = unica data disponivel (proxy de inicio/finalizacao)
  - data/snapshots/*.parquet: snapshots diarios a partir de 2026-05-14
  - NC: apenas contagens (qtdNaoConformidade / qtdNaoConformidadeTratada)
    Endpoints /nao-conformidades inexistentes na API (retornam 404).
"""

import sys
import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from fvs_dashboard.core.data_manager import DataManager, OBRAS
from fvs_dashboard.core.audit_engine import (
    build_monthly_from_inspections,
    build_monthly_from_snapshots,
    build_obra_comparison,
    compute_audit_kpis,
    compute_sla,
    period_dates,
    STATUS_NAO_INICIADA, STATUS_EM_ANDAMENTO, STATUS_FINALIZADA,
)

# ── Sessao ────────────────────────────────────────────────────────────────────
dm: DataManager = st.session_state.dm

# ── Paleta corporativa ────────────────────────────────────────────────────────
C_AZUL     = "#2F5597"
C_AZUL_ESC = "#1a2744"
C_VERDE    = "#1e7e34"
C_AMARELO  = "#d39e00"
C_VERMELHO = "#b21f2d"
C_CINZA    = "#6c757d"
C_VERDE_BG = "#d4edda"
C_AMAR_BG  = "#fff3cd"
C_VERM_BG  = "#f8d7da"

OBRA_OPTS = ["Todas as Obras"] + list(OBRAS.keys())

# ── CSS executivo ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* KPI Cards executivos */
.kpi-card {
    background: #ffffff;
    border-radius: 12px;
    padding: 18px 20px 14px 20px;
    border-left: 5px solid #2F5597;
    box-shadow: 0 2px 8px rgba(47,85,151,0.10);
    margin-bottom: 8px;
    min-height: 110px;
}
.kpi-card.green  { border-left-color: #1e7e34; }
.kpi-card.yellow { border-left-color: #d39e00; }
.kpi-card.red    { border-left-color: #b21f2d; }
.kpi-card.gray   { border-left-color: #6c757d; }
.kpi-icon  { font-size: 20px; margin-bottom: 4px; }
.kpi-value { font-size: 36px; font-weight: 800; color: #1a2744; line-height: 1.1; }
.kpi-label { font-size: 11px; font-weight: 600; color: #6b7fa3;
             text-transform: uppercase; letter-spacing: 0.5px; margin-top: 2px; }
.kpi-sub   { font-size: 12px; color: #6c757d; margin-top: 4px; }
.kpi-delta { font-size: 12px; margin-top: 6px; font-weight: 600; }
.delta-pos { color: #1e7e34; }
.delta-neg { color: #b21f2d; }
.delta-neu { color: #6c757d; }

/* Header */
.audit-header {
    background: linear-gradient(135deg, #1a2744 0%, #2F5597 100%);
    border-radius: 12px;
    padding: 22px 28px;
    margin-bottom: 1.5rem;
    color: white;
}
.audit-header h1 {
    color: white !important;
    font-size: 22px !important;
    font-weight: 800 !important;
    margin: 0 0 4px 0 !important;
    letter-spacing: 0.3px;
}
.audit-header p { color: #a0b8e0; font-size: 13px; margin: 0; }

/* Secoes */
.section-title {
    font-size: 13px;
    font-weight: 700;
    color: #2F5597;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    border-bottom: 2px solid #e8edf5;
    padding-bottom: 6px;
    margin: 1.4rem 0 0.8rem 0;
}

/* Alert boxes */
.alert-critico {
    background: #fff5f5;
    border: 1px solid #f5c6cb;
    border-left: 4px solid #b21f2d;
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 8px;
    font-size: 13px;
}
.alert-aviso {
    background: #fffbf0;
    border: 1px solid #ffeeba;
    border-left: 4px solid #d39e00;
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 8px;
    font-size: 13px;
}
.badge-fonte {
    background: #e8edf5;
    color: #2F5597;
    font-size: 10px;
    padding: 2px 8px;
    border-radius: 10px;
    font-weight: 600;
    letter-spacing: 0.3px;
}
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="audit-header">
  <h1>AUDITORIA GERENCIAL — R21 EMPREENDIMENTOS</h1>
  <p>Indicadores historicos de FVS e Nao-Conformidades &nbsp;|&nbsp;
     Dados: InMeta (nov/2024 a mai/2026) + Snapshots diarios (a partir de 14/05/2026)</p>
</div>
""", unsafe_allow_html=True)

# ── Filtros ───────────────────────────────────────────────────────────────────
col_obra, col_period, col_datas = st.columns([2, 3, 3])

with col_obra:
    obra_sel = st.selectbox("Obra", OBRA_OPTS, label_visibility="collapsed",
                            key="audit_obra",
                            format_func=lambda x: f"🏗 {x}" if x != "Todas as Obras" else "🏗 Todas as Obras")

with col_period:
    periodo = st.radio(
        "Período",
        ["Mes", "Trimestre", "Semestre", "Anual", "Tudo", "Personalizado"],
        horizontal=True,
        label_visibility="collapsed",
        key="audit_period",
    )

with col_datas:
    if periodo == "Personalizado":
        today = datetime.date.today()
        d_ini = st.date_input("De", value=today - datetime.timedelta(days=90),
                              key="audit_d_ini", label_visibility="visible")
        d_fim = st.date_input("Até", value=today, key="audit_d_fim",
                              label_visibility="visible")
    else:
        d_ini, d_fim = None, None

date_start, date_end = period_dates(periodo, d_ini, d_fim)
obra_filter = None if obra_sel == "Todas as Obras" else obra_sel

# ── Carregamento de dados (cacheado por sessao) ───────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def _get_monthly_insp():
    return build_monthly_from_inspections()

@st.cache_data(ttl=300, show_spinner=False)
def _get_history_ct():
    return DataManager().load_history("Cape Town Residence")

@st.cache_data(ttl=300, show_spinner=False)
def _get_history_hm():
    return DataManager().load_history("Holmes Residence")

with st.spinner("Carregando dados..."):
    mi_all    = _get_monthly_insp()
    hist_ct   = _get_history_ct()
    hist_hm   = _get_history_hm()

# Monta historia combinada
if obra_filter:
    hist_snap = hist_ct if obra_filter == "Cape Town Residence" else hist_hm
else:
    hist_snap = pd.concat([hist_ct, hist_hm], ignore_index=True) if not hist_ct.empty else hist_hm

mi_filtrado = mi_all.copy()
if obra_filter:
    mi_filtrado = mi_filtrado[mi_filtrado["obra"] == obra_filter]
mi_periodo = mi_filtrado[
    (mi_filtrado["date_month"] >= date_start) &
    (mi_filtrado["date_month"] <= date_end)
]

# Latest snapshot para KPIs de estado atual
if hist_snap.empty:
    latest_snap = pd.DataFrame()
else:
    lat_date = hist_snap["date_snapshot"].max()
    latest_snap = hist_snap[hist_snap["date_snapshot"] == lat_date]
    if obra_filter:
        latest_snap = latest_snap[latest_snap["obra"] == obra_filter]

# KPIs
kpis = compute_audit_kpis(mi_all, latest_snap, date_start, date_end, obra_filter)

# ── Label de periodo ─────────────────────────────────────────────────────────
periodo_label = {
    "Mes": "Ultimo mes", "Trimestre": "Ultimo trimestre",
    "Semestre": "Ultimo semestre", "Anual": "Este ano",
    "Tudo": "Todo o historico", "Personalizado": f"{date_start} a {date_end}",
}.get(periodo, periodo)

st.caption(f"Periodo: **{periodo_label}** &nbsp;|&nbsp; Obra: **{obra_sel}** &nbsp;|&nbsp; "
           f"Intervalo: {date_start.strftime('%d/%m/%Y')} – {date_end.strftime('%d/%m/%Y')}")

# ── KPI Cards ─────────────────────────────────────────────────────────────────
st.markdown('<div class="section-title">Indicadores do Periodo</div>', unsafe_allow_html=True)

def _kpi_card(icon, value, label, sub="", color="blue", delta_html=""):
    color_cls = {"blue": "", "green": "green", "yellow": "yellow",
                 "red": "red", "gray": "gray"}.get(color, "")
    return f"""
    <div class="kpi-card {color_cls}">
      <div class="kpi-icon">{icon}</div>
      <div class="kpi-value">{value}</div>
      <div class="kpi-label">{label}</div>
      {"<div class='kpi-sub'>" + sub + "</div>" if sub else ""}
      {"<div class='kpi-delta'>" + delta_html + "</div>" if delta_html else ""}
    </div>"""

total_insp   = kpis.get("total_insp", 0)
finalizada   = kpis.get("finalizada", 0)
em_and       = kpis.get("em_andamento", 0)
nc_total     = kpis.get("nc_total", 0)
nc_pend      = kpis.get("nc_pendentes", 0)
pct_fin      = kpis.get("pct_finalizada", 0.0)

snap_ni      = kpis.get("snap_nao_iniciada", 0)
snap_crit    = kpis.get("snap_criticas", 0)
snap_nc_pend = kpis.get("snap_nc_pendentes", 0)

c1, c2, c3, c4, c5, c6 = st.columns(6)
with c1:
    st.markdown(_kpi_card("📋", total_insp, "FVS Inspecionadas",
                          f"no periodo selecionado"), unsafe_allow_html=True)
with c2:
    st.markdown(_kpi_card("✅", finalizada, "Finalizadas",
                          f"{pct_fin:.0f}% do total", "green"), unsafe_allow_html=True)
with c3:
    st.markdown(_kpi_card("🔄", em_and, "Em Andamento",
                          f"{100*em_and/total_insp:.0f}%" if total_insp else "0%", "yellow"),
                unsafe_allow_html=True)
with c4:
    st.markdown(_kpi_card("🔴", snap_ni, "Nao Iniciadas",
                          "estado atual", "red",
                          f'<span class="delta-neg">⚠ {snap_crit} criticas (&gt;7d)</span>'
                          if snap_crit else ""), unsafe_allow_html=True)
with c5:
    st.markdown(_kpi_card("⚠️", nc_total, "NC Total",
                          f"no periodo", "yellow"), unsafe_allow_html=True)
with c6:
    st.markdown(_kpi_card("🔴", snap_nc_pend, "NC Pendentes",
                          "estado atual", "red" if snap_nc_pend > 0 else "green"),
                unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Linha 2: Evolucao mensal + Pizza ─────────────────────────────────────────
st.markdown('<div class="section-title">Evolucao Temporal</div>', unsafe_allow_html=True)

col_evol, col_pizza = st.columns([3, 2])

with col_evol:
    if mi_filtrado.empty:
        st.info("Sem dados de inspecoes para o periodo.")
    else:
        months = sorted(mi_filtrado["date_month"].unique())
        fin_vals  = []
        em_vals   = []
        nc_vals   = []
        for m in months:
            row = mi_filtrado[mi_filtrado["date_month"] == m]
            fin_vals.append(int(row["finalizada"].sum()))
            em_vals.append(int(row["em_andamento"].sum()))
            nc_vals.append(int(row["nc_total"].sum()))

        month_labels = [m.strftime("%b/%y") for m in months]

        fig_evol = go.Figure()
        fig_evol.add_trace(go.Scatter(
            x=month_labels, y=fin_vals, name="Finalizada",
            mode="lines+markers", line=dict(color=C_VERDE, width=2.5),
            marker=dict(size=7),
        ))
        fig_evol.add_trace(go.Scatter(
            x=month_labels, y=em_vals, name="Em Andamento",
            mode="lines+markers", line=dict(color=C_AMARELO, width=2.5),
            marker=dict(size=7),
        ))
        fig_evol.add_trace(go.Scatter(
            x=month_labels, y=nc_vals, name="NC Total",
            mode="lines+markers", line=dict(color=C_VERMELHO, width=1.5, dash="dot"),
            marker=dict(size=5),
        ))
        fig_evol.update_layout(
            title=dict(text="Evolucao Mensal de FVS", font=dict(size=13, color=C_AZUL_ESC)),
            height=300,
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#f8fafd",
            margin=dict(l=10, r=10, t=40, b=10),
            legend=dict(orientation="h", y=-0.15, font=dict(size=11)),
            xaxis=dict(tickfont=dict(size=10), gridcolor="#eaeef5"),
            yaxis=dict(tickfont=dict(size=10), gridcolor="#eaeef5"),
        )
        st.plotly_chart(fig_evol, use_container_width=True)
        st.caption('<span class="badge-fonte">Fonte: dataInspecao — proxy de atividade da FVS</span>',
                   unsafe_allow_html=True)

with col_pizza:
    if not latest_snap.empty:
        fin_s  = int((latest_snap["status"] == STATUS_FINALIZADA).sum())
        em_s   = int((latest_snap["status"] == STATUS_EM_ANDAMENTO).sum())
        nao_s  = int((latest_snap["status"] == STATUS_NAO_INICIADA).sum())
        total_s = fin_s + em_s + nao_s

        fig_pie = go.Figure(go.Pie(
            labels=["Finalizada", "Em Andamento", "Nao Iniciada"],
            values=[fin_s, em_s, nao_s],
            hole=0.55,
            marker_colors=[C_VERDE, C_AMARELO, C_VERMELHO],
            textinfo="percent+label",
            textfont=dict(size=11),
        ))
        fig_pie.update_layout(
            title=dict(text="Estado Atual das FVS", font=dict(size=13, color=C_AZUL_ESC)),
            height=300,
            paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=10, r=10, t=40, b=10),
            showlegend=False,
            annotations=[dict(text=f"<b>{total_s}</b><br>FVS", x=0.5, y=0.5,
                              font=dict(size=14), showarrow=False)],
        )
        st.plotly_chart(fig_pie, use_container_width=True)
        st.caption('<span class="badge-fonte">Fonte: snapshot ' +
                   (latest_snap["date_snapshot"].max().strftime("%d/%m/%Y") if not latest_snap.empty else "—") +
                   '</span>', unsafe_allow_html=True)
    else:
        st.info("Snapshot ainda nao disponivel.")

# ── Barras empilhadas por mes ─────────────────────────────────────────────────
st.markdown('<div class="section-title">Composicao Mensal por Status</div>', unsafe_allow_html=True)

if not mi_filtrado.empty:
    months = sorted(mi_filtrado["date_month"].unique())
    month_labels = [m.strftime("%b/%y") for m in months]
    fin_v  = [int(mi_filtrado[mi_filtrado["date_month"] == m]["finalizada"].sum()) for m in months]
    em_v   = [int(mi_filtrado[mi_filtrado["date_month"] == m]["em_andamento"].sum()) for m in months]

    fig_bar = go.Figure()
    fig_bar.add_trace(go.Bar(name="Finalizada",   x=month_labels, y=fin_v,
                             marker_color=C_VERDE,   opacity=0.85))
    fig_bar.add_trace(go.Bar(name="Em Andamento", x=month_labels, y=em_v,
                             marker_color=C_AMARELO,  opacity=0.85))
    fig_bar.update_layout(
        barmode="stack", height=260,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#f8fafd",
        margin=dict(l=10, r=10, t=20, b=10),
        legend=dict(orientation="h", y=-0.2, font=dict(size=11)),
        xaxis=dict(tickfont=dict(size=10), gridcolor="#eaeef5"),
        yaxis=dict(tickfont=dict(size=10), gridcolor="#eaeef5", title="Qtd FVS"),
    )
    st.plotly_chart(fig_bar, use_container_width=True)

# ── NC Evolucao + Comparativo obras ──────────────────────────────────────────
col_nc, col_comp = st.columns(2)

with col_nc:
    st.markdown('<div class="section-title">Nao-Conformidades</div>', unsafe_allow_html=True)
    if not mi_filtrado.empty:
        months = sorted(mi_filtrado["date_month"].unique())
        month_labels = [m.strftime("%b/%y") for m in months]
        nc_tot_v  = [int(mi_filtrado[mi_filtrado["date_month"] == m]["nc_total"].sum()) for m in months]
        nc_pend_v = [int(mi_filtrado[mi_filtrado["date_month"] == m]["nc_pendentes"].sum()) for m in months]
        nc_trat_v = [int(mi_filtrado[mi_filtrado["date_month"] == m]["nc_tratadas"].sum()) for m in months]

        fig_nc = go.Figure()
        fig_nc.add_trace(go.Scatter(
            x=month_labels, y=nc_tot_v, name="NC Total",
            mode="lines+markers", line=dict(color=C_VERMELHO, width=2.5), marker=dict(size=7),
        ))
        fig_nc.add_trace(go.Scatter(
            x=month_labels, y=nc_pend_v, name="NC Pendentes",
            mode="lines+markers", line=dict(color=C_AMARELO, width=2, dash="dash"), marker=dict(size=6),
        ))
        fig_nc.add_trace(go.Scatter(
            x=month_labels, y=nc_trat_v, name="NC Tratadas",
            mode="lines+markers", line=dict(color=C_VERDE, width=2, dash="dot"), marker=dict(size=6),
        ))
        fig_nc.update_layout(
            height=270,
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#f8fafd",
            margin=dict(l=10, r=10, t=20, b=10),
            legend=dict(orientation="h", y=-0.25, font=dict(size=10)),
            xaxis=dict(tickfont=dict(size=9)),
            yaxis=dict(tickfont=dict(size=9)),
        )
        st.plotly_chart(fig_nc, use_container_width=True)
        st.caption(
            '<span class="badge-fonte">NC pendente = qtdNaoConformidade - qtdNaoConformidadeTratada &nbsp;|&nbsp; '
            'Sem datas individuais de abertura (endpoint inexistente na API)</span>',
            unsafe_allow_html=True,
        )
    else:
        st.info("Sem dados no periodo.")

with col_comp:
    st.markdown('<div class="section-title">Comparativo entre Obras</div>', unsafe_allow_html=True)
    comp_df = build_obra_comparison(mi_all)
    comp_filt = comp_df[
        (comp_df["date_month"] >= date_start) &
        (comp_df["date_month"] <= date_end)
    ] if not comp_df.empty else comp_df

    if not comp_filt.empty:
        labels = [m.strftime("%b/%y") for m in comp_filt["date_month"]]
        fig_comp = go.Figure()
        fig_comp.add_trace(go.Bar(name="Cape Town", x=labels, y=comp_filt["fin_ct"].tolist(),
                                  marker_color=C_AZUL, opacity=0.85))
        fig_comp.add_trace(go.Bar(name="Holmes",    x=labels, y=comp_filt["fin_hm"].tolist(),
                                  marker_color="#5b9bd5", opacity=0.85))
        fig_comp.update_layout(
            barmode="group", height=270,
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#f8fafd",
            margin=dict(l=10, r=10, t=20, b=10),
            legend=dict(orientation="h", y=-0.25, font=dict(size=10)),
            xaxis=dict(tickfont=dict(size=9)),
            yaxis=dict(tickfont=dict(size=9), title="FVS Finalizadas"),
        )
        st.plotly_chart(fig_comp, use_container_width=True)
    else:
        st.info("Sem dados para comparativo no periodo.")

# ── Aging + Top Modelos ───────────────────────────────────────────────────────
col_aging, col_top = st.columns(2)

with col_aging:
    st.markdown('<div class="section-title">Aging de Backlog</div>', unsafe_allow_html=True)
    if not hist_snap.empty:
        snap_lat_date = hist_snap["date_snapshot"].max()
        snap_latest   = hist_snap[hist_snap["date_snapshot"] == snap_lat_date]
        if obra_filter:
            snap_latest = snap_latest[snap_latest["obra"] == obra_filter]

        pend = snap_latest[snap_latest["status"] != STATUS_FINALIZADA]
        if not pend.empty:
            faixas = ["0-3d", "4-7d", "8-14d", ">14d"]
            vals   = [int((pend["faixa_aging"] == f).sum()) for f in faixas]
            cores  = [C_VERDE, C_AMARELO, "#e67e22", C_VERMELHO]

            fig_aging = go.Figure(go.Bar(
                x=vals, y=faixas, orientation="h",
                marker_color=cores, text=vals, textposition="auto",
            ))
            fig_aging.update_layout(
                height=220,
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#f8fafd",
                margin=dict(l=10, r=10, t=10, b=10),
                xaxis=dict(tickfont=dict(size=10)),
                yaxis=dict(tickfont=dict(size=11), tickfont_color=C_AZUL_ESC),
            )
            st.plotly_chart(fig_aging, use_container_width=True)

            sla = compute_sla(hist_snap if not obra_filter else
                              (hist_ct if obra_filter == "Cape Town Residence" else hist_hm))
            st.caption(
                f"Dias medio pendente (Nao Iniciada): **{sla.get('avg_dias_nao_iniciada', 0):.1f}d** &nbsp;|&nbsp; "
                f"Maximo: **{sla.get('max_dias_nao_iniciada', 0)}d**"
            )
        else:
            st.success("Nenhum backlog pendente.")
    else:
        st.info("Historico de snapshots ainda nao disponivel.")

with col_top:
    st.markdown('<div class="section-title">Top Modelos com Pendencias</div>', unsafe_allow_html=True)
    if not hist_snap.empty:
        snap_lat_date = hist_snap["date_snapshot"].max()
        snap_latest   = hist_snap[hist_snap["date_snapshot"] == snap_lat_date]
        if obra_filter:
            snap_latest = snap_latest[snap_latest["obra"] == obra_filter]

        top = (
            snap_latest[snap_latest["status"] != STATUS_FINALIZADA]
            .groupby("modelo")
            .agg(pend=("status", "count"), nc=("nc", "sum"))
            .sort_values("pend", ascending=True)
            .tail(8)
            .reset_index()
        )
        if not top.empty:
            # Encurta nome do modelo
            top["modelo_curto"] = top["modelo"].str.replace(
                r"FVS \d+\.\d+\.\d+ - ", "", regex=True
            ).str[:35]
            fig_top = go.Figure()
            fig_top.add_trace(go.Bar(
                y=top["modelo_curto"], x=top["pend"], orientation="h",
                name="Pendentes", marker_color=C_AZUL, opacity=0.85,
            ))
            fig_top.add_trace(go.Bar(
                y=top["modelo_curto"], x=top["nc"], orientation="h",
                name="NC", marker_color=C_VERMELHO, opacity=0.7,
            ))
            fig_top.update_layout(
                barmode="overlay", height=280,
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#f8fafd",
                margin=dict(l=10, r=10, t=10, b=10),
                legend=dict(orientation="h", y=-0.15, font=dict(size=10)),
                xaxis=dict(tickfont=dict(size=9)),
                yaxis=dict(tickfont=dict(size=9)),
            )
            st.plotly_chart(fig_top, use_container_width=True)
        else:
            st.success("Nenhuma pendencia no estado atual.")
    else:
        st.info("Aguardando snapshots.")

# ── Alertas Criticos ──────────────────────────────────────────────────────────
st.markdown('<div class="section-title">Alertas Criticos</div>', unsafe_allow_html=True)

if not latest_snap.empty:
    criticas_df = latest_snap[
        (latest_snap["status"] == STATUS_NAO_INICIADA) &
        (latest_snap["dias_pendente"] > 7)
    ]
    nc_pend_df = latest_snap[latest_snap["nc_pendentes"] > 0] \
        if "nc_pendentes" in latest_snap.columns else pd.DataFrame()

    if criticas_df.empty and nc_pend_df.empty:
        st.markdown(
            '<div style="background:#d4edda;border:1px solid #c3e6cb;border-radius:8px;'
            'padding:12px 16px;color:#155724;font-size:13px;font-weight:600;">'
            '✅ Nenhum alerta critico no momento.</div>',
            unsafe_allow_html=True,
        )
    else:
        if not criticas_df.empty:
            st.markdown(
                f'<div class="alert-critico">🔴 <b>{len(criticas_df)} FVS com mais de 7 dias sem ser iniciadas</b>'
                f' — requerem abertura imediata no InMeta.</div>',
                unsafe_allow_html=True,
            )
            show_df = criticas_df[["obra", "floor", "modelo", "local", "dias_pendente", "nc"]].copy()
            show_df.columns = ["Obra", "Pavimento", "Modelo FVS", "Local", "Dias Pendente", "NC"]
            show_df = show_df.sort_values("Dias Pendente", ascending=False)
            st.dataframe(show_df, use_container_width=True, hide_index=True,
                         height=min(35 * len(show_df) + 38, 280))

        if not nc_pend_df.empty:
            total_nc_p = int(nc_pend_df["nc_pendentes"].sum()) \
                if "nc_pendentes" in nc_pend_df.columns else "?"
            st.markdown(
                f'<div class="alert-aviso">⚠️ <b>{total_nc_p} NC pendentes</b> em '
                f'{len(nc_pend_df)} FVS — aguardando tratamento.</div>',
                unsafe_allow_html=True,
            )
else:
    st.info("Sem snapshot disponivel para verificar alertas.")

# ── Tabela Mensal (Excel view) ────────────────────────────────────────────────
with st.expander("📊 Tabela Mensal Detalhada", expanded=False):
    if not mi_filtrado.empty:
        pivot = mi_filtrado.pivot_table(
            index="obra",
            columns="date_month",
            values=["finalizada", "em_andamento", "nc_total", "nc_pendentes"],
            aggfunc="sum",
            fill_value=0,
        )
        pivot.columns = [f"{v.replace('_', ' ').title()} {m.strftime('%b/%y')}"
                         for v, m in pivot.columns]
        st.dataframe(pivot, use_container_width=True)
    else:
        st.info("Sem dados no periodo selecionado.")

# ── Exportacoes ───────────────────────────────────────────────────────────────
st.markdown('<div class="section-title">Exportacoes</div>', unsafe_allow_html=True)

col_pdf, col_xl, col_info = st.columns([2, 2, 3])

with col_pdf:
    try:
        from fvs_dashboard.core.audit_exporter import export_audit_pdf
        with st.spinner("Gerando PDF executivo com graficos..."):
            pdf_bytes = export_audit_pdf(
                monthly_insp=mi_filtrado,
                kpis=kpis,
                obra=obra_sel,
                periodo_label=periodo_label,
                date_start=date_start,
                date_end=date_end,
                latest_snap=latest_snap,
                hist_snap=hist_snap,
            )
        today_str  = datetime.date.today().strftime("%Y%m%d")
        obra_slug  = obra_sel.replace(" ", "_")
        st.download_button(
            label="⬇️ PDF Executivo",
            data=pdf_bytes,
            file_name=f"Auditoria_R21_{obra_slug}_{today_str}.pdf",
            mime="application/pdf",
            use_container_width=True,
            type="primary",
        )
    except Exception as e:
        st.error(f"Erro PDF: {e}")

with col_xl:
    try:
        from fvs_dashboard.core.audit_exporter import export_audit_excel
        with st.spinner("Gerando Excel..."):
            xl_bytes = export_audit_excel(
                monthly_insp=mi_filtrado,
                kpis=kpis,
                obra=obra_sel,
                periodo_label=periodo_label,
                date_start=date_start,
                date_end=date_end,
                hist_snap=hist_snap,
            )
        today_str  = datetime.date.today().strftime("%Y%m%d")
        obra_slug  = obra_sel.replace(" ", "_")
        st.download_button(
            label="⬇️ Excel Gerencial",
            data=xl_bytes,
            file_name=f"Auditoria_R21_{obra_slug}_{today_str}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    except Exception as e:
        st.error(f"Erro Excel: {e}")

with col_info:
    ages_ct = dm.cache_age("Cape Town Residence")
    st.caption(
        f"Cache InMeta: {ages_ct['inmeta']} &nbsp;|&nbsp; "
        f"Prevision: {ages_ct['prevision']} &nbsp;|&nbsp; "
        f"Snapshots: {len(hist_snap['date_snapshot'].unique()) if not hist_snap.empty else 0} dias"
    )
    st.caption(
        "Dados historicos: dataInspecao (InMeta, nov/2024–mai/2026) &nbsp;|&nbsp; "
        "NC: contagens agregadas — sem datas individuais (endpoint inexistente na API)"
    )
