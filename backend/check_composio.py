"""Quick script to list all Composio auth configs and their toolkit slugs."""

import os
from dotenv import load_dotenv
from composio import Composio

load_dotenv()

api_key = os.getenv("COMPOSIO_API_KEY", "")
print(f"API key: {api_key[:8]}...{api_key[-4:]}")

client = Composio(api_key=api_key)

print("\n--- Listing ALL auth configs (no filter) ---\n")

result = client.client.auth_configs.list()

print(f"Total items: {len(result.items)}\n")

for i, item in enumerate(result.items):
    # Print all available attributes
    attrs = {k: v for k, v in vars(item).items() if not k.startswith("_")}
    print(f"[{i}] {attrs}")
    print()
