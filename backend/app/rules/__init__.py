"""Human-editable rule files (YAML). Each engine records the version + hash of the rules it used."""

import hashlib
import json
from functools import lru_cache
from pathlib import Path

import yaml

RULES_DIR = Path(__file__).parent


@lru_cache
def load_rules(name: str) -> dict:
    with open(RULES_DIR / f"{name}.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def rules_hash(rules: dict) -> str:
    return hashlib.sha256(json.dumps(rules, sort_keys=True).encode()).hexdigest()[:16]
