from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _string(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass(frozen=True)
class Settings:
    database_url: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        database_url=_string("DATABASE_URL"),
    )
