"""
Design System do FVS Dashboard — R21 Empreendimentos.

Fonte unica de verdade para cores, tipografia, espacamentos e componentes
reutilizaveis de UI. Todas as paginas importam daqui para garantir uma
identidade visual consistente.

Uso tipico numa pagina:

    from fvs_dashboard.ui import theme as ui

    ui.page_header("Backlog FVS", eyebrow=obra,
                   subtitle="Pacotes liberados x status de cada FVS")
    ui.section("Filtros")
    st.markdown(ui.kpi("Pacotes Liberados", "149"), unsafe_allow_html=True)
"""

from fvs_dashboard.ui import theme  # noqa: F401
