import asyncio
import os
from src.core.llm import LLMClient
from src.core.task_types import TaskType

async def main():
    # Make sure env vars are loaded
    from dotenv import load_dotenv
    load_dotenv()

    llm = LLMClient()

    # Test 1: New generate() with full attribution
    print("Test 1: generate() with TaskType...")
    r1 = await llm.generate(
        task=TaskType.CHAT_RESPONSE,
        messages=[{"role": "user", "content": "Say hello in one sentence"}],
        system_prompt="You are ARIA, an AI sales colleague.",
        tenant_id="00000000-0000-0000-0000-000000000001",
        user_id="00000000-0000-0000-0000-000000000001",
        agent_id="chat",
    )
    print(f"  Response: {r1[:100]}")

    # Test 2: Old method (backward compat)
    print("Test 2: generate_response() backward compat...")
    r2 = await llm.generate_response(
        messages=[{"role": "user", "content": "Say goodbye in one sentence"}],
        system_prompt="You are ARIA.",
    )
    print(f"  Response: {r2[:100]}")

    print("\n✅ Both calls succeeded.")
    print("👉 Check https://us.cloud.langfuse.com for traces with task_type metadata")

asyncio.run(main())
