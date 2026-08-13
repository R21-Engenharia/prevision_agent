"""
scripts/coletar_compras.py
==========================
Coletor de COMPRAS (pedidos de compra + itens) do Sienge — base do módulo de
Inteligência de Custos. Cada item de PO traz o insumo (resourceId/description),
unidade, quantidade, preço unitário; o PO traz fornecedor e data. Isso dá o
HISTÓRICO DE PREÇO e CONSUMO por insumo.

Itens só saem por PO (não há endpoint em lote), então cacheia por PO em disco
(data/raw/po_items/{id}.json) — rerun fica barato. Resiliente a 5xx.

Saída: data/compras_{project_id}.json — por insumo (resourceId):
    { total_qtd, total_valor, unidade, descricao, n_compras,
      preco: {primeiro, ultimo, min, max, medio, medio_ponderado},
      historico: [{data, pu, qtd, fornecedor_id}], fornecedores: [...] }

Executar (a partir de prevision_agent/), com SIENGE_* no ambiente:
    python scripts/coletar_compras.py
    python scripts/coletar_compras.py --obra "Cape Town Residence" --desde 2025-01-01
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

from fvs_dashboard.core.data_manager import OBRAS
from rup.sienge_client import SiengeClient

DATA = _ROOT / "data"
CACHE = DATA / "raw" / "po_items"


def _pos_do_building(sng: SiengeClient, bid: int, desde: str | None) -> list[dict]:
    pos, offset = [], 0
    params = {"buildingId": bid, "limit": 200}
    if desde:
        params["startDate"], params["endDate"] = desde, "2100-01-01"
    while True:
        params["offset"] = offset
        body = sng.get_json("purchase-orders", params=params)
        res = body.get("results", []) if isinstance(body, dict) else []
        pos.extend(res)
        total = body.get("resultSetMetadata", {}).get("count", 0)
        offset += 200
        if not res or offset >= total:
            break
    return pos


def _itens_do_po(sng: SiengeClient, po_id, refresh: bool) -> list[dict]:
    f = CACHE / f"{po_id}.json"
    if f.exists() and not refresh:
        return json.loads(f.read_text(encoding="utf-8"))
    for tent in range(4):
        try:
            body = sng.get_json(f"purchase-orders/{po_id}/items")
            itens = body.get("results", []) if isinstance(body, dict) else []
            f.write_text(json.dumps(itens, ensure_ascii=False), encoding="utf-8")
            return itens
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500:
                time.sleep(1.5 * (tent + 1)); continue
            return []
        except (httpx.TransportError, httpx.TimeoutException):
            time.sleep(1.5 * (tent + 1))
    return []


def coletar(obra: str, cfg: dict, desde: str | None, refresh: bool) -> dict:
    sng = SiengeClient()
    bid = cfg["sienge_building_id"]
    pos = _pos_do_building(sng, bid, desde)
    print(f"  {len(pos)} pedidos de compra", flush=True)

    ins: dict[int, dict] = defaultdict(lambda: {
        "descricao": "", "unidade": None, "total_qtd": 0.0, "total_valor": 0.0,
        "historico": [], "fornecedores": set()})
    for i, po in enumerate(pos, 1):
        data_po = (po.get("date") or "")[:10]
        forn = po.get("supplierId")
        for it in _itens_do_po(sng, po["id"], refresh):
            rid = it.get("resourceId")
            if rid is None:
                continue
            qtd = float(it.get("quantity") or 0)
            pu = float(it.get("unitPrice") or it.get("netPrice") or 0)
            if qtd <= 0 or pu <= 0:
                continue
            g = ins[rid]
            g["descricao"] = it.get("resourceDescription") or g["descricao"]
            g["unidade"] = it.get("unitOfMeasure") or g["unidade"]
            g["total_qtd"] += qtd
            g["total_valor"] += qtd * pu
            g["historico"].append({"data": data_po, "pu": round(pu, 4),
                                   "qtd": qtd, "fornecedor_id": forn})
            if forn:
                g["fornecedores"].add(forn)
        if i % 200 == 0 or i == len(pos):
            print(f"    {i}/{len(pos)} POs · {len(ins)} insumos", flush=True)

    # consolida preço por insumo
    saida = {}
    for rid, g in ins.items():
        hist = sorted(g["historico"], key=lambda h: h["data"])
        pus = [h["pu"] for h in hist]
        # média ponderada pela quantidade
        sq = sum(h["qtd"] for h in hist)
        mp = sum(h["pu"] * h["qtd"] for h in hist) / sq if sq else 0
        saida[str(rid)] = {
            "resource_id": rid, "descricao": g["descricao"], "unidade": g["unidade"],
            "total_qtd": round(g["total_qtd"], 3), "total_valor": round(g["total_valor"], 2),
            "n_compras": len(hist),
            "preco": {"primeiro": pus[0], "ultimo": pus[-1], "min": min(pus),
                      "max": max(pus), "medio": round(sum(pus) / len(pus), 4),
                      "medio_ponderado": round(mp, 4)},
            "fornecedores": sorted(g["fornecedores"]),
            "historico": hist,
        }
    return saida


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--obra")
    ap.add_argument("--desde", help="data mínima do PO (YYYY-MM-DD)")
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    CACHE.mkdir(parents=True, exist_ok=True)
    obras = [args.obra] if args.obra else list(OBRAS)
    for obra in obras:
        cfg = OBRAS[obra]
        print(f"\n{obra} (Sienge building {cfg['sienge_building_id']})")
        saida = coletar(obra, cfg, args.desde, args.refresh)
        out = DATA / f"compras_{cfg['prevision_id']}.json"
        out.write_text(json.dumps({"obra": obra, "insumos": saida},
                                  ensure_ascii=False), encoding="utf-8")
        val = sum(v["total_valor"] for v in saida.values())
        print(f"  → {len(saida)} insumos · R$ {val:,.0f} comprado · {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
