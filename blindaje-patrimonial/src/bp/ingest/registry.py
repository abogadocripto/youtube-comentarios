"""Registro de conectores y ejecución de la ingesta diaria."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from bp.config import Config
from bp.ingest.base import Connector, ConnectorRun
from bp.ingest.crypto import AlternativeMe, CoinGecko, Mempool, SoSoValueETF
from bp.ingest.official import ECBFx, FedH41, FiscalDataTGA, NYFed, TreasuryYields
from bp.models import RunContext
from bp.store.base import Store

DAILY_CONNECTORS: list[type[Connector]] = [CoinGecko, AlternativeMe, Mempool, TreasuryYields, NYFed, FiscalDataTGA, FedH41,
                                           ECBFx, SoSoValueETF]


def run_daily_ingest(ctx: RunContext, cfg: Config, store: Store, fixtures_dir: Path | None = None,
                     only: list[str] | None = None) -> list[ConnectorRun]:
    conns = [c(cfg, fixtures_dir) for c in DAILY_CONNECTORS if not only or c.id in only]
    with ThreadPoolExecutor(max_workers=6) as pool:
        return list(pool.map(lambda c: c.run(ctx, store), conns))
