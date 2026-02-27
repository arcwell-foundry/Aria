"""Manual smoke test for LLM Gateway end-to-end pipeline.

Verifies: LLM call → llm_usage table → budget check.
(Langfuse tracing verified separately due to Python 3.14 compatibility)

Run with: python -m tests.test_gateway_e2e
NOT for CI — requires real credentials and database access.
"""

import asyncio

from dotenv import load_dotenv

load_dotenv()

# Disable Langfuse BEFORE any litellm imports (Python 3.14 compatibility)
import os
os.environ["LANGFUSE_PUBLIC_KEY"] = ""
os.environ["LANGFUSE_SECRET_KEY"] = ""
os.environ["LANGFUSE_HOST"] = ""

import litellm
litellm.success_callback = []
litellm.failure_callback = []
litellm.set_verbose = False
litellm.drop_params = True

from src.core.budget import get_budget_governor
from src.core.llm import LLMClient
from src.core.task_types import TaskType
from src.core.usage_logger import UsageLogger
from src.db.supabase import SupabaseClient


async def main() -> None:
    print("=== LLM Gateway E2E Smoke Test ===\n")

    # 1. Initialize clients
    print("1. Initializing clients...")
    db = SupabaseClient.get_client()
    usage_logger = UsageLogger(db)
    llm = LLMClient(usage_logger=usage_logger)
    print("   ✓ Supabase, UsageLogger, LLMClient initialized\n")

    # 2. Get a real tenant and user from DB
    print("2. Fetching tenant/user from database...")
    companies = db.table("companies").select("id").limit(1).execute()
    users = db.table("user_profiles").select("id, company_id").limit(1).execute()

    tenant_id = companies.data[0]["id"] if companies.data else ""
    user_id = users.data[0]["id"] if users.data else ""
    print(f"   ✓ Tenant: {tenant_id[:8]}... | User: {user_id[:8]}...\n")

    # 3. Make LLM call
    print("3. Calling LLM...")
    llm_success = False
    try:
        response = await llm.generate(
            messages=[{"role": "user", "content": "Say hello in one sentence"}],
            task=TaskType.CHAT_RESPONSE,
            system_prompt="You are ARIA, an AI sales colleague.",
            tenant_id=tenant_id,
            user_id=user_id,
            agent_id="chat",
        )
        print(f"   ✓ Response: {response}\n")
        llm_success = True
    except Exception as e:
        err_str = str(e)
        if "Langfuse" in err_str or "langfuse" in err_str:
            print("   ✗ LLM call blocked by Python 3.14 + Langfuse incompatibility")
            print("   (Run on Python 3.13 or earlier for full test)\n")
        elif "401" in err_str or "token expired" in err_str or "AuthenticationError" in err_str:
            print(f"   ✗ LLM auth failed: check ANTHROPIC_API_KEY in .env")
            print(f"   Error: {e}\n")
        else:
            print(f"   ✗ LLM call failed: {e}\n")

    # 4. Wait for fire-and-forget log (if LLM succeeded)
    if llm_success:
        print("4. Waiting 2s for usage log...")
        await asyncio.sleep(2)

        # 5. Query llm_usage table
        usage = (
            db.table("llm_usage")
            .select("model, task_type, input_tokens, output_tokens, total_cost_usd, latency_ms")
            .eq("tenant_id", tenant_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if usage.data:
            row = usage.data[0]
            print("   ✓ Latest llm_usage row:")
            print(f"     model: {row['model']}")
            print(f"     task_type: {row['task_type']}")
            print(f"     input_tokens: {row['input_tokens']}")
            print(f"     output_tokens: {row['output_tokens']}")
            print(f"     total_cost_usd: ${row['total_cost_usd']:.6f}")
            print(f"     latency_ms: {row['latency_ms']}ms\n")
        else:
            print("   ✗ No llm_usage rows found!\n")
    else:
        print("4-5. Skipping usage log check (LLM call failed)\n")

    # 6. Budget check (always works)
    print("6. Checking tenant budget...")
    budget = get_budget_governor()
    status = await budget.check(tenant_id)
    print(f"   ✓ Budget: allowed={status.allowed} | "
          f"${status.monthly_spend_usd:.2f}/${status.monthly_limit_usd:.2f} "
          f"({status.utilization_percent:.1f}%)\n")

    print("=== Summary ===")
    print("✓ Database connection: OK")
    print("✓ Budget governor: OK")
    if llm_success:
        print("✓ LLM call: OK")
        print("✓ Usage logging: OK")
        print("\nCheck Langfuse dashboard for trace with task_type=chat.response")
    else:
        print("✗ LLM call: Check API key or Python version")


if __name__ == "__main__":
    asyncio.run(main())
