"""Local-only integration settings. Lives next to the program, never committed."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FILENAME = "integrations.json"
EXAMPLE = "integrations.example.json"

DEFAULTS: dict[str, Any] = {
    "broker": "yahoo",
    "symbol": "SPY",
    "expiration": "",
    "auto_fetch": True,
    "polygon_api_key": "",
    "tradier_token": "",
    "tradier_endpoint": "https://api.tradier.com/v1",
}


def integrations_path(app_dir: Path) -> Path:
    return app_dir / FILENAME


def load_integrations(app_dir: Path) -> dict[str, Any]:
    data = dict(DEFAULTS)
    path = integrations_path(app_dir)
    if path.exists():
        try:
            raw = json.loads(path.read_text())
            if isinstance(raw, dict):
                data.update({k: raw[k] for k in raw if k in DEFAULTS or k.endswith("_key") or k.endswith("_token")})
        except (OSError, json.JSONDecodeError):
            pass
    return data


def save_integrations(app_dir: Path, data: dict[str, Any]) -> Path:
    path = integrations_path(app_dir)
    clean = dict(DEFAULTS)
    clean.update({k: v for k, v in data.items() if v is not None})
    path.write_text(json.dumps(clean, indent=2) + "\n")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def setup_wizard(app_dir: Path) -> dict[str, Any]:
    current = load_integrations(app_dir)
    print("Local integrations (saved only in this folder)")
    print(f"File: {integrations_path(app_dir)}")
    print("Leave blank to keep the current value.\n")

    def ask(label: str, key: str, secret: bool = False) -> None:
        shown = current.get(key) or ""
        mask = ("*" * min(8, len(str(shown)))) if secret and shown else shown
        raw = input(f"{label} [{mask}]: ").strip()
        if raw:
            current[key] = raw

    ask("Broker  yahoo / polygon / tradier / file", "broker")
    ask("Symbol", "symbol")
    ask("Expiration YYYY-MM-DD or empty for nearest", "expiration")
    fetch = input(f"Auto-fetch tape on start? [{'Y' if current.get('auto_fetch') else 'n'}]: ").strip().lower()
    if fetch in ("y", "yes"):
        current["auto_fetch"] = True
    elif fetch in ("n", "no"):
        current["auto_fetch"] = False
    ask("Polygon API key", "polygon_api_key", secret=True)
    ask("Tradier token", "tradier_token", secret=True)
    path = save_integrations(app_dir, current)
    print(f"\nSaved {path}")
    print("This file stays on this computer. Do not email or commit it.")
    return current
