"""Seed aria_knowledge table from aria_capabilities.yaml.

Reads the YAML single source of truth and upserts rows into the
aria_knowledge table so ARIA can query her own capabilities at runtime
(for chat responses, deck generation, prospect conversations, etc.).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_YAML_PATH = Path(__file__).resolve().parent.parent / "core" / "aria_capabilities.yaml"


def _load_yaml() -> dict[str, Any]:
    """Load and parse aria_capabilities.yaml.

    Returns:
        Parsed YAML as a dict.

    Raises:
        FileNotFoundError: If the YAML file is missing.
        yaml.YAMLError: If the YAML is malformed.
    """
    with open(_YAML_PATH) as f:
        return yaml.safe_load(f)


def _build_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert parsed YAML into flat rows for aria_knowledge.

    Categories: identity, agent, capability, integration, does_not_do.

    Args:
        data: Parsed YAML dict.

    Returns:
        List of dicts ready for upsert.
    """
    rows: list[dict[str, Any]] = []

    # Identity
    identity = data.get("identity", {})
    for key, value in identity.items():
        rows.append({
            "category": "identity",
            "name": key,
            "description": str(value).strip(),
            "metadata": json.dumps({}),
        })

    # Agents
    agents = data.get("agents", {})
    for agent_name, agent_info in agents.items():
        rows.append({
            "category": "agent",
            "name": agent_name,
            "description": agent_info.get("description", ""),
            "metadata": json.dumps({}),
        })

    # Capabilities
    capabilities = data.get("capabilities", [])
    for cap in capabilities:
        rows.append({
            "category": "capability",
            "name": cap.get("name", ""),
            "description": cap.get("description", ""),
            "metadata": json.dumps({}),
        })

    # Integrations
    integrations = data.get("integrations", [])
    for integration in integrations:
        rows.append({
            "category": "integration",
            "name": str(integration),
            "description": f"Connected integration: {integration}",
            "metadata": json.dumps({}),
        })

    # Does not do
    does_not_do = data.get("does_not_do", [])
    for idx, constraint in enumerate(does_not_do):
        rows.append({
            "category": "does_not_do",
            "name": f"constraint_{idx}",
            "description": str(constraint),
            "metadata": json.dumps({}),
        })

    return rows


async def seed_aria_knowledge() -> int:
    """Read aria_capabilities.yaml and upsert into aria_knowledge.

    Uses ON CONFLICT (category, name) DO UPDATE to keep rows current.

    Returns:
        Number of rows upserted.
    """
    from src.db.supabase import SupabaseClient

    data = _load_yaml()
    rows = _build_rows(data)

    if not rows:
        logger.warning("aria_capabilities.yaml produced 0 rows — skipping seed")
        return 0

    db = SupabaseClient.get_client()

    # Upsert in a single call — Supabase client supports on_conflict
    db.table("aria_knowledge").upsert(
        rows,
        on_conflict="category,name",
    ).execute()

    logger.info("aria_knowledge seeded: %d rows upserted", len(rows))
    return len(rows)
