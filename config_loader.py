from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_ROOT / "config.yaml"

DEFAULT_CONFIG: dict[str, Any] = {
    "growth_tickers": ["LUNR", "RKLB", "ASTS", "PL", "SPCE", "ACHR", "JOBY"],
    "mega_cap_tickers": ["NVDA", "TSLA", "GOOG", "AAPL"],
    "screening": {
        "price_history_period": "1y",
        "output_dir": "output",
    },
    "backtest": {
        "history_period": "2y",
        "cooldown_days": 10,
        "output_dir": "output",
    },
}


def deep_merge(defaults: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(defaults)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def normalize_tickers(value: Any, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return fallback

    tickers = []
    for item in value:
        if item is None:
            continue
        ticker = str(item).strip().upper()
        if ticker:
            tickers.append(ticker)
    return tickers or fallback


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    path = config_path or CONFIG_PATH
    if not path.exists():
        return deepcopy(DEFAULT_CONFIG)

    with path.open("r", encoding="utf-8") as file:
        loaded = yaml.safe_load(file) or {}

    if not isinstance(loaded, dict):
        return deepcopy(DEFAULT_CONFIG)

    config = deep_merge(DEFAULT_CONFIG, loaded)
    config["growth_tickers"] = normalize_tickers(
        config.get("growth_tickers"),
        DEFAULT_CONFIG["growth_tickers"],
    )
    config["mega_cap_tickers"] = normalize_tickers(
        config.get("mega_cap_tickers"),
        DEFAULT_CONFIG["mega_cap_tickers"],
    )
    return config


def output_dir_for(base_dir: Path, section: dict[str, Any]) -> Path:
    configured = str(section.get("output_dir", "output")).strip() or "output"
    output_dir = Path(configured)
    if output_dir.is_absolute():
        return output_dir
    return base_dir / output_dir
