"""
Roteamento de destinatários do relatório por obra.
===================================================
Cada obra vai para o e-mail da engenharia dela + os gestores (que recebem
todas). Editável aqui; sem depender de secret.
"""
from __future__ import annotations

# Gestores recebem o relatório de TODAS as obras.
GESTORES = [
    "rafael@r21empreendimentos.com",
    "elrik@r21empreendimentos.com",
]

# Engenharia específica de cada obra.
POR_OBRA = {
    "Holmes Residence": ["engenharia.hr@r21empreendimentos.com"],
    "Cape Town Residence": ["engenharia.ct@r21empreendimentos.com"],
}


def destinatarios(obra: str) -> list[str]:
    """E-mails que recebem o relatório da obra (engenharia da obra + gestores)."""
    lista = list(POR_OBRA.get(obra, [])) + GESTORES
    return list(dict.fromkeys(lista))   # remove duplicados preservando ordem
