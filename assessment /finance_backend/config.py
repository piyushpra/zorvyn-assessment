from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import os


@dataclass(frozen=True)
class Settings:
    database_path: str
    host: str
    port: int
    debug: bool
    seed_demo_data: bool


def _as_bool(value: Optional[str], default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> Settings:
    base_dir = Path.cwd()
    return Settings(
        database_path=os.getenv("FINANCE_DB_PATH", str(base_dir / "finance.db")),
        host=os.getenv("FINANCE_HOST", "127.0.0.1"),
        port=int(os.getenv("FINANCE_PORT", "8000")),
        debug=_as_bool(os.getenv("FINANCE_DEBUG"), False),
        seed_demo_data=_as_bool(os.getenv("FINANCE_SEED_DEMO_DATA"), True),
    )
