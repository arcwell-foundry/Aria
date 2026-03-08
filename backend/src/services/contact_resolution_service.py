"""Contact Resolution Service.

Implements a cascade resolution strategy to find the best contacts for a given company:
1. discovered_leads - contacts from lead discovery
2. email_scan_log - senders at the company domain
3. memory_semantic - future enhancement (not implemented yet)

This service is used by the action_executor to resolve recipients when
processing deferred actions where recipients were not initially specified.
"""

from __future__ import annotations

import logging

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)

# Maximum number of contacts to return
MAX_CONTACTS = 3


class ContactResolutionService:
    """Service for resolving contacts by company name using a cascade strategy."""

    def __init__(self) -> None:
        """Initialize the contact resolution service."""
        self._supabase = SupabaseClient.get_client()

    async def resolve_contacts(
        self,
        user_id: str,
        company_name: str,
        industry_hint: str | None = None,
    ) -> list[dict[str, str]]:
        """Resolve contacts for a company using the cascade resolution strategy.

        Args:
            user_id: The user ID to search contacts for.
            company_name: The company name to search for.
            industry_hint: Optional industry hint for future semantic search enhancement.

        Returns:
            List of contact dictionaries with 'name' and 'email' keys.
            Maximum of 3 contacts returned.
        """
        contacts: list[dict[str, str]] = []
        seen_emails: set[str] = set()

        # Step 1: Try discovered_leads table
        lead_contacts = await self._resolve_from_discovered_leads(
            user_id, company_name, seen_emails
        )
        if lead_contacts:
            logger.info(
                "ContactResolution: Found %d contacts from discovered_leads for company '%s'",
                len(lead_contacts),
                company_name,
            )
            contacts.extend(lead_contacts)
            seen_emails.update(c.get("email", "").lower() for c in lead_contacts)

        # Step 2: If we still need more contacts, try email_scan_log
        if len(contacts) < MAX_CONTACTS:
            email_contacts = await self._resolve_from_email_scan_log(
                user_id, company_name, seen_emails
            )
            if email_contacts:
                logger.info(
                    "ContactResolution: Found %d contacts from email_scan_log for company '%s'",
                    len(email_contacts),
                    company_name,
                )
                contacts.extend(email_contacts)
                seen_emails.update(c.get("email", "").lower() for c in email_contacts)

        # Step 3: memory_semantic - Future enhancement
        # TODO: Implement semantic search for contact resolution
        # This would search memory_semantic for person/company associations
        # and could use the industry_hint for better matching

        # Limit to MAX_CONTACTS
        contacts = contacts[:MAX_CONTACTS]

        if not contacts:
            logger.warning(
                "ContactResolution: No contacts found for company '%s' (user_id=%s)",
                company_name,
                user_id,
            )
        else:
            logger.info(
                "ContactResolution: Resolved %d contact(s) for company '%s'",
                len(contacts),
                company_name,
            )

        return contacts

    async def _resolve_from_discovered_leads(
        self,
        user_id: str,
        company_name: str,
        seen_emails: set[str],
    ) -> list[dict[str, str]]:
        """Resolve contacts from the discovered_leads table.

        Query for matching contacts by company name (case-insensitive partial match).

        Args:
            user_id: The user ID to search for.
            company_name: The company name to search for.
            seen_emails: Set of emails already found (for deduplication).

        Returns:
            List of contact dictionaries with 'name' and 'email' keys.
        """
        contacts: list[dict[str, str]] = []

        try:
            # Query discovered_leads for matching company name
            # Using ILIKE for case-insensitive partial matching
            response = (
                self._supabase.table("discovered_leads")
                .select("company_name, contacts")
                .eq("user_id", user_id)
                .ilike("company_name", f"%{company_name}%")
                .limit(5)
                .execute()
            )

            if not response.data:
                logger.debug(
                    "ContactResolution: No discovered_leads found for company '%s'",
                    company_name,
                )
                return contacts

            # Extract contacts from the contacts JSONB column
            for row in response.data:
                row_contacts = row.get("contacts", [])
                if not isinstance(row_contacts, list):
                    continue

                for contact in row_contacts:
                    if not isinstance(contact, dict):
                        continue

                    email = contact.get("email", "")
                    if not email or email.lower() in seen_emails:
                        continue

                    name = contact.get("name", "") or contact.get("full_name", "")
                    if not name:
                        # Try to construct name from parts
                        first = contact.get("first_name", "")
                        last = contact.get("last_name", "")
                        if first or last:
                            name = f"{first} {last}".strip()

                    contacts.append({
                        "name": name or email.split("@")[0],
                        "email": email,
                    })

                    if len(contacts) >= MAX_CONTACTS:
                        return contacts

        except Exception as e:
            logger.warning(
                "ContactResolution: Error querying discovered_leads for company '%s': %s",
                company_name,
                e,
            )

        return contacts

    async def _resolve_from_email_scan_log(
        self,
        user_id: str,
        company_name: str,
        seen_emails: set[str],
    ) -> list[dict[str, str]]:
        """Resolve contacts from the email_scan_log table.

        Query for senders at the company domain extracted from sender_email.

        Args:
            user_id: The user ID to search for.
            company_name: The company name to derive domain from.
            seen_emails: Set of emails already found (for deduplication).

        Returns:
            List of contact dictionaries with 'name' and 'email' keys.
        """
        contacts: list[dict[str, str]] = []

        try:
            # Extract potential domain from company name
            # Convert company name to potential domain patterns
            domain_patterns = self._extract_domain_patterns(company_name)

            if not domain_patterns:
                logger.debug(
                    "ContactResolution: Could not extract domain patterns from company '%s'",
                    company_name,
                )
                return contacts

            # Query email_scan_log for senders matching any domain pattern
            # Build OR conditions for each domain pattern
            for domain in domain_patterns:
                if len(contacts) >= MAX_CONTACTS:
                    break

                response = (
                    self._supabase.table("email_scan_log")
                    .select("sender_name, sender_email")
                    .eq("user_id", user_id)
                    .ilike("sender_email", f"%{domain}%")
                    .limit(10)
                    .execute()
                )

                if not response.data:
                    continue

                logger.debug(
                    "ContactResolution: Found %d senders in email_scan_log matching domain '%s'",
                    len(response.data),
                    domain,
                )

                for row in response.data:
                    email = row.get("sender_email", "")
                    if not email or email.lower() in seen_emails:
                        continue

                    name = row.get("sender_name", "") or email.split("@")[0]

                    contacts.append({
                        "name": name,
                        "email": email,
                    })
                    seen_emails.add(email.lower())

                    if len(contacts) >= MAX_CONTACTS:
                        break

        except Exception as e:
            logger.warning(
                "ContactResolution: Error querying email_scan_log for company '%s': %s",
                company_name,
                e,
            )

        return contacts

    def _extract_domain_patterns(self, company_name: str) -> list[str]:
        """Extract potential domain patterns from a company name.

        This method attempts to derive likely email domains from a company name.
        For example, "Acme Corporation" might yield ["acme.com", "acmecorp.com"].

        Args:
            company_name: The company name to extract domains from.

        Returns:
            List of potential domain patterns to search for.
        """
        patterns: list[str] = []

        if not company_name:
            return patterns

        # Clean the company name
        name = company_name.lower().strip()

        # Remove common suffixes
        suffixes = [
            "inc", "inc.", "corp", "corp.", "corporation", "llc", "l.l.c.",
            "ltd", "ltd.", "limited", "co", "co.", "company",
            "group", "holdings", "partners", "solutions", "services",
            "technologies", "technology", "systems", "software",
        ]

        base_name = name
        for suffix in suffixes:
            if base_name.endswith(f" {suffix}"):
                base_name = base_name[: -len(f" {suffix}")]
            elif base_name.endswith(suffix):
                base_name = base_name[: -len(suffix)]

        base_name = base_name.strip()

        # Generate potential domains
        # 1. Just the base name (e.g., "acme" from "Acme Corporation")
        if base_name:
            patterns.append(f"@{base_name.replace(' ', '')}.com")

            # 2. First word only (e.g., "acme" from "Acme Tech Solutions")
            words = base_name.split()
            if len(words) > 1:
                patterns.append(f"@{words[0]}.com")

            # 3. Abbreviation from first letters of words
            if len(words) > 1:
                abbr = "".join(w[0] for w in words if w)
                if len(abbr) >= 2:
                    patterns.append(f"@{abbr}.com")

        # Also try the original name without spaces
        original_no_spaces = name.replace(" ", "").replace("-", "").replace(".", "")
        if original_no_spaces and len(original_no_spaces) > 2:
            patterns.append(f"@{original_no_spaces}.com")

        return list(set(patterns))  # Deduplicate
