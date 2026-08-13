"""
custos/normalizar.py
====================
Normalização de insumo → GRUPO ECONÔMICO, para análise (ABC por grupo, tendência
por família) sem destruir o dado original. Cada insumo mantém código/descrição
originais; o grupo é uma camada por cima.

Regras por palavra-chave na descrição (determinístico, auditável). "outros"
quando nada bate — nunca força equivalência onde não existe (regra do brief).
"""
from __future__ import annotations

import re
import unicodedata

# grupo econômico -> palavras-chave (ordem importa: mais específico primeiro)
_GRUPOS: list[tuple[str, list[str]]] = [
    ("Concreto", ["concreto usinado", "concreto fck", "concreto bombeado", "concreto "]),
    ("Argamassa", ["argamassa", "graute"]),
    ("Aço/Armadura", ["vergalhao", "aco ca", "aco nervurado", "tela soldada", "arame"]),
    ("Cimento/Cal", ["cimento", " cal ", "cal hidratada"]),
    ("Areia/Brita/Agregado", ["areia", "brita", "pedrisco", "agregado", "mistura (areia"]),
    ("Bloco/Tijolo", ["bloco ceramico", "bloco de concreto", "tijolo", "bloco estrutural"]),
    ("Cerâmica/Porcelanato", ["porcelanato", "azulejo", "ceramica", "revestimento ceramico",
                              "piso ", "pastilha", "rejunte"]),
    ("Gesso/Drywall", ["gesso", "drywall", "placa st", "placa ru"]),
    ("Cabo/Fio elétrico", ["cabo flexivel", "cabo de cobre", "fio ", "cabo "]),
    ("Eletroduto/Elétrica", ["eletroduto", "disjuntor", "quadro", "tomada", "interruptor",
                             "eletrica", "conduite"]),
    ("Tubo/Conexão hidráulica", ["tubo", "conexao", "joelho", "tê ", "luva", "registro",
                                 "pvc", "cpvc", "ppr"]),
    ("Tinta/Pintura", ["tinta", "massa corrida", "selador", "textura", "verniz", "primer"]),
    ("Impermeabilizante", ["impermeabil", "manta asfaltica", "asfalto"]),
    ("Esquadria/Vidro", ["esquadria", "janela", "porta", "vidro", "aluminio", "batente"]),
    ("Louças/Metais", ["louca", "vaso sanitario", "cuba", "torneira", "metal sanitario", "ducha"]),
    ("Madeira/Forma", ["madeirite", "compensado", "sarrafo", "tabua", "escora", "madeira"]),
    ("Impermeab./Aditivo", ["aditivo", "desmoldante"]),
    ("EPI/Segurança", ["botina", "capacete", "oculos de protecao", "protetor auricular",
                       "cinto de seguranca", "mascara", "luva de seguranca", "luva nitrilica",
                       "colete refletivo", "bota de borracha"]),
    ("Fixação/Ferragem", ["prego", "parafuso", "bucha", "arruela", "porca ", "abracadeira"]),
    ("Ferramenta/Consumível", ["disco de corte", "disco de desbaste", "broca", "lixa",
                               "eletrodo", "serra", "trena", "disco diamantado"]),
    ("Vedação/Química", ["silicone", "espuma expansiva", "cola ", "adesivo", "veda"]),
]


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return " " + re.sub(r"[^a-z0-9 ]", " ", s.lower()) + " "


def grupo_de(descricao: str) -> str:
    n = _norm(descricao)
    for grupo, chaves in _GRUPOS:
        if any(f" {c.strip()}" in n or c in n for c in chaves):
            return grupo
    return "Outros"
