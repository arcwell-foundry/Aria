#!/usr/bin/env python
"""Setup script for ARIA Tavus persona.

Creates the ARIA persona and guardrails in Tavus if they don't exist.
Updates .env file with the persona and guardrails IDs.

Usage:
    python scripts/setup_tavus_persona.py        # Create if not exists
    python scripts/setup_tavus_persona.py --force  # Recreate even if exists
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# Add backend to path for imports
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path / "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def validate_environment() -> bool:
    """Validate required environment variables.

    Returns:
        True if all required variables are set.
    """
    required = [
        "TAVUS_API_KEY",
        "TAVUS_REPLICA_ID",
        "ANTHROPIC_API_KEY",
    ]

    missing = []
    for var in required:
        if not os.environ.get(var):
            missing.append(var)

    if missing:
        logger.error("Missing required environment variables: %s", ", ".join(missing))
        logger.error("Please set these in your .env file or environment.")
        return False

    return True


def update_env_file(persona_id: str, guardrails_id: str) -> bool:
    """Update .env file with persona and guardrails IDs.

    Args:
        persona_id: The created persona ID.
        guardrails_id: The created guardrails ID.

    Returns:
        True if successful.
    """
    env_path = backend_path / ".env"

    # Read existing .env
    env_lines = []
    if env_path.exists():
        with open(env_path) as f:
            env_lines = f.readlines()

    # Update or add the IDs
    updated_persona = False
    updated_guardrails = False
    new_lines = []

    for line in env_lines:
        if line.startswith("TAVUS_PERSONA_ID="):
            new_lines.append(f"TAVUS_PERSONA_ID={persona_id}\n")
            updated_persona = True
        elif line.startswith("TAVUS_GUARDRAILS_ID="):
            new_lines.append(f"TAVUS_GUARDRAILS_ID={guardrails_id}\n")
            updated_guardrails = True
        else:
            new_lines.append(line)

    # Add if not found
    if not updated_persona:
        new_lines.append(f"TAVUS_PERSONA_ID={persona_id}\n")
    if not updated_guardrails:
        new_lines.append(f"TAVUS_GUARDRAILS_ID={guardrails_id}\n")

    # Write back
    with open(env_path, "w") as f:
        f.writelines(new_lines)

    logger.info("Updated .env file with persona and guardrails IDs")
    return True


async def setup_persona(force_recreate: bool = False) -> int:
    """Setup ARIA persona in Tavus.

    Args:
        force_recreate: If True, delete and recreate even if exists.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    if not validate_environment():
        return 1

    try:
        from src.integrations.tavus_persona import get_aria_persona_manager

        logger.info("Starting ARIA persona setup...")

        manager = get_aria_persona_manager()

        result = await manager.get_or_create_persona(force_recreate=force_recreate)

        persona_id = result.get("persona_id")
        guardrails_id = result.get("guardrails_id")
        created = result.get("created", False)

        if created:
            logger.info("Created new ARIA persona: %s", persona_id)
            logger.info("Created guardrails: %s", guardrails_id)
        else:
            logger.info("Found existing ARIA persona: %s", persona_id)

        # Update .env file
        if persona_id and guardrails_id:
            update_env_file(persona_id, guardrails_id)

        # Verify by fetching the persona
        logger.info("Verifying persona...")
        persona_details = await manager.tavus_client.get_persona(persona_id)
        logger.info(
            "Persona verified: %s",
            persona_details.get("persona_name", "Unknown"),
        )

        print("\n" + "=" * 50)
        print("ARIA Tavus Persona Setup Complete")
        print("=" * 50)
        print(f"Persona ID:    {persona_id}")
        print(f"Guardrails ID: {guardrails_id}")
        print(f"Status:        {'Created' if created else 'Existing'}")
        print("\n.env file has been updated with these IDs.")
        print("=" * 50 + "\n")

        return 0

    except Exception as e:
        logger.exception("Failed to setup ARIA persona: %s", e)
        return 1


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Setup ARIA persona in Tavus",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/setup_tavus_persona.py         # Create if not exists
    python scripts/setup_tavus_persona.py --force # Recreate even if exists

Environment Variables Required:
    TAVUS_API_KEY       - Your Tavus API key
    TAVUS_REPLICA_ID    - Your Phoenix-4 replica ID
    ANTHROPIC_API_KEY   - Your Anthropic API key for Claude LLM
        """,
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force recreation of persona even if it exists",
    )

    args = parser.parse_args()

    return asyncio.run(setup_persona(force_recreate=args.force))


if __name__ == "__main__":
    sys.exit(main())
