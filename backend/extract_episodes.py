#!/usr/bin/env python3
"""Script to call the extract-missing episodes endpoint.

Usage:
    python extract_episodes.py <email> <password>

Example:
    python extract_episodes.py user@example.com mypassword
"""

import asyncio
import os
import sys
from dotenv import load_dotenv
from supabase import create_client
import httpx

load_dotenv()


async def main():
    # Get credentials from command line args or env
    if len(sys.argv) >= 3:
        test_email = sys.argv[1]
        test_password = sys.argv[2]
    else:
        test_email = os.getenv("TEST_USER_EMAIL")
        test_password = os.getenv("TEST_USER_PASSWORD")

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_ANON_KEY")

    if not supabase_url or not supabase_key:
        print("ERROR: SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env")
        return

    if not test_email or not test_password:
        print("Usage: python extract_episodes.py <email> <password>")
        print("       Or set TEST_USER_EMAIL and TEST_USER_PASSWORD in .env")
        return

    # Create Supabase client and sign in
    supabase = create_client(supabase_url, supabase_key)

    try:
        auth_response = supabase.auth.sign_in_with_password({
            "email": test_email,
            "password": test_password,
        })
    except Exception as e:
        print(f"ERROR: Failed to sign in: {e}")
        return

    access_token = auth_response.session.access_token
    user_id = auth_response.user.id
    print(f"Signed in as: {auth_response.user.email} (id={user_id})")

    # Call the extract-missing endpoint
    api_url = "http://localhost:8000/api/v1/memory/episodes/extract-missing"

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            api_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
        )

        print(f"\nStatus: {response.status_code}")
        print(f"Response: {response.json()}")

    # Now verify the episodes were created
    print("\n--- Checking conversation_episodes table ---")

    # Query the episodes table directly
    episodes = (
        supabase.table("conversation_episodes")
        .select("conversation_id, summary, key_topics, created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )

    if episodes.data:
        print(f"Found {len(episodes.data)} episodes:")
        for ep in episodes.data:
            print(f"\n  Conversation: {ep['conversation_id']}")
            print(f"  Summary: {ep['summary'][:100]}..." if len(ep.get("summary", "")) > 100 else f"  Summary: {ep.get('summary', 'N/A')}")
            print(f"  Topics: {ep.get('key_topics', [])}")
    else:
        print("No episodes found in conversation_episodes table.")


if __name__ == "__main__":
    asyncio.run(main())
