"""Lead memory graph module for knowledge graph operations.

Stores lead memories as first-class nodes in Graphiti with typed relationships:
- OWNED_BY: Lead owned by a user
- CONTRIBUTED_BY: Users who contributed to the lead
- ABOUT_COMPANY: Links to company entity
- HAS_CONTACT: Stakeholder contacts
- HAS_COMMUNICATION: Email/meeting/call events
- HAS_SIGNAL: Market signals and insights
- SYNCED_TO: CRM synchronization link

Enables cross-lead queries and pattern detection.
"""

import contextlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from src.core.exceptions import LeadMemoryGraphError, LeadMemoryNotFoundError
from src.memory.audit import MemoryOperation, MemoryType, log_memory_operation

if TYPE_CHECKING:
    from graphiti_core import Graphiti

logger = logging.getLogger(__name__)


class LeadRelationshipType(Enum):
    """Types of relationships between lead memory nodes."""

    OWNED_BY = "OWNED_BY"  # Lead -> User (owner)
    CONTRIBUTED_BY = "CONTRIBUTED_BY"  # Lead -> User (contributor)
    ABOUT_COMPANY = "ABOUT_COMPANY"  # Lead -> Company
    HAS_CONTACT = "HAS_CONTACT"  # Lead -> Contact/Stakeholder
    HAS_COMMUNICATION = "HAS_COMMUNICATION"  # Lead -> Event (email/meeting/call)
    HAS_SIGNAL = "HAS_SIGNAL"  # Lead -> Signal/Insight
    SYNCED_TO = "SYNCED_TO"  # Lead -> CRM Record


@dataclass
class LeadMemoryNode:
    """A lead memory node for the knowledge graph.

    Represents a sales lead/opportunity/account with all its metadata.
    Stored in both Supabase (structured data) and Graphiti (relationships).
    """

    id: str
    user_id: str
    company_name: str
    lifecycle_stage: str  # lead, opportunity, account
    status: str  # active, won, lost, dormant
    health_score: int
    created_at: datetime
    company_id: str | None = None
    crm_id: str | None = None
    crm_provider: str | None = None
    first_touch_at: datetime | None = None
    last_activity_at: datetime | None = None
    expected_close_date: str | None = None  # ISO date string
    expected_value: float | None = None
    tags: list[str] = field(default_factory=list)
    updated_at: datetime | None = None
    graphiti_node_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize node to dictionary for storage.

        Returns:
            Dictionary suitable for database insertion.
        """
        return {
            "id": self.id,
            "user_id": self.user_id,
            "company_name": self.company_name,
            "company_id": self.company_id,
            "lifecycle_stage": self.lifecycle_stage,
            "status": self.status,
            "health_score": self.health_score,
            "crm_id": self.crm_id,
            "crm_provider": self.crm_provider,
            "first_touch_at": self.first_touch_at.isoformat() if self.first_touch_at else None,
            "last_activity_at": self.last_activity_at.isoformat()
            if self.last_activity_at
            else None,
            "expected_close_date": self.expected_close_date,
            "expected_value": self.expected_value,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "graphiti_node_id": self.graphiti_node_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LeadMemoryNode":
        """Create a LeadMemoryNode from a dictionary.

        Args:
            data: Dictionary from database query.

        Returns:
            LeadMemoryNode instance.
        """
        return cls(
            id=data["id"],
            user_id=data["user_id"],
            company_name=data["company_name"],
            company_id=data.get("company_id"),
            lifecycle_stage=data["lifecycle_stage"],
            status=data["status"],
            health_score=data["health_score"],
            crm_id=data.get("crm_id"),
            crm_provider=data.get("crm_provider"),
            first_touch_at=datetime.fromisoformat(data["first_touch_at"])
            if data.get("first_touch_at")
            else None,
            last_activity_at=datetime.fromisoformat(data["last_activity_at"])
            if data.get("last_activity_at")
            else None,
            expected_close_date=data.get("expected_close_date"),
            expected_value=data.get("expected_value"),
            tags=data.get("tags") or [],
            created_at=datetime.fromisoformat(data["created_at"])
            if isinstance(data.get("created_at"), str)
            else data.get("created_at") or datetime.now(UTC),
            updated_at=datetime.fromisoformat(data["updated_at"])
            if data.get("updated_at")
            else None,
            graphiti_node_id=data.get("graphiti_node_id"),
        )


class LeadMemoryGraph:
    """Service for managing lead memories in the knowledge graph.

    Provides methods for storing leads as Graphiti nodes with typed
    relationships, and querying across leads for patterns and insights.
    Uses both Supabase (metadata) and Graphiti (semantic content).
    """

    def _get_graphiti_node_name(self, lead_id: str) -> str:
        """Generate namespaced node name for Graphiti.

        Args:
            lead_id: The lead's UUID.

        Returns:
            Namespaced node name (e.g., "lead:lead-123").
        """
        return f"lead:{lead_id}"

    async def _get_graphiti_client(self) -> "Graphiti":
        """Get the Graphiti client instance.

        Returns:
            Initialized Graphiti client.

        Raises:
            LeadMemoryGraphError: If client initialization fails.
        """
        from src.db.graphiti import GraphitiClient

        try:
            return await GraphitiClient.get_instance()
        except Exception as e:
            raise LeadMemoryGraphError(f"Failed to get Graphiti client: {e}") from e

    def _build_lead_body(self, lead: LeadMemoryNode) -> str:
        """Build structured lead body for Graphiti storage.

        Args:
            lead: The LeadMemoryNode to serialize.

        Returns:
            Structured text representation with relationship markers.
        """
        parts = [
            f"Lead ID: {lead.id}",
            f"Company: {lead.company_name}",
            f"OWNED_BY: {lead.user_id}",
            f"Lifecycle Stage: {lead.lifecycle_stage}",
            f"Status: {lead.status}",
            f"Health Score: {lead.health_score}",
        ]

        if lead.company_id:
            parts.append(f"ABOUT_COMPANY: {lead.company_id}")

        if lead.crm_id:
            parts.append(f"SYNCED_TO: {lead.crm_provider}:{lead.crm_id}")

        if lead.expected_value:
            parts.append(f"Expected Value: {lead.expected_value}")

        if lead.tags:
            parts.append(f"Tags: {', '.join(lead.tags)}")

        return "\n".join(parts)

    def _parse_edge_to_lead(self, edge: Any, user_id: str) -> LeadMemoryNode | None:
        """Parse a Graphiti edge into a LeadMemoryNode.

        Args:
            edge: The Graphiti edge object.
            user_id: The expected user ID for ownership verification.

        Returns:
            LeadMemoryNode if parsing succeeds and matches user, None otherwise.
        """
        try:
            fact = getattr(edge, "fact", "")
            created_at = getattr(edge, "created_at", datetime.now(UTC))
            edge_name = getattr(edge, "name", "") or ""

            # Extract lead ID from name (format: lead:lead-id)
            if not edge_name.startswith("lead:"):
                return None

            lead_id = edge_name.replace("lead:", "")

            lead = self._parse_content_to_lead(
                lead_id=lead_id,
                content=fact,
                created_at=created_at if isinstance(created_at, datetime) else datetime.now(UTC),
            )

            # Verify ownership
            if lead and lead.user_id != user_id:
                return None

            return lead
        except Exception as e:
            logger.warning(f"Failed to parse edge to lead: {e}")
            return None

    def _parse_content_to_lead(
        self,
        lead_id: str,
        content: str,
        created_at: datetime,
    ) -> LeadMemoryNode | None:
        """Parse lead content string into LeadMemoryNode.

        Args:
            lead_id: The lead ID.
            content: The raw content string from Graphiti.
            created_at: When the lead was created.

        Returns:
            LeadMemoryNode if parsing succeeds, None otherwise.
        """
        try:
            lines = content.split("\n")
            user_id = ""
            company_name = ""
            company_id = None
            lifecycle_stage = "lead"
            status = "active"
            health_score = 50
            crm_id = None
            crm_provider = None
            expected_value = None
            tags: list[str] = []

            for line in lines:
                if line.startswith("OWNED_BY:"):
                    user_id = line.replace("OWNED_BY:", "").strip()
                elif line.startswith("Company:"):
                    company_name = line.replace("Company:", "").strip()
                elif line.startswith("ABOUT_COMPANY:"):
                    company_id = line.replace("ABOUT_COMPANY:", "").strip()
                elif line.startswith("Lifecycle Stage:"):
                    lifecycle_stage = line.replace("Lifecycle Stage:", "").strip()
                elif line.startswith("Status:"):
                    status = line.replace("Status:", "").strip()
                elif line.startswith("Health Score:"):
                    with contextlib.suppress(ValueError):
                        health_score = int(line.replace("Health Score:", "").strip())
                elif line.startswith("SYNCED_TO:"):
                    sync_info = line.replace("SYNCED_TO:", "").strip()
                    if ":" in sync_info:
                        crm_provider, crm_id = sync_info.split(":", 1)
                elif line.startswith("Expected Value:"):
                    with contextlib.suppress(ValueError):
                        expected_value = float(line.replace("Expected Value:", "").strip())
                elif line.startswith("Tags:"):
                    tags_str = line.replace("Tags:", "").strip()
                    tags = [t.strip() for t in tags_str.split(",") if t.strip()]

            if not user_id or not company_name:
                return None

            return LeadMemoryNode(
                id=lead_id,
                user_id=user_id,
                company_name=company_name,
                company_id=company_id,
                lifecycle_stage=lifecycle_stage,
                status=status,
                health_score=health_score,
                crm_id=crm_id,
                crm_provider=crm_provider,
                expected_value=expected_value,
                tags=tags,
                created_at=created_at,
            )
        except Exception as e:
            logger.warning(f"Failed to parse lead content: {e}")
            return None

    async def store_lead(self, lead: LeadMemoryNode) -> str:
        """Store a lead memory node in the knowledge graph.

        Args:
            lead: The lead memory node to store.

        Returns:
            The ID of the stored lead.

        Raises:
            LeadMemoryGraphError: If storage fails.
        """
        try:
            import uuid as uuid_module

            lead_id = lead.id if lead.id else str(uuid_module.uuid4())

            # Get Graphiti client
            client = await self._get_graphiti_client()

            # Build lead body with relationships
            lead_body = self._build_lead_body(lead)

            # Store in Graphiti
            from graphiti_core.nodes import EpisodeType

            await client.add_episode(
                name=self._get_graphiti_node_name(lead_id),
                episode_body=lead_body,
                source=EpisodeType.text,
                source_description=f"lead_memory:{lead.user_id}:{lead.lifecycle_stage}",
                reference_time=lead.created_at,
            )

            logger.info(
                "Stored lead memory in graph",
                extra={
                    "lead_id": lead_id,
                    "user_id": lead.user_id,
                    "company_name": lead.company_name,
                },
            )

            # Audit log
            await log_memory_operation(
                user_id=lead.user_id,
                operation=MemoryOperation.CREATE,
                memory_type=MemoryType.LEAD,
                memory_id=lead_id,
                metadata={"company_name": lead.company_name, "stage": lead.lifecycle_stage},
                suppress_errors=True,
            )

            return lead_id

        except LeadMemoryGraphError:
            raise
        except Exception as e:
            logger.exception("Failed to store lead in graph")
            raise LeadMemoryGraphError(f"Failed to store lead: {e}") from e

    async def get_lead(self, user_id: str, lead_id: str) -> LeadMemoryNode:
        """Retrieve a specific lead by ID.

        Args:
            user_id: The user who owns the lead.
            lead_id: The lead's UUID.

        Returns:
            The requested LeadMemoryNode.

        Raises:
            LeadMemoryNotFoundError: If lead doesn't exist.
            LeadMemoryGraphError: If retrieval fails.
        """
        try:
            client = await self._get_graphiti_client()

            # Query for specific lead by name
            query = """
            MATCH (e:Episode)
            WHERE e.name = $lead_name
            RETURN e
            """

            lead_name = self._get_graphiti_node_name(lead_id)

            result = await client.driver.execute_query(
                query,
                lead_name=lead_name,
            )

            records = result[0] if result else []

            if not records:
                raise LeadMemoryNotFoundError(lead_id)

            # Parse the node into a LeadMemoryNode
            node = records[0]["e"]
            content = getattr(node, "content", "") or node.get("content", "")
            created_at = getattr(node, "created_at", None) or node.get("created_at")

            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at)
            elif created_at is None:
                created_at = datetime.now(UTC)

            lead = self._parse_content_to_lead(
                lead_id=lead_id,
                content=content,
                created_at=created_at,
            )

            if lead is None:
                raise LeadMemoryNotFoundError(lead_id)

            # Verify ownership
            if lead.user_id != user_id:
                raise LeadMemoryNotFoundError(lead_id)

            return lead

        except LeadMemoryNotFoundError:
            raise
        except LeadMemoryGraphError:
            raise
        except Exception as e:
            logger.exception("Failed to get lead from graph", extra={"lead_id": lead_id})
            raise LeadMemoryGraphError(f"Failed to get lead: {e}") from e

    async def update_lead(self, lead: LeadMemoryNode) -> None:
        """Update an existing lead memory node.

        Args:
            lead: The lead with updated data.

        Raises:
            LeadMemoryNotFoundError: If lead doesn't exist.
            LeadMemoryGraphError: If update fails.
        """
        try:
            client = await self._get_graphiti_client()

            lead_name = self._get_graphiti_node_name(lead.id)
            query = """
            MATCH (e:Episode)
            WHERE e.name = $lead_name
            DETACH DELETE e
            RETURN count(e) as deleted
            """

            result = await client.driver.execute_query(
                query,
                lead_name=lead_name,
            )

            records = result[0] if result else []
            deleted_count = records[0]["deleted"] if records else 0

            if deleted_count == 0:
                raise LeadMemoryNotFoundError(lead.id)

            lead_body = self._build_lead_body(lead)

            from graphiti_core.nodes import EpisodeType

            await client.add_episode(
                name=lead_name,
                episode_body=lead_body,
                source=EpisodeType.text,
                source_description=f"lead_memory:{lead.user_id}:{lead.lifecycle_stage}:updated",
                reference_time=lead.updated_at or datetime.now(UTC),
            )

            logger.info(
                "Updated lead in graph",
                extra={"lead_id": lead.id, "user_id": lead.user_id},
            )

            await log_memory_operation(
                user_id=lead.user_id,
                operation=MemoryOperation.UPDATE,
                memory_type=MemoryType.LEAD,
                memory_id=lead.id,
                metadata={"stage": lead.lifecycle_stage, "status": lead.status},
                suppress_errors=True,
            )

        except LeadMemoryNotFoundError:
            raise
        except LeadMemoryGraphError:
            raise
        except Exception as e:
            logger.exception("Failed to update lead in graph")
            raise LeadMemoryGraphError(f"Failed to update lead: {e}") from e

    async def add_contact(
        self,
        lead_id: str,
        contact_email: str,
        contact_name: str | None = None,
        role: str | None = None,
        influence_level: int = 5,
    ) -> None:
        """Add a contact relationship to a lead.

        Args:
            lead_id: The lead's UUID.
            contact_email: Contact's email address.
            contact_name: Contact's name.
            role: Stakeholder role (decision_maker, influencer, etc.).
            influence_level: 1-10 influence score.

        Raises:
            LeadMemoryGraphError: If operation fails.
        """
        try:
            client = await self._get_graphiti_client()

            parts = [
                f"HAS_CONTACT: {lead_id}",
                f"Contact: {contact_email}",
            ]

            if contact_name:
                parts.append(f"Name: {contact_name}")

            if role:
                parts.append(f"Role: {role}")

            parts.append(f"Influence: {influence_level}")

            contact_body = "\n".join(parts)

            from graphiti_core.nodes import EpisodeType

            contact_id = contact_email.replace("@", "_at_").replace(".", "_")
            await client.add_episode(
                name=f"contact:{lead_id}:{contact_id}",
                episode_body=contact_body,
                source=EpisodeType.text,
                source_description=f"lead_contact:{lead_id}:{role or 'unknown'}",
                reference_time=datetime.now(UTC),
            )

            logger.info(
                "Added contact to lead",
                extra={"lead_id": lead_id, "contact_email": contact_email, "role": role},
            )

        except LeadMemoryGraphError:
            raise
        except Exception as e:
            logger.exception("Failed to add contact to lead")
            raise LeadMemoryGraphError(f"Failed to add contact: {e}") from e

    async def add_communication(
        self,
        lead_id: str,
        event_type: str,
        content: str,
        occurred_at: datetime,
        participants: list[str] | None = None,
    ) -> None:
        """Add a communication event to a lead.

        Args:
            lead_id: The lead's UUID.
            event_type: Type of communication (email, meeting, call).
            content: Summary of the communication.
            occurred_at: When the communication happened.
            participants: List of participant names/emails.

        Raises:
            LeadMemoryGraphError: If operation fails.
        """
        try:
            import uuid as uuid_module

            client = await self._get_graphiti_client()

            parts = [
                f"HAS_COMMUNICATION: {lead_id}",
                f"Event Type: {event_type}",
                f"Content: {content}",
                f"Occurred At: {occurred_at.isoformat()}",
            ]

            if participants:
                parts.append(f"Participants: {', '.join(participants)}")

            comm_body = "\n".join(parts)

            from graphiti_core.nodes import EpisodeType

            comm_id = str(uuid_module.uuid4())
            await client.add_episode(
                name=f"comm:{lead_id}:{comm_id}",
                episode_body=comm_body,
                source=EpisodeType.text,
                source_description=f"lead_communication:{lead_id}:{event_type}",
                reference_time=occurred_at,
            )

            logger.info(
                "Added communication to lead",
                extra={"lead_id": lead_id, "event_type": event_type},
            )

        except LeadMemoryGraphError:
            raise
        except Exception as e:
            logger.exception("Failed to add communication to lead")
            raise LeadMemoryGraphError(f"Failed to add communication: {e}") from e

    async def add_signal(
        self,
        lead_id: str,
        signal_type: str,
        content: str,
        confidence: float = 0.7,
    ) -> None:
        """Add a market signal or insight to a lead.

        Args:
            lead_id: The lead's UUID.
            signal_type: Type of signal (buying_signal, objection, etc.).
            content: Description of the signal.
            confidence: Confidence score 0-1.

        Raises:
            LeadMemoryGraphError: If operation fails.
        """
        try:
            import uuid as uuid_module

            client = await self._get_graphiti_client()

            parts = [
                f"HAS_SIGNAL: {lead_id}",
                f"Signal Type: {signal_type}",
                f"Content: {content}",
                f"Confidence: {confidence}",
                f"Detected At: {datetime.now(UTC).isoformat()}",
            ]

            signal_body = "\n".join(parts)

            from graphiti_core.nodes import EpisodeType

            signal_id = str(uuid_module.uuid4())
            await client.add_episode(
                name=f"signal:{lead_id}:{signal_id}",
                episode_body=signal_body,
                source=EpisodeType.text,
                source_description=f"lead_signal:{lead_id}:{signal_type}",
                reference_time=datetime.now(UTC),
            )

            logger.info(
                "Added signal to lead",
                extra={"lead_id": lead_id, "signal_type": signal_type, "confidence": confidence},
            )

        except LeadMemoryGraphError:
            raise
        except Exception as e:
            logger.exception("Failed to add signal to lead")
            raise LeadMemoryGraphError(f"Failed to add signal: {e}") from e

    async def search_leads(
        self,
        user_id: str,
        query: str,
        limit: int = 20,
    ) -> list[LeadMemoryNode]:
        """Search leads using semantic search.

        Args:
            user_id: The user whose leads to search.
            query: Natural language search query.
            limit: Maximum number of leads to return.

        Returns:
            List of matching leads.

        Raises:
            LeadMemoryGraphError: If search fails.
        """
        try:
            client = await self._get_graphiti_client()

            search_query = f"lead memory for user {user_id}: {query}"
            results = await client.search(search_query)

            leads = []
            for edge in results[:limit]:
                lead = self._parse_edge_to_lead(edge, user_id)
                if lead:
                    leads.append(lead)

            return leads

        except LeadMemoryGraphError:
            raise
        except Exception as e:
            logger.exception("Failed to search leads")
            raise LeadMemoryGraphError(f"Failed to search leads: {e}") from e

    async def find_leads_by_topic(
        self,
        user_id: str,
        topic: str,
        limit: int = 20,
    ) -> list[LeadMemoryNode]:
        """Find leads where a specific topic was discussed.

        Args:
            user_id: The user whose leads to search.
            topic: Topic to search for (e.g., "pricing", "implementation").
            limit: Maximum number of leads to return.

        Returns:
            List of leads where the topic was discussed.

        Raises:
            LeadMemoryGraphError: If query fails.
        """
        try:
            client = await self._get_graphiti_client()

            search_query = f"lead communication discussing {topic}"
            results = await client.search(search_query)

            lead_ids: set[str] = set()
            for edge in results:
                fact = getattr(edge, "fact", "")
                for line in fact.split("\n"):
                    if line.startswith("HAS_COMMUNICATION:"):
                        lead_id = line.replace("HAS_COMMUNICATION:", "").strip()
                        lead_ids.add(lead_id)
                        break

            leads = []
            for lead_id in list(lead_ids)[:limit]:
                try:
                    lead = await self.get_lead(user_id, lead_id)
                    leads.append(lead)
                except LeadMemoryNotFoundError:
                    continue

            return leads

        except LeadMemoryGraphError:
            raise
        except Exception as e:
            logger.exception("Failed to find leads by topic")
            raise LeadMemoryGraphError(f"Failed to find leads by topic: {e}") from e

    async def find_silent_leads(
        self,
        user_id: str,
        days_inactive: int = 14,
        limit: int = 20,
    ) -> list[LeadMemoryNode]:
        """Find leads that have gone silent (no recent activity).

        Args:
            user_id: The user whose leads to check.
            days_inactive: Number of days without activity to consider silent.
            limit: Maximum number of leads to return.

        Returns:
            List of leads with no recent activity.

        Raises:
            LeadMemoryGraphError: If query fails.
        """
        try:
            from datetime import timedelta

            client = await self._get_graphiti_client()
            cutoff_date = datetime.now(UTC) - timedelta(days=days_inactive)

            search_query = (
                f"lead memory for user {user_id} active status silent inactive no recent activity"
            )
            results = await client.search(search_query)

            leads = []
            for edge in results[: limit * 2]:
                lead = self._parse_edge_to_lead(edge, user_id)
                if (
                    lead
                    and lead.status == "active"
                    and (lead.last_activity_at is None or lead.last_activity_at < cutoff_date)
                ):
                    leads.append(lead)
                    if len(leads) >= limit:
                        break

            return leads

        except LeadMemoryGraphError:
            raise
        except Exception as e:
            logger.exception("Failed to find silent leads")
            raise LeadMemoryGraphError(f"Failed to find silent leads: {e}") from e

    async def get_leads_for_company(
        self,
        user_id: str,
        company_id: str,
        limit: int = 20,
    ) -> list[LeadMemoryNode]:
        """Get all leads associated with a company.

        Args:
            user_id: The user whose leads to search.
            company_id: The company's UUID.
            limit: Maximum number of leads to return.

        Returns:
            List of leads for the company.

        Raises:
            LeadMemoryGraphError: If query fails.
        """
        try:
            client = await self._get_graphiti_client()

            search_query = f"lead memory ABOUT_COMPANY {company_id} for user {user_id}"
            results = await client.search(search_query)

            leads = []
            for edge in results[:limit]:
                lead = self._parse_edge_to_lead(edge, user_id)
                if lead and lead.company_id == company_id:
                    leads.append(lead)

            return leads

        except LeadMemoryGraphError:
            raise
        except Exception as e:
            logger.exception("Failed to get leads for company")
            raise LeadMemoryGraphError(f"Failed to get leads for company: {e}") from e
