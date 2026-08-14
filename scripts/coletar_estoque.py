"""
scripts/coletar_estoque.py
==========================
Coletor de ESTOQUE (movimentações de almoxarifado) do Sienge — base do módulo de
inteligência de estoque (Fase 1). Fonte ÚNICA: `inventory-movements`.

Cada movimentação tem direção (INPUT/OUTPUT), tipo (Compra/Consumo/Devolução/
Transferência), material (resourceId — a MESMA chave do módulo de compras),
quantidade na UNIDADE BASE (movementQuantity), valor unitário e fornecedor.

Reconstrói, por insumo:
  • saldo corrente  = Σ entradas − Σ saídas (unidade base)
  • consumo         = Σ saídas do tipo "Consumo"
  • consumo mensal  = {AAAA-MM: qtd}  (base p/ taxa de consumo e cobertura)
  • entradas/valor, fornecedores, primeira/última movimentação

NÃO cria segunda fonte de verdade: só espelha o que o Sienge registrou. O cálculo
de cobertura/ruptura fica no engine (custos/estoque.py), separado.

Saída: data/estoque_{project_id}.json

Executar (a partir de prevision_agent/):
    python scripts/coletar_estoque.py
    python scripts/coletar_estoque.py --obra 10223
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import httpx

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

sys.stdout.reconfigure(encoding="utf-8")

from rup.sienge_client import SiengeClient

DATA = _ROOT / "data"
# obra (prevision_id) -> buildingId do Sienge
OBRAS = {10223: {"nome": "Cape Town Residence", "building": 23},
         18992: {"nome": "Holmes Residence", "building": 13}}


def _movimentacoes(sng: SiengeClient, building: int) -> list[dict]:
    """Todas as movimentações da obra (paginado). Precisa do histórico completo
    para reconstruir o saldo corrente (entrada − saída desde o início)."""
    out: list[dict] = []
    offset = 0
    while True:
        for tent in range(4):
            try:
                r = sng.get("inventory-movements", params={
                    "buildingId": building, "limit": 200, "offset": offset})
                if r.status_code >= 500:
                    time.sleep(1.5 * (tent + 1)); continue
                r.raise_for_status()
                break
            except (httpx.TransportError, httpx.TimeoutException):
                time.sleep(1.5 * (tent + 1))
        else:
            print(f"    falha persistente no offset {offset} — parando", flush=True)
            break
        body = r.json()
        res = body.get("results", []) if isinstance(body, dict) else []
        out.extend(res)
        total = body.get("resultSetMetadata", {}).get("count", 0)
        offset += 200
        if not res or offset >= total:
            break
        if offset % 2000 == 0:
            print(f"    {offset}/{total} movimentações", flush=True)
    return out


def _agregar(movs: list[dict]) -> dict:
    """Consolida por resourceId. movementQuantity já vem na unidade BASE."""
    ins: dict = {}
    consumo_mes: dict = defaultdict(lambda: defaultdict(float))
    for m in movs:
        rid = m.get("resourceId")
        if rid is None:
            continue
        rid = str(rid)
        q = float(m.get("movementQuantity") or 0)
        val = float(m.get("movementValue") or 0)
        io = m.get("inputOutput")
        tipo = m.get("movementTypeDescription") or ""
        data = (m.get("movementDate") or "")[:10]
        base_un = m.get("baseUnitOfMeasureSymbol") or m.get("unitOfMeasureSymbol") or ""

        d = ins.get(rid)
        if d is None:
            d = ins[rid] = {
                "resource_id": rid, "descricao": m.get("resourceDescription"),
                "unidade_base": base_un, "entrada_qtd": 0.0, "saida_qtd": 0.0,
                "consumo_qtd": 0.0, "valor_entrada": 0.0, "n_movs": 0,
                "primeiro_mov": data, "ultimo_mov": data, "ultimo_consumo": "",
                "unidades_vistas": set(), "fornecedores": set()}
        d["n_movs"] += 1
        d["unidades_vistas"].add(base_un)
        if data:
            if not d["primeiro_mov"] or data < d["primeiro_mov"]:
                d["primeiro_mov"] = data
            if data > d["ultimo_mov"]:
                d["ultimo_mov"] = data
        if io == "INPUT":
            d["entrada_qtd"] += q
            d["valor_entrada"] += q * val
            if m.get("supplierId"):
                d["fornecedores"].add(m["supplierId"])
        else:  # OUTPUT
            d["saida_qtd"] += q
        if "consumo" in tipo.lower():
            d["consumo_qtd"] += q
            if data:
                consumo_mes[rid][data[:7]] += q
                if data > d["ultimo_consumo"]:
                    d["ultimo_consumo"] = data

    # finaliza: saldo, sets -> contagem/lista, consumo mensal
    for rid, d in ins.items():
        d["saldo"] = round(d["entrada_qtd"] - d["saida_qtd"], 3)
        d["entrada_qtd"] = round(d["entrada_qtd"], 3)
        d["saida_qtd"] = round(d["saida_qtd"], 3)
        d["consumo_qtd"] = round(d["consumo_qtd"], 3)
        d["valor_entrada"] = round(d["valor_entrada"], 2)
        d["n_fornecedores"] = len(d["fornecedores"])
        # flag de qualidade: mais de uma unidade base para o mesmo insumo
        d["unidade_inconsistente"] = len(d["unidades_vistas"]) > 1
        d.pop("fornecedores"); d.pop("unidades_vistas")
        d["consumo_mensal"] = {k: round(v, 3) for k, v in sorted(consumo_mes[rid].items())}
    return ins


def coletar(pid: int) -> dict:
    sng = SiengeClient()
    building = OBRAS[pid]["building"]
    movs = _movimentacoes(sng, building)
    print(f"  {len(movs)} movimentações", flush=True)
    insumos = _agregar(movs)
    neg = sum(1 for d in insumos.values() if d["saldo"] < -0.001)
    print(f"  {len(insumos)} insumos · {neg} com saldo negativo (alerta de dado)", flush=True)
    from datetime import datetime, timezone
    return {"obra": OBRAS[pid]["nome"], "building_id": building,
            "coletado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "insumos": insumos}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--obra", type=int, choices=list(OBRAS), default=None)
    args = ap.parse_args()
    alvos = [args.obra] if args.obra else list(OBRAS)
    for pid in alvos:
        print(f"\n{OBRAS[pid]['nome']} (building {OBRAS[pid]['building']})")
        dados = coletar(pid)
        out = DATA / f"estoque_{pid}.json"
        out.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
        val = sum(d["valor_entrada"] for d in dados["insumos"].values())
        print(f"  → {len(dados['insumos'])} insumos · R$ {val:,.0f} em entradas · {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
