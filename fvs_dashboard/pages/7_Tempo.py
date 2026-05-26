"""
Pagina 7 — Condicao do Tempo
============================
Graficos de pizza interativos com condicao climatica por periodo.
Inclui historico pre-InMeta registrado manualmente.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from datetime import date

import httpx
import time
import streamlit as st
import plotly.graph_objects as go
import pandas as pd

# ── Path setup ────────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fvs_dashboard.core.data_manager import OBRAS, DATA_RAW

# ── Constantes históricas (pré-InMeta) ───────────────────────────────────────
# Registros manuais anteriores ao uso do InMeta Diário de Obra
HISTORICAL: dict[str, dict[str, int]] = {
    "Cape Town Residence": {"ENSOLARADO": 129, "NUBLADO": 77, "CHUVOSO": 42},
    "Holmes Residence":    {"ENSOLARADO": 0,   "NUBLADO": 0,  "CHUVOSO": 0},
}

# ── Metadados visuais de clima ────────────────────────────────────────────────
WEATHER_META: dict[str, dict] = {
    "ENSOLARADO": {"icon": "☀️",  "label": "Ensolarado", "color": "#F6A623"},
    "NUBLADO":    {"icon": "⛅", "label": "Nublado",    "color": "#82A0C0"},
    "CHUVOSO":    {"icon": "🌧️", "label": "Chuvoso",    "color": "#4A7BB5"},
}
WEATHER_KEYS = list(WEATHER_META.keys())

DIARIO_CACHE = DATA_RAW / "inmeta_diario_raw.json"

MONTHS_PT = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr",
    5: "Mai", 6: "Jun", 7: "Jul", 8: "Ago",
    9: "Set", 10: "Out", 11: "Nov", 12: "Dez",
}

# ── Helpers de segredos ───────────────────────────────────────────────────────

def _secret(key: str, default: str = "") -> str:
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key, default)


# ── Leitura / escrita do cache diário ────────────────────────────────────────

def _load_diario_cache() -> dict:
    if not DIARIO_CACHE.exists():
        return {}
    try:
        return json.loads(DIARIO_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_diario_cache(data: dict) -> None:
    DIARIO_CACHE.parent.mkdir(parents=True, exist_ok=True)
    DIARIO_CACHE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# ── Normalização de condição climática ───────────────────────────────────────

def _normalize(val: str) -> str:
    """Normaliza string de condição para ENSOLARADO / NUBLADO / CHUVOSO."""
    if not val:
        return "OUTRO"
    v = str(val).upper().strip()
    if any(x in v for x in ["SOL", "ENSOL", "SUNNY", "CLEAR", "BOM", "ABERTO"]):
        return "ENSOLARADO"
    if any(x in v for x in ["NUBLA", "CLOUDY", "PARCIAL", "OVERCAST"]):
        return "NUBLADO"
    if any(x in v for x in ["CHUV", "RAIN", "MOLHA"]):
        return "CHUVOSO"
    return v


# ── Extração de clima das inspeções diário ───────────────────────────────────

_CAMPO_CLIMA = [
    "condicaoClimatica", "climaCondicao", "clima", "weather",
    "tempoClimatico", "condicaoTempo", "tempo", "condicao",
]


def _extract_rows(inspections: list[dict]) -> list[dict]:
    """Extrai lista de {data, cond} das inspeções do diário."""
    rows = []
    for insp in inspections:
        cond = None
        # Tenta campos conhecidos
        for field in _CAMPO_CLIMA:
            val = insp.get(field)
            if val and isinstance(val, str):
                cond = _normalize(val)
                break
        # Fallback: qualquer campo cujo nome contenha "clima" ou "tempo"
        if cond is None:
            for key, val in insp.items():
                if isinstance(val, str) and any(
                    x in key.lower() for x in ["clima", "tempo", "weather"]
                ):
                    cond = _normalize(val)
                    break
        if cond is None:
            cond = "OUTRO"

        date_str = insp.get("dataInspecao", "") or ""
        rows.append({"cond": cond, "data": date_str[:10] if len(date_str) >= 10 else ""})
    return rows


def _count(rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {k: 0 for k in WEATHER_KEYS}
    counts["OUTRO"] = 0
    for r in rows:
        c = r["cond"]
        counts[c] = counts.get(c, 0) + 1
    return counts


def _filter_period(rows: list[dict], year: int, month: int | None) -> list[dict]:
    out = []
    for r in rows:
        d = r.get("data", "")
        if not d or len(d) < 7:
            continue
        try:
            yr = int(d[:4])
            mo = int(d[5:7])
        except ValueError:
            continue
        if yr == year and (month is None or mo == month):
            out.append(r)
    return out


def _available_periods(rows: list[dict]) -> list[tuple[int, int]]:
    """Retorna lista de (ano, mes) únicos disponíveis, ordenados."""
    seen: set[tuple[int, int]] = set()
    for r in rows:
        d = r.get("data", "")
        if d and len(d) >= 7:
            try:
                seen.add((int(d[:4]), int(d[5:7])))
            except ValueError:
                pass
    return sorted(seen)


# ── Gráfico de pizza ─────────────────────────────────────────────────────────

def _make_pie(
    counts: dict[str, int],
    title: str,
    center_label: str = "dias",
) -> go.Figure:
    labels, values, colors = [], [], []
    for key in WEATHER_KEYS:
        m = WEATHER_META[key]
        labels.append(f"{m['icon']} {m['label']}")
        values.append(counts.get(key, 0))
        colors.append(m["color"])

    outro = counts.get("OUTRO", 0)
    if outro > 0:
        labels.append("❓ Outro")
        values.append(outro)
        colors.append("#BBBBBB")

    total = sum(values)

    fig = go.Figure(go.Pie(
        labels=labels,
        values=values,
        hole=0.45,
        marker=dict(
            colors=colors,
            line=dict(color="#ffffff", width=2),
        ),
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
        legend=dict(
            orientation="h",
            yanchor="bottom", y=-0.30,
            xanchor="center", x=0.5,
            font=dict(size=11),
        ),
        margin=dict(t=55, b=70, l=10, r=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=380,
    )
    return fig


# ── Config do modebar Plotly (download) ──────────────────────────────────────
_PLOTLY_CFG = {
    "displaylogo": False,
    "modeBarButtonsToRemove": [
        "zoom2d", "pan2d", "select2d", "lasso2d",
        "zoomIn2d", "zoomOut2d", "autoScale2d", "resetScale2d",
    ],
    "toImageButtonOptions": {
        "format": "png",
        "filename": "condicao_do_tempo",
        "height": 500,
        "width": 600,
        "scale": 2,
    },
}

# ── Fetch InMeta diário ───────────────────────────────────────────────────────

def _fetch_diario_httpx(base_url: str, email: str, senha: str, alvo_id: str) -> list[dict]:
    """
    Busca inspecoes do Diario de Obra diretamente via httpx (sem InMetaClient).
    Faz auth JWT própria para evitar dependência de módulo cacheado.
    """
    base_url = base_url.rstrip("/")
    # 1. Autentica
    r_auth = httpx.post(
        f"{base_url}/api/v1/token",
        json={"email": email, "senha": senha},
        timeout=15,
    )
    r_auth.raise_for_status()
    token = r_auth.json()["content"]["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Busca diário
    r = httpx.get(
        f"{base_url}/api/v1/alvos/{alvo_id}/inspecoes/atuais",
        headers=headers,
        params={"modulo": "DIARIO"},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    return data.get("content", []) if isinstance(data, dict) else data


def _do_refresh_diario() -> tuple[bool, str]:
    """Busca dados diário do InMeta e salva no cache. Retorna (sucesso, msg)."""
    try:
        base_url = _secret("INMETA_BASE_URL", "https://api.inmeta.com.br")
        email    = _secret("INMETA_EMAIL")
        senha    = _secret("INMETA_SENHA")

        cache: dict = _load_diario_cache()
        cache["collected_at"] = str(date.today())
        total = 0
        for obra_name, cfg in OBRAS.items():
            insps = _fetch_diario_httpx(base_url, email, senha, cfg["inmeta_id"])
            key   = cfg["insp_key"]
            cache[key] = {"inspections": insps}
            total += len(insps)
        _save_diario_cache(cache)
        # Invalida cache de session_state
        for k in list(st.session_state.keys()):
            if k.startswith("diario_rows_"):
                del st.session_state[k]
        return True, f"✅ {total} registros diários carregados."
    except Exception as e:
        return False, f"❌ Erro ao buscar InMeta: {e}"


# ── Carregamento de rows diário (com cache em session_state) ──────────────────

def _get_diario_rows(obra: str) -> list[dict]:
    cache_key = f"diario_rows_{obra}"
    if cache_key in st.session_state:
        return st.session_state[cache_key]

    raw = _load_diario_cache()
    key = OBRAS[obra]["insp_key"]
    insps = raw.get(key, {}).get("inspections", [])
    rows = _extract_rows(insps)
    st.session_state[cache_key] = rows
    return rows


# ═══════════════════════════════════════════════════════════════════════════════
# PÁGINA PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

st.markdown("""
<div style="
    background: linear-gradient(135deg, #8B0D22 0%, #C41230 100%);
    padding: 18px 24px 14px 24px;
    border-radius: 10px;
    margin-bottom: 20px;
">
    <div style="font-size:22px; font-weight:800; color:#ffffff; letter-spacing:-0.3px;">
        🌤️ Condição do Tempo
    </div>
    <div style="font-size:12px; color:rgba(255,255,255,0.75); margin-top:4px;">
        Registros históricos + dados InMeta Diário de Obra
    </div>
</div>
""", unsafe_allow_html=True)

# ── Seleção de obra ───────────────────────────────────────────────────────────
obra = st.session_state.get("obra", list(OBRAS.keys())[0])

# ── Controles de atualização ──────────────────────────────────────────────────
col_info, col_btn = st.columns([3, 1])

raw_cache = _load_diario_cache()
_collected_at = raw_cache.get("collected_at", None)

with col_info:
    if _collected_at:
        st.caption(f"📅 Dados InMeta atualizados em: **{_collected_at}**")
    else:
        st.caption("ℹ️ Dados InMeta ainda não carregados. Clique em **Atualizar Diário**.")

with col_btn:
    if st.button("🔄 Atualizar Diário", use_container_width=True, type="primary"):
        with st.spinner("Buscando dados diário no InMeta..."):
            ok, msg = _do_refresh_diario()
        if ok:
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)

st.divider()

# ── Carrega dados ─────────────────────────────────────────────────────────────
hist = HISTORICAL.get(obra, {})
diario_rows = _get_diario_rows(obra)

# Soma histórico + InMeta para totais acumulados
counts_inmeta = _count(diario_rows)
counts_total: dict[str, int] = {}
for k in WEATHER_KEYS:
    counts_total[k] = hist.get(k, 0) + counts_inmeta.get(k, 0)
counts_total["OUTRO"] = counts_inmeta.get("OUTRO", 0)

# ── Períodos disponíveis no InMeta ────────────────────────────────────────────
periods = _available_periods(diario_rows)  # [(ano, mes), ...]
period_labels = [f"{MONTHS_PT[m]}/{str(y)[-2:]}" for y, m in periods]

_no_inmeta = len(diario_rows) == 0

# ── Seletores de período ──────────────────────────────────────────────────────
st.markdown("#### Selecione os períodos para comparar")

sel_col1, sel_col2 = st.columns(2)

_default_idx_1 = max(0, len(periods) - 1) if periods else 0
_default_idx_2 = max(0, len(periods) - 2) if len(periods) > 1 else 0

with sel_col1:
    if period_labels:
        sel_p1 = st.selectbox(
            "Período 1",
            options=period_labels,
            index=_default_idx_1,
            key="tempo_p1",
        )
        p1_idx   = period_labels.index(sel_p1)
        p1_year, p1_month = periods[p1_idx]
    else:
        st.selectbox("Período 1", options=["(sem dados)"], disabled=True, key="tempo_p1")
        p1_year, p1_month = None, None

with sel_col2:
    if period_labels:
        sel_p2 = st.selectbox(
            "Período 2",
            options=period_labels,
            index=_default_idx_2,
            key="tempo_p2",
        )
        p2_idx   = period_labels.index(sel_p2)
        p2_year, p2_month = periods[p2_idx]
    else:
        st.selectbox("Período 2", options=["(sem dados)"], disabled=True, key="tempo_p2")
        p2_year, p2_month = None, None

st.markdown("")

# ── 3 gráficos de pizza ───────────────────────────────────────────────────────
c1, c2, c3 = st.columns(3)

# ── Coluna 1: Total Acumulado (histórico + InMeta) ────────────────────────────
with c1:
    total_dias = sum(v for k, v in counts_total.items() if k != "OUTRO")
    fig1 = _make_pie(counts_total, "Total Acumulado", "dias")
    st.plotly_chart(fig1, use_container_width=True, config=_PLOTLY_CFG)

    # Mini tabela de resumo
    hist_total = sum(hist.values())
    inmeta_total = len(diario_rows)
    st.markdown(
        f"""
        <div style="
            background:rgba(196,18,48,0.06);
            border-left:3px solid #C41230;
            border-radius:6px;
            padding:10px 14px;
            font-size:12px;
        ">
            <div style="font-weight:700;color:#C41230;margin-bottom:6px;">Composição</div>
            <div>📚 Histórico pré-InMeta: <b>{hist_total}</b> dias</div>
            <div>📡 InMeta Diário: <b>{inmeta_total}</b> dias</div>
            <div style="margin-top:6px;border-top:1px solid rgba(196,18,48,0.2);padding-top:6px;">
                <b>Total: {hist_total + inmeta_total}</b> dias registrados
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ── Coluna 2: Período 1 ───────────────────────────────────────────────────────
with c2:
    if p1_year is not None and diario_rows:
        rows_p1     = _filter_period(diario_rows, p1_year, p1_month)
        counts_p1   = _count(rows_p1)
        label_p1    = f"{MONTHS_PT[p1_month]}/{str(p1_year)[-2:]}"
        fig2        = _make_pie(counts_p1, f"Período 1 — {label_p1}", "dias")
        st.plotly_chart(fig2, use_container_width=True, config=_PLOTLY_CFG)

        total_p1 = len(rows_p1)
        lines = []
        for k in WEATHER_KEYS:
            m   = WEATHER_META[k]
            cnt = counts_p1.get(k, 0)
            pct = f"{cnt/total_p1*100:.0f}%" if total_p1 > 0 else "—"
            lines.append(
                f"<div>{m['icon']} {m['label']}: <b>{cnt}</b> dias ({pct})</div>"
            )
        st.markdown(
            f"""
            <div style="
                background:rgba(82,160,192,0.08);
                border-left:3px solid #82A0C0;
                border-radius:6px;
                padding:10px 14px;
                font-size:12px;
            ">
                <div style="font-weight:700;color:#4A7BB5;margin-bottom:6px;">{label_p1}</div>
                {''.join(lines)}
                <div style="margin-top:6px;border-top:1px solid rgba(82,160,192,0.2);padding-top:6px;">
                    <b>Total: {total_p1}</b> dias
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <div style="
                display:flex; align-items:center; justify-content:center;
                height:340px; background:rgba(0,0,0,0.04);
                border-radius:10px; border: 1px dashed #cccccc;
                flex-direction:column; gap:8px;
            ">
                <div style="font-size:36px;">📡</div>
                <div style="font-size:13px; color:#888888; text-align:center;">
                    Sem dados InMeta.<br>Clique em <b>Atualizar Diário</b>.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

# ── Coluna 3: Período 2 ───────────────────────────────────────────────────────
with c3:
    if p2_year is not None and diario_rows:
        rows_p2     = _filter_period(diario_rows, p2_year, p2_month)
        counts_p2   = _count(rows_p2)
        label_p2    = f"{MONTHS_PT[p2_month]}/{str(p2_year)[-2:]}"
        fig3        = _make_pie(counts_p2, f"Período 2 — {label_p2}", "dias")
        st.plotly_chart(fig3, use_container_width=True, config=_PLOTLY_CFG)

        total_p2 = len(rows_p2)
        lines = []
        for k in WEATHER_KEYS:
            m   = WEATHER_META[k]
            cnt = counts_p2.get(k, 0)
            pct = f"{cnt/total_p2*100:.0f}%" if total_p2 > 0 else "—"
            lines.append(
                f"<div>{m['icon']} {m['label']}: <b>{cnt}</b> dias ({pct})</div>"
            )
        st.markdown(
            f"""
            <div style="
                background:rgba(246,166,35,0.08);
                border-left:3px solid #F6A623;
                border-radius:6px;
                padding:10px 14px;
                font-size:12px;
            ">
                <div style="font-weight:700;color:#D48B10;margin-bottom:6px;">{label_p2}</div>
                {''.join(lines)}
                <div style="margin-top:6px;border-top:1px solid rgba(246,166,35,0.2);padding-top:6px;">
                    <b>Total: {total_p2}</b> dias
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <div style="
                display:flex; align-items:center; justify-content:center;
                height:340px; background:rgba(0,0,0,0.04);
                border-radius:10px; border: 1px dashed #cccccc;
                flex-direction:column; gap:8px;
            ">
                <div style="font-size:36px;">📡</div>
                <div style="font-size:13px; color:#888888; text-align:center;">
                    Sem dados InMeta.<br>Clique em <b>Atualizar Diário</b>.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

# ── Seção: Histórico mensal InMeta ────────────────────────────────────────────
if diario_rows and periods:
    st.divider()
    st.markdown("#### 📊 Evolução Mensal — InMeta Diário")

    # Agrupa por mês
    monthly: list[dict] = []
    for year, month in periods:
        rows_m = _filter_period(diario_rows, year, month)
        c = _count(rows_m)
        monthly.append({
            "label":      f"{MONTHS_PT[month]}/{str(year)[-2:]}",
            "Ensolarado": c.get("ENSOLARADO", 0),
            "Nublado":    c.get("NUBLADO",    0),
            "Chuvoso":    c.get("CHUVOSO",    0),
            "Total":      len(rows_m),
        })

    df_monthly = pd.DataFrame(monthly)

    fig_bar = go.Figure()
    fig_bar.add_trace(go.Bar(
        name="☀️ Ensolarado",
        x=df_monthly["label"],
        y=df_monthly["Ensolarado"],
        marker_color="#F6A623",
        text=df_monthly["Ensolarado"],
        textposition="inside",
    ))
    fig_bar.add_trace(go.Bar(
        name="⛅ Nublado",
        x=df_monthly["label"],
        y=df_monthly["Nublado"],
        marker_color="#82A0C0",
        text=df_monthly["Nublado"],
        textposition="inside",
    ))
    fig_bar.add_trace(go.Bar(
        name="🌧️ Chuvoso",
        x=df_monthly["label"],
        y=df_monthly["Chuvoso"],
        marker_color="#4A7BB5",
        text=df_monthly["Chuvoso"],
        textposition="inside",
    ))

    fig_bar.update_layout(
        barmode="stack",
        height=300,
        margin=dict(t=20, b=10, l=10, r=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(tickangle=-30, tickfont=dict(size=11)),
        yaxis=dict(title="Dias"),
    )
    fig_bar.update_yaxes(gridcolor="rgba(0,0,0,0.08)")

    st.plotly_chart(fig_bar, use_container_width=True, config={
        **_PLOTLY_CFG,
        "toImageButtonOptions": {
            **_PLOTLY_CFG["toImageButtonOptions"],
            "filename": "tempo_mensal",
            "width": 1000,
        },
    })

    # Tabela mensal
    with st.expander("Ver tabela mensal"):
        st.dataframe(
            df_monthly.rename(columns={"label": "Mês/Ano"}),
            use_container_width=True,
            hide_index=True,
        )

# ── Nota de rodapé ────────────────────────────────────────────────────────────
st.markdown(
    """
    <div style="
        margin-top: 24px;
        padding: 10px 14px;
        background: rgba(0,0,0,0.03);
        border-radius: 6px;
        font-size: 11px;
        color: #888888;
    ">
        ℹ️ <b>Total Acumulado</b> = registros históricos (pré-InMeta) + dados InMeta Diário de Obra.
        Os gráficos de pizza suportam download de imagem via o ícone 📷 na barra do gráfico.
    </div>
    """,
    unsafe_allow_html=True,
)
