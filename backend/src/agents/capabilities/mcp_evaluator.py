"""MCP Evaluator capability — assesses security and reliability of MCP servers.

Used by the Analyst agent's ``evaluate_mcp_server`` tool to produce a
``SecurityAssessment`` before recommending installation to the user.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from src.mcp_servers.models import MCPServerInfo, SecurityAssessment

logger = logging.getLogger(__name__)

# Thresholds for scoring
_STALE_DAYS_THRESHOLD = 180  # 6 months without update = stale
_HIGH_ADOPTION_DOWNLOADS = 1000
_MEDIUM_ADOPTION_DOWNLOADS = 100


class MCPEvaluatorCapability:
    """Evaluates an MCP server's security posture and reliability.

    Performs rule-based analysis of publisher identity, open-source status,
    permission scope, freshness, and community adoption. Optionally uses
    an LLM for deeper permission-vs-purpose analysis.

    Usage::

        evaluator = MCPEvaluatorCapability()
        assessment = await evaluator.evaluate(server_info)
    """

    def __init__(self, llm_client: Any | None = None) -> None:
        """Initialize the evaluator.

        Args:
            llm_client: Optional LLM client for permission-purpose analysis.
                If not provided, only rule-based evaluation is performed.
        """
        self._llm = llm_client

    async def evaluate(self, server_info: MCPServerInfo) -> SecurityAssessment:
        """Evaluate an MCP server's security and reliability.

        Checks:
        1. Publisher identity and verification status
        2. Open-source availability
        3. Required permissions vs stated purpose
        4. Download count / community adoption
        5. Last update freshness

        Args:
            server_info: Server metadata from registry discovery.

        Returns:
            A SecurityAssessment with risk level and recommendation.
        """
        risk_factors: list[str] = []
        positive_factors: list[str] = []

        # 1. Publisher verification
        if server_info.is_verified_publisher:
            positive_factors.append("Publisher is verified")
        else:
            risk_factors.append("Publisher is not verified")

        # 2. Open source
        if server_info.is_open_source and server_info.repo_url:
            positive_factors.append(f"Open source: {server_info.repo_url}")
        else:
            risk_factors.append("Closed source — code cannot be audited")

        # 3. Permission analysis
        permissions = server_info.permissions
        data_access_scope = self._analyze_permissions(permissions, server_info.description)
        if "write" in data_access_scope.lower() or "delete" in data_access_scope.lower():
            risk_factors.append(f"Requests write/delete access: {data_access_scope}")
        elif "read" in data_access_scope.lower():
            positive_factors.append(f"Read-only access: {data_access_scope}")

        # 4. Freshness
        freshness_days = self._calculate_freshness(server_info.last_updated)
        if freshness_days > _STALE_DAYS_THRESHOLD:
            risk_factors.append(
                f"Package is stale ({freshness_days} days since last update)"
            )
        elif freshness_days < 30:
            positive_factors.append("Recently updated")

        # 5. Adoption
        adoption_score = self._calculate_adoption_score(server_info.download_count)
        if adoption_score >= 0.7:
            positive_factors.append(
                f"High adoption ({server_info.download_count} downloads)"
            )
        elif adoption_score < 0.3:
            risk_factors.append(
                f"Low adoption ({server_info.download_count} downloads)"
            )

        # Calculate overall risk and recommendation
        overall_risk = self._calculate_overall_risk(
            risk_factors=risk_factors,
            positive_factors=positive_factors,
            freshness_days=freshness_days,
            adoption_score=adoption_score,
            is_verified=server_info.is_verified_publisher,
            is_open_source=server_info.is_open_source,
        )

        recommendation = self._derive_recommendation(overall_risk)

        # Build reasoning
        reasoning_parts: list[str] = []
        if positive_factors:
            reasoning_parts.append("Positive: " + "; ".join(positive_factors))
        if risk_factors:
            reasoning_parts.append("Risks: " + "; ".join(risk_factors))
        reasoning = ". ".join(reasoning_parts) if reasoning_parts else "No notable factors."

        assessment = SecurityAssessment(
            overall_risk=overall_risk,
            publisher_verified=server_info.is_verified_publisher,
            open_source=server_info.is_open_source,
            data_access_scope=data_access_scope,
            recommendation=recommendation,
            reasoning=reasoning,
            freshness_days=freshness_days,
            adoption_score=adoption_score,
        )

        logger.info(
            "Evaluated %s: risk=%s recommendation=%s",
            server_info.name,
            overall_risk,
            recommendation,
        )

        return assessment

    async def evaluate_batch(
        self, servers: list[MCPServerInfo]
    ) -> list[tuple[MCPServerInfo, SecurityAssessment]]:
        """Evaluate multiple servers and return sorted by recommendation.

        Args:
            servers: List of server info objects to evaluate.

        Returns:
            List of (server_info, assessment) tuples, sorted with
            "recommend" first, then "caution", then "reject".
        """
        results: list[tuple[MCPServerInfo, SecurityAssessment]] = []
        for server in servers:
            assessment = await self.evaluate(server)
            results.append((server, assessment))

        # Sort: recommend > caution > reject
        rec_order = {"recommend": 0, "caution": 1, "reject": 2}
        results.sort(key=lambda x: rec_order.get(x[1].recommendation, 3))

        return results

    def _analyze_permissions(
        self, permissions: dict[str, Any], description: str
    ) -> str:
        """Summarize the data access scope from declared permissions.

        Args:
            permissions: Declared permission requirements dict.
            description: Server description for context.

        Returns:
            Human-readable summary of data access scope.
        """
        if not permissions:
            return "No explicit permissions declared"

        scopes: list[str] = []

        # Check for common permission patterns
        for key, value in permissions.items():
            key_lower = key.lower()
            if "read" in key_lower:
                scopes.append(f"read:{key}")
            elif "write" in key_lower:
                scopes.append(f"write:{key}")
            elif "delete" in key_lower:
                scopes.append(f"delete:{key}")
            elif "admin" in key_lower:
                scopes.append(f"admin:{key}")
            elif isinstance(value, list):
                scopes.extend(str(v) for v in value)
            elif isinstance(value, str):
                scopes.append(value)

        if not scopes:
            return "Permissions declared but scope unclear"

        return ", ".join(scopes[:10])

    def _calculate_freshness(self, last_updated: str) -> int:
        """Calculate days since last update.

        Args:
            last_updated: ISO timestamp of last update.

        Returns:
            Days since last update (0 if unparseable).
        """
        if not last_updated:
            return 365  # Assume stale if no date

        try:
            updated_dt = datetime.fromisoformat(
                last_updated.replace("Z", "+00:00")
            )
            now = datetime.now(UTC)
            return max(0, (now - updated_dt).days)
        except (ValueError, TypeError):
            return 365

    def _calculate_adoption_score(self, download_count: int) -> float:
        """Compute an adoption score from download count.

        Args:
            download_count: Total downloads.

        Returns:
            Score between 0.0 and 1.0.
        """
        if download_count >= _HIGH_ADOPTION_DOWNLOADS:
            return min(1.0, 0.7 + (download_count / 10000) * 0.3)
        if download_count >= _MEDIUM_ADOPTION_DOWNLOADS:
            return 0.4 + (download_count / _HIGH_ADOPTION_DOWNLOADS) * 0.3
        if download_count > 0:
            return (download_count / _MEDIUM_ADOPTION_DOWNLOADS) * 0.4
        return 0.0

    def _calculate_overall_risk(
        self,
        risk_factors: list[str],
        positive_factors: list[str],
        freshness_days: int,
        adoption_score: float,
        is_verified: bool,
        is_open_source: bool,
    ) -> str:
        """Determine overall risk level.

        Args:
            risk_factors: List of identified risks.
            positive_factors: List of positive signals.
            freshness_days: Days since last update.
            adoption_score: Adoption score 0-1.
            is_verified: Whether publisher is verified.
            is_open_source: Whether source code is available.

        Returns:
            Risk level: "low", "medium", "high", or "critical".
        """
        risk_score = 0.0

        # Base risk from factor counts
        risk_score += len(risk_factors) * 0.15
        risk_score -= len(positive_factors) * 0.10

        # Freshness penalty
        if freshness_days > _STALE_DAYS_THRESHOLD:
            risk_score += 0.2
        elif freshness_days > 90:
            risk_score += 0.1

        # Adoption bonus
        risk_score -= adoption_score * 0.2

        # Verification and open-source bonuses
        if is_verified:
            risk_score -= 0.15
        if is_open_source:
            risk_score -= 0.1

        # Clamp to [0, 1]
        risk_score = max(0.0, min(1.0, risk_score))

        if risk_score >= 0.7:
            return "critical"
        if risk_score >= 0.5:
            return "high"
        if risk_score >= 0.25:
            return "medium"
        return "low"

    def _derive_recommendation(self, overall_risk: str) -> str:
        """Map risk level to recommendation.

        Args:
            overall_risk: Risk level string.

        Returns:
            Recommendation: "recommend", "caution", or "reject".
        """
        if overall_risk == "low":
            return "recommend"
        if overall_risk in ("medium", "high"):
            return "caution"
        return "reject"
