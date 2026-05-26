"""
Pagina 7 — Condicao do Tempo
============================
Graficos de pizza interativos com condicao climatica por periodo.
Dados inseridos manualmente por mes — API InMeta nao expoe modulo Diario.
Historico pre-InMeta registrado como constante (Cape Town: Sol=129, Nub=77, Chu=42).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import date, datetime

import streamlit as st
import plotly.graph_objects as go
import pandas as pd

# ── Path setup ────────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fvs_dashboard.core.data_manager import OBRAS, DATA_RAW

# ── Constantes históricas (pré-InMeta, fixas) ────────────────────────────────
HISTORICAL: dict[str, dict[str, int]] = {
    "Cape Town Residence": {"ENSOLARADO": 129, "NUBLADO": 77, "CHUVOSO": 42},
    "Holmes Residence":    {"ENSOLARADO": 0,   "NUBLADO": 0,  "CHUVOSO": 0},
}

# ── Metadados visuais ─────────────────────────────────────────────────────────
WEATHER_META: dict[str, dict] = {
    "ENSOLARADO": {"icon": "☀️",  "label": "Ensolarado", "color": "#F6A623"},
    "NUBLADO":    {"icon": "⛅", "label": "Nublado",    "color": "#82A0C0"},
    "CHUVOSO":    {"icon": "🌧️", "label": "Chuvoso",    "color": "#4A7BB5"},
}
WEATHER_KEYS = list(WEATHER_META.keys())

MONTHS_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março",    4: "Abril",
    5: "Maio",    6: "Junho",     7: "Julho",     8: "Agosto",
    9: "Setembro",10: "Outubro",  11: "Novembro", 12: "Dezembro",
}
MONTHS_SHORT = {k: v[:3] for k, v in MONTHS_PT.items()}

# ── Arquivo de dados manuais ──────────────────────────────────────────────────
WEATHER_DATA_FILE = DATA_RAW / "weather_manual.json"

# ── Leitura / escrita ─────────────────────────────────────────────────────────

def _load_data() -> dict:
    """
    Estrutura: { "cape_town": {"2025-01": {"ENSOLARADO":15,"NUBLADO":8,"CHUVOSO":7}, ...}, ... }
    """
    if not WEATHER_DATA_FILE.exists():
        return {}
    try:
        return json.loads(WEATHER_DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_data(data: dict) -> None:
    WEATHER_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    WEATHER_DATA_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _obra_key(obra: str) -> str:
    return OBRAS[obra]["insp_key"]  # "cape_town" ou "holmes"


# ── Agregações ────────────────────────────────────────────────────────────────

def _get_obra_months(data: dict, obra: str) -> dict[str, dict[str, int]]:
    """Retorna dict {YYYY-MM: {ENSOLARADO:n, NUBLADO:n, CHUVOSO:n}} para a obra."""
    return data.get(_obra_key(obra), {})


def _sum_months(months: dict[str, dict[str, int]]) -> dict[str, int]:
    """Soma todos os meses."""
    total = {k: 0 for k in WEATHER_KEYS}
    for m_data in months.values():
        for k in WEATHER_KEYS:
            total[k] += m_data.get(k, 0)
    return total


def _available_periods(months: dict) -> list[str]:
    """Lista de YYYY-MM ordenados."""
    return sorted(months.keys())


# ── Gráfico de pizza ─────────────────────────────────────────────────────────

def _make_pie(counts: dict[str, int], title: str, center_label: str = "dias") -> go.Figure:
    labels, values, colors = [], [], []
    for key in WEATHER_KEYS:
        m = WEATHER_META[key]
        labels.append(f"{m['icon']} {m['label']}")
        values.append(counts.get(key, 0))
        colors.append(m["color"])

    total = sum(values)

    fig = go.Figure(go.Pie(
        labels=labels,
        values=values,
        hole=0.45,
        marker=dict(colors=colors, line=dict(color="#ffffff", width=2)),
        textinfo="label+percent",
        textfont=dict(size=12, family="Arial"),
        hovertemplate="<b>%{label}</b><br>%{value} dias (%{percent})<extra></extra>",
        sort=False,
    ))
    fig.update_layout(
        title=dict(
            text=f"<b>{title}</b>",
            font=dict(size=14, color="#C41230", family="Arial Black"),
            x=0.5, xanchor="center",
        ),
        annotations=[dict(
            text=f"<b>{total}</b><br><span style='font-size:10px'>{center_label}</span>",
            x=0.5, y=0.5,
            font=dict(size=20, color="#1A1A1A", family="Arial Black"),
            showarrow=False,
        )],
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.30, xanchor="center", x=0.5,
                    font=dict(size=11)),
        margin=dict(t=55, b=70, l=10, r=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=380,
    )
    return fig


_PLOTLY_CFG = {
    "displaylogo": False,
    "modeBarButtonsToRemove": [
        "zoom2d", "pan2d", "select2d", "lasso2d",
        "zoomIn2d", "zoomOut2d", "autoScale2d", "resetScale2d",
    ],
    "toImageButtonOptions": {
        "format": "png", "filename": "condicao_do_tempo",
        "height": 500, "width": 600, "scale": 2,
    },
}

# ── Resumo card ───────────────────────────────────────────────────────────────

def _summary_card(counts: dict[str, int], label: str, border_color: str, title_color: str):
    total = sum(counts.get(k, 0) for k in WEATHER_KEYS)
    lines = "".join(
        f"<div>{WEATHER_META[k]['icon']} {WEATHER_META[k]['label']}: "
        f"<b>{counts.get(k,0)}</b> dias "
        f"({'—' if total==0 else f'{counts.get(k,0)/total*100:.0f}%'})</div>"
        for k in WEATHER_KEYS
    )
    st.markdown(
        f"""<div style="background:rgba(0,0,0,0.04); border-left:3px solid {border_color};
            border-radius:6px; padding:10px 14px; font-size:12px;">
            <div style="font-weight:700;color:{title_color};margin-bottom:6px;">{label}</div>
            {lines}
            <div style="margin-top:6px;border-top:1px solid rgba(0,0,0,0.1);padding-top:6px;">
                <b>Total: {total}</b> dias</div></div>""",
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PÁGINA PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

st.markdown("""
<div style="background:linear-gradient(135deg,#8B0D22 0%,#C41230 100%);
    padding:18px 24px 14px;border-radius:10px;margin-bottom:20px;">
    <div style="font-size:22px;font-weight:800;color:#fff;letter-spacing:-0.3px;">
        🌤️ Condição do Tempo</div>
    <div style="font-size:12px;color:rgba(255,255,255,0.75);margin-top:4px;">
        Registros históricos + entrada mensal de dados por obra</div>
</div>""", unsafe_allow_html=True)

obra = st.session_state.get("obra", list(OBRAS.keys())[0])

# Carrega dados
weather_data = _load_data()
obra_months  = _get_obra_months(weather_data, obra)
hist         = HISTORICAL.get(obra, {})

# Soma histórico + meses manuais
counts_manual = _sum_months(obra_months)
counts_total  = {k: hist.get(k, 0) + counts_manual.get(k, 0) for k in WEATHER_KEYS}

periods       = _available_periods(obra_months)  # ["2025-01", "2025-02", ...]
period_labels = [
    f"{MONTHS_SHORT[int(p[5:7])]}/{p[2:4]}" for p in periods
]

# ── Abas: Gráficos | Inserir Dados ───────────────────────────────────────────
tab_charts, tab_input = st.tabs(["📊 Gráficos", "✏️ Inserir / Editar Dados"])

# ═════════════════════════════════════════════════════════════════════════════
# ABA 1 — GRÁFICOS
# ═════════════════════════════════════════════════════════════════════════════
with tab_charts:

    # Seletores de período
    sel_col1, sel_col2 = st.columns(2)
    with sel_col1:
        if period_labels:
            sel_p1 = st.selectbox("Período 1", period_labels,
                                  index=max(0, len(periods)-1), key="tempo_p1")
            p1_key = periods[period_labels.index(sel_p1)]
            counts_p1 = obra_months.get(p1_key, {k: 0 for k in WEATHER_KEYS})
            label_p1  = f"{MONTHS_PT[int(p1_key[5:7])]} {p1_key[:4]}"
        else:
            st.selectbox("Período 1", ["(sem dados)"], disabled=True, key="tempo_p1")
            counts_p1, label_p1, p1_key = None, None, None

    with sel_col2:
        if period_labels:
            idx2 = max(0, len(periods)-2)
            sel_p2 = st.selectbox("Período 2", period_labels,
                                  index=idx2, key="tempo_p2")
            p2_key = periods[period_labels.index(sel_p2)]
            counts_p2 = obra_months.get(p2_key, {k: 0 for k in WEATHER_KEYS})
            label_p2  = f"{MONTHS_PT[int(p2_key[5:7])]} {p2_key[:4]}"
        else:
            st.selectbox("Período 2", ["(sem dados)"], disabled=True, key="tempo_p2")
            counts_p2, label_p2, p2_key = None, None, None

    st.markdown("")

    # 3 colunas de pizza
    c1, c2, c3 = st.columns(3)

    with c1:
        hist_total   = sum(hist.values())
        manual_total = sum(counts_manual.values())
        fig1 = _make_pie(counts_total, "Total Acumulado", "dias")
        st.plotly_chart(fig1, use_container_width=True, config=_PLOTLY_CFG)
        st.markdown(
            f"""<div style="background:rgba(196,18,48,0.06);border-left:3px solid #C41230;
                border-radius:6px;padding:10px 14px;font-size:12px;">
                <div style="font-weight:700;color:#C41230;margin-bottom:6px;">Composição</div>
                <div>📚 Histórico pré-InMeta: <b>{hist_total}</b> dias</div>
                <div>✏️ Entrada manual: <b>{manual_total}</b> dias ({len(obra_months)} meses)</div>
                <div style="margin-top:6px;border-top:1px solid rgba(196,18,48,0.2);padding-top:6px;">
                    <b>Total: {hist_total+manual_total}</b> dias</div></div>""",
            unsafe_allow_html=True,
        )

    with c2:
        if counts_p1 is not None:
            fig2 = _make_pie(counts_p1, f"Período 1", "dias")
            st.plotly_chart(fig2, use_container_width=True, config=_PLOTLY_CFG)
            _summary_card(counts_p1, label_p1, "#82A0C0", "#4A7BB5")
        else:
            st.markdown(
                """<div style="display:flex;align-items:center;justify-content:center;
                    height:340px;background:rgba(0,0,0,0.04);border-radius:10px;
                    border:1px dashed #ccc;flex-direction:column;gap:8px;">
                    <div style="font-size:36px;">✏️</div>
                    <div style="font-size:13px;color:#888;text-align:center;">
                        Sem dados manuais.<br>Use a aba <b>Inserir / Editar Dados</b>.</div>
                </div>""",
                unsafe_allow_html=True,
            )

    with c3:
        if counts_p2 is not None:
            fig3 = _make_pie(counts_p2, f"Período 2", "dias")
            st.plotly_chart(fig3, use_container_width=True, config=_PLOTLY_CFG)
            _summary_card(counts_p2, label_p2, "#F6A623", "#D48B10")
        else:
            st.markdown(
                """<div style="display:flex;align-items:center;justify-content:center;
                    height:340px;background:rgba(0,0,0,0.04);border-radius:10px;
                    border:1px dashed #ccc;flex-direction:column;gap:8px;">
                    <div style="font-size:36px;">✏️</div>
                    <div style="font-size:13px;color:#888;text-align:center;">
                        Sem dados manuais.<br>Use a aba <b>Inserir / Editar Dados</b>.</div>
                </div>""",
                unsafe_allow_html=True,
            )

    # Evolução mensal — barras empilhadas
    if obra_months:
        st.divider()
        st.markdown("#### 📊 Evolução Mensal")

        monthly = []
        for p in periods:
            d = obra_months[p]
            monthly.append({
                "Mês":        f"{MONTHS_SHORT[int(p[5:7])]}/{p[2:4]}",
                "Ensolarado": d.get("ENSOLARADO", 0),
                "Nublado":    d.get("NUBLADO",    0),
                "Chuvoso":    d.get("CHUVOSO",    0),
            })
        df_m = pd.DataFrame(monthly)

        fig_bar = go.Figure()
        for col, color, name in [
            ("Ensolarado", "#F6A623", "☀️ Ensolarado"),
            ("Nublado",    "#82A0C0", "⛅ Nublado"),
            ("Chuvoso",    "#4A7BB5", "🌧️ Chuvoso"),
        ]:
            fig_bar.add_trace(go.Bar(
                name=name, x=df_m["Mês"], y=df_m[col],
                marker_color=color, text=df_m[col], textposition="inside",
            ))

        fig_bar.update_layout(
            barmode="stack", height=300,
            margin=dict(t=20, b=10, l=10, r=10),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            xaxis=dict(tickangle=-30, tickfont=dict(size=11)),
            yaxis=dict(title="Dias", gridcolor="rgba(0,0,0,0.08)"),
        )
        st.plotly_chart(fig_bar, use_container_width=True, config={
            **_PLOTLY_CFG,
            "toImageButtonOptions": {**_PLOTLY_CFG["toImageButtonOptions"],
                                     "filename": "tempo_mensal", "width": 1000},
        })

        with st.expander("Ver tabela"):
            df_m["Total"] = df_m["Ensolarado"] + df_m["Nublado"] + df_m["Chuvoso"]
            st.dataframe(df_m, use_container_width=True, hide_index=True)

    st.markdown(
        """<div style="margin-top:24px;padding:10px 14px;background:rgba(0,0,0,0.03);
            border-radius:6px;font-size:11px;color:#888;">
            ℹ️ <b>Total Acumulado</b> = registros históricos pré-InMeta + meses inseridos manualmente.
            Clique no ícone 📷 na barra do gráfico para baixar como imagem PNG.</div>""",
        unsafe_allow_html=True,
    )

# ═════════════════════════════════════════════════════════════════════════════
# ABA 2 — INSERIR / EDITAR DADOS
# ═════════════════════════════════════════════════════════════════════════════
with tab_input:

    st.markdown("### ✏️ Registrar condição do tempo por mês")
    st.caption(
        "Consulte o Diário de Obra no InMeta e insira os totais mensais abaixo. "
        "Os dados ficam salvos permanentemente."
    )

    # ── Formulário de entrada ─────────────────────────────────────────────────
    with st.form("form_weather", clear_on_submit=True):
        fc1, fc2 = st.columns(2)
        with fc1:
            f_obra = st.selectbox("Obra", list(OBRAS.keys()), key="fw_obra",
                                  index=list(OBRAS.keys()).index(obra))
        with fc2:
            _today = date.today()
            anos_opts = list(range(_today.year - 3, _today.year + 2))
            f_ano = st.selectbox("Ano", anos_opts,
                                 index=anos_opts.index(_today.year), key="fw_ano")

        fc3, fc4, fc5, fc6 = st.columns(4)
        with fc3:
            f_mes = st.selectbox("Mês", list(MONTHS_PT.keys()),
                                 format_func=lambda x: MONTHS_PT[x],
                                 index=_today.month - 1, key="fw_mes")
        with fc4:
            f_sol = st.number_input("☀️ Ensolarado", min_value=0, max_value=31,
                                    value=0, step=1, key="fw_sol")
        with fc5:
            f_nub = st.number_input("⛅ Nublado", min_value=0, max_value=31,
                                    value=0, step=1, key="fw_nub")
        with fc6:
            f_chu = st.number_input("🌧️ Chuvoso", min_value=0, max_value=31,
                                    value=0, step=1, key="fw_chu")

        submitted = st.form_submit_button("💾 Salvar mês", use_container_width=True,
                                          type="primary")

    if submitted:
        total_dias_form = f_sol + f_nub + f_chu
        if total_dias_form == 0:
            st.warning("Informe pelo menos 1 dia antes de salvar.")
        elif total_dias_form > 31:
            st.warning(f"Total de {total_dias_form} dias excede o máximo de 31 por mês.")
        else:
            key_obra = _obra_key(f_obra)
            period_k = f"{f_ano}-{f_mes:02d}"
            wd = _load_data()
            if key_obra not in wd:
                wd[key_obra] = {}
            wd[key_obra][period_k] = {
                "ENSOLARADO": int(f_sol),
                "NUBLADO":    int(f_nub),
                "CHUVOSO":    int(f_chu),
            }
            _save_data(wd)
            st.success(
                f"✅ {MONTHS_PT[f_mes]}/{f_ano} — {f_obra} salvo! "
                f"(☀️ {f_sol}  ⛅ {f_nub}  🌧️ {f_chu})"
            )
            st.rerun()

    # ── Tabela de registros existentes ────────────────────────────────────────
    st.divider()
    st.markdown(f"#### Registros de **{obra}**")

    obra_months_now = _get_obra_months(_load_data(), obra)

    if not obra_months_now:
        st.info("Nenhum dado manual registrado ainda para esta obra.")
    else:
        rows_table = []
        for p in sorted(obra_months_now.keys(), reverse=True):
            d = obra_months_now[p]
            rows_table.append({
                "Período":    f"{MONTHS_PT[int(p[5:7])]} {p[:4]}",
                "☀️ Ensolarado": d.get("ENSOLARADO", 0),
                "⛅ Nublado":    d.get("NUBLADO",    0),
                "🌧️ Chuvoso":   d.get("CHUVOSO",    0),
                "Total":      sum(d.get(k, 0) for k in WEATHER_KEYS),
                "_key":       p,
            })

        df_table = pd.DataFrame(rows_table)

        # Edita inline (st.data_editor)
        edited = st.data_editor(
            df_table[["Período", "☀️ Ensolarado", "⛅ Nublado", "🌧️ Chuvoso", "Total"]],
            use_container_width=True,
            hide_index=True,
            disabled=["Período", "Total"],
            key="weather_editor",
        )

        # Detecta mudanças e salva
        _changed = False
        wd_edit = _load_data()
        ok_key = _obra_key(obra)
        for i, row in edited.iterrows():
            orig_key = rows_table[i]["_key"]
            new_vals = {
                "ENSOLARADO": int(row["☀️ Ensolarado"]),
                "NUBLADO":    int(row["⛅ Nublado"]),
                "CHUVOSO":    int(row["🌧️ Chuvoso"]),
            }
            if new_vals != {k: obra_months_now[orig_key].get(k, 0) for k in WEATHER_KEYS}:
                wd_edit[ok_key][orig_key] = new_vals
                _changed = True

        if _changed:
            _save_data(wd_edit)
            st.success("Alterações salvas!")
            st.rerun()

        # Excluir período
        st.markdown("")
        del_period = st.selectbox(
            "Excluir período",
            options=["— selecione —"] + [r["Período"] for r in rows_table],
            key="del_period",
        )
        if del_period != "— selecione —":
            if st.button(f"🗑️ Excluir {del_period}", type="secondary"):
                del_key = rows_table[[r["Período"] for r in rows_table].index(del_period)]["_key"]
                wd_del = _load_data()
                wd_del.get(_obra_key(obra), {}).pop(del_key, None)
                _save_data(wd_del)
                st.success(f"Período {del_period} excluído.")
                st.rerun()

    # ── Histórico pré-InMeta (informativo) ────────────────────────────────────
    st.divider()
    st.markdown("#### 📚 Histórico pré-InMeta (fixo)")
    st.caption("Esses valores são constantes registrados antes do uso do InMeta.")
    h = HISTORICAL.get(obra, {})
    cols_h = st.columns(3)
    for i, k in enumerate(WEATHER_KEYS):
        with cols_h[i]:
            m = WEATHER_META[k]
            st.metric(f"{m['icon']} {m['label']}", f"{h.get(k, 0)} dias")
