"""
scripts/coletar_desembolso.py
=============================
Coletor de DESEMBOLSO (títulos a pagar + parcelas) do Sienge — base da previsão
de desembolso (Fase 3). Cada título (bill) tem fornecedor e vínculo ao pedido de
compra; cada parcela (installment) tem VENCIMENTO (dueDate), valor e situação.

Atribuição à obra pelo CENTRO DE CUSTO (sondado: Cape Town 20009/20014,
Holmes 20012/20017). Só o dado REAL agendado — a projeção estatística do
não-comprado entra no motor de previsão, separada.

Saída: data/desembolso_{project_id}.json
    { parcelas: [{data_venc, valor, situacao, fornecedor_id, bill_id}] }

Executar (com SIENGE_* no ambiente):
    python scripts/coletar_desembolso.py --desde 2025-06-01
"""
from __future__ import annotations

import argparse
import json
import sys
import time
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
CACHE = DATA / "raw" / "bill_installments"
# obra (prevision_id) -> centro de custo do Sienge (= id do "Custo de Obra")
CENTROS = {10223: [23], 18992: [13]}
OBRA_NOME = {10223: "Cape Town Residence", 18992: "Holmes Residence"}


def _janelas_anuais(desde: str, ate: str):
    """Quebra [desde, ate] em janelas de ≤1 ano (o filtro de bills limita o range)."""
    from datetime import date, timedelta
    d0 = date.fromisoformat(desde)
    d1 = date.fromisoformat(ate)
    while d0 < d1:
        fim = min(d1, date(d0.year + 1, d0.month, d0.day) - timedelta(days=1))
        yield d0.isoformat(), fim.isoformat()
        d0 = fim + timedelta(days=1)


def _bills(sng: SiengeClient, cc: int, desde: str, ate: str) -> list[dict]:
    out = []
    for jd, ja in _janelas_anuais(desde, ate):
        offset = 0
        while True:
            try:
                body = sng.get_json("bills", params={
                    "costCenterId": cc, "startDate": jd, "endDate": ja,
                    "limit": 200, "offset": offset})
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    break  # janela sem títulos (ex.: emissão futura)
                raise
            res = body.get("results", []) if isinstance(body, dict) else []
            out.extend(res)
            total = body.get("resultSetMetadata", {}).get("count", 0)
            offset += 200
            if not res or offset >= total:
                break
    return out


def _installments(sng: SiengeClient, bill_id) -> list[dict]:
    f = CACHE / f"{bill_id}.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass  # cache vazio/corrompido (Drive) — re-busca abaixo
    for tent in range(4):
        try:
            body = sng.get_json(f"bills/{bill_id}/installments")
            res = body.get("results", []) if isinstance(body, dict) else []
            try:
                f.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
            except OSError:
                pass  # Google Drive às vezes recusa a escrita (Errno 22) — segue sem cachear
            return res
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500:
                time.sleep(1.5 * (tent + 1)); continue
            return []
        except (httpx.TransportError, httpx.TimeoutException):
            time.sleep(1.5 * (tent + 1))
    return []


def coletar(pid: int, desde: str, ate: str) -> list[dict]:
    sng = SiengeClient()
    bills, vistos = [], set()
    for cc in CENTROS[pid]:
        for b in _bills(sng, cc, desde, ate):
            if b["id"] not in vistos:
                vistos.add(b["id"]); bills.append(b)
    print(f"  {len(bills)} títulos", flush=True)

    parcelas = []
    for i, b in enumerate(bills, 1):
        for p in _installments(sng, b["id"]):
            parcelas.append({
                "bill_id": b["id"], "fornecedor_id": b.get("creditorId"),
                "doc_tipo": (b.get("documentIdentificationId") or "").strip(),
                "data_venc": (p.get("dueDate") or "")[:10],
                "valor": float(p.get("amount") or 0),
                "situacao": p.get("situation"),
                "parcela": p.get("installmentNumber"),
            })
        if i % 200 == 0 or i == len(bills):
            print(f"    {i}/{len(bills)} títulos · {len(parcelas)} parcelas", flush=True)
    return parcelas


def main() -> int:
    from datetime import date
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", default="2025-01-01")
    # filtro de bills é por EMISSÃO → não faz sentido ir além de hoje
    ap.add_argument("--ate", default=date.today().isoformat())
    args = ap.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    for pid, ccs in CENTROS.items():
        print(f"\n{OBRA_NOME[pid]} (centros {ccs})")
        parcelas = coletar(pid, args.desde, args.ate)
        out = DATA / f"desembolso_{pid}.json"
        out.write_text(json.dumps({"obra": OBRA_NOME[pid], "parcelas": parcelas},
                                  ensure_ascii=False), encoding="utf-8")
        apagar = sum(p["valor"] for p in parcelas if "paga" not in (p["situacao"] or "").lower())
        print(f"  → {len(parcelas)} parcelas · R$ {apagar:,.0f} a pagar · {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
