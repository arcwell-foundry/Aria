"""Custom exceptions for ARIA backend."""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Exception type → safe user-facing message mapping
_SAFE_MESSAGES: dict[str, str] = {
    "NotFoundError": "The requested resource was not found.",
    "AuthenticationError": "Authentication failed. Please log in again.",
    "AuthorizationError": "You do not have permission to perform this action.",
    "ValidationError": "The provided input is invalid. Please check and try again.",
    "ConflictError": "A conflict occurred. Please refresh and try again.",
    "DatabaseError": "A database error occurred. Please try again.",
    "ExternalServiceError": "An external service is temporarily unavailable.",
    "GraphitiConnectionError": "A service dependency is temporarily unavailable.",
    "CircuitBreakerOpen": "A service dependency is temporarily unavailable. Please try again in a moment.",
    "RateLimitError": "Too many requests. Please try again later.",
    "BillingError": "Billing service temporarily unavailable.",
    "SkillNotFoundError": "The requested skill was not found.",
    "SkillExecutionError": "Skill execution failed. Please try again.",
    "ComplianceError": "A compliance operation failed. Please try again.",
    "LeadMemoryError": "An error occurred processing lead data.",
    "InvalidStageTransitionError": "This stage transition is not allowed.",
    "ValueError": "The provided value is invalid.",
}

_DEFAULT_MESSAGE = "An error occurred. Please try again."


def sanitize_error(e: Exception) -> str:
    """Map an exception to a safe, user-facing error message.

    Logs the full exception details server-side but returns only
    a generic message suitable for HTTP responses. This prevents
    leaking internal implementation details, stack traces, or
    database schema information to clients.

    Args:
        e: The exception to sanitize.

    Returns:
        A safe, generic error message string.
    """
    # Walk the MRO to find the most specific matching type
    for cls in type(e).__mro__:
        safe_msg = _SAFE_MESSAGES.get(cls.__name__)
        if safe_msg:
            return safe_msg

    return _DEFAULT_MESSAGE


class ARIAException(Exception):
    """Base exception for all ARIA-specific errors."""

    def __init__(
        self,
        message: str,
        code: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize ARIA exception.

        Args:
            message: Human-readable error message.
            code: Machine-readable error code.
            status_code: HTTP status code.
            details: Additional error details.
        """
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class NotFoundError(ARIAException):
    """Resource not found error (404)."""

    def __init__(self, resource: str, resource_id: str | None = None) -> None:
        """Initialize not found error.

        Args:
            resource: Name of the resource that was not found.
            resource_id: Optional ID of the resource.
        """
        message = f"{resource} not found"
        if resource_id:
            message = f"{resource} with ID '{resource_id}' not found"
        super().__init__(
            message=message,
            code="NOT_FOUND",
            status_code=404,
            details={"resource": resource, "resource_id": resource_id},
        )


class AuthenticationError(ARIAException):
    """Authentication failed error (401)."""

    def __init__(self, message: str = "Authentication required") -> None:
        """Initialize authentication error.

        Args:
            message: Error message.
        """
        super().__init__(
            message=message,
            code="AUTHENTICATION_ERROR",
            status_code=401,
        )


class AuthorizationError(ARIAException):
    """Authorization/permission denied error (403)."""

    def __init__(self, message: str = "Permission denied") -> None:
        """Initialize authorization error.

        Args:
            message: Error message.
        """
        super().__init__(
            message=message,
            code="AUTHORIZATION_ERROR",
            status_code=403,
        )


class ValidationError(ARIAException):
    """Input validation error (400)."""

    def __init__(
        self, message: str, field: str | None = None, details: dict[str, Any] | None = None
    ) -> None:
        """Initialize validation error.

        Args:
            message: Error message.
            field: Name of the invalid field.
            details: Additional validation details.
        """
        error_details = details or {}
        if field:
            error_details["field"] = field
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=400,
            details=error_details,
        )


class ConflictError(ARIAException):
    """Resource conflict error (409)."""

    def __init__(self, message: str, resource: str | None = None) -> None:
        """Initialize conflict error.

        Args:
            message: Error message.
            resource: Name of the conflicting resource.
        """
        details = {}
        if resource:
            details["resource"] = resource
        super().__init__(
            message=message,
            code="CONFLICT",
            status_code=409,
            details=details,
        )


class DatabaseError(ARIAException):
    """Database operation error (500)."""

    def __init__(self, message: str = "A database error occurred") -> None:
        """Initialize database error.

        Args:
            message: Error message.
        """
        super().__init__(
            message=message,
            code="DATABASE_ERROR",
            status_code=500,
        )


class ExternalServiceError(ARIAException):
    """External service error (502)."""

    def __init__(self, service: str, message: str | None = None) -> None:
        """Initialize external service error.

        Args:
            service: Name of the external service.
            message: Optional error message.
        """
        error_message = message or f"Error communicating with {service}"
        super().__init__(
            message=error_message,
            code="EXTERNAL_SERVICE_ERROR",
            status_code=502,
            details={"service": service},
        )


class GraphitiConnectionError(ARIAException):
    """Neo4j/Graphiti connection error (503)."""

    def __init__(self, message: str = "Unknown error") -> None:
        """Initialize Graphiti connection error.

        Args:
            message: Error details.
        """
        super().__init__(
            message=f"Failed to connect to Neo4j: {message}",
            code="GRAPHITI_CONNECTION_ERROR",
            status_code=503,
        )


class WorkingMemoryError(ARIAException):
    """Working memory operation error (400).

    Note: Named WorkingMemoryError to avoid shadowing Python's built-in MemoryError.
    """

    def __init__(self, message: str = "Unknown error") -> None:
        """Initialize working memory error.

        Args:
            message: Error details.
        """
        super().__init__(
            message=f"Memory operation failed: {message}",
            code="WORKING_MEMORY_ERROR",
            status_code=400,
        )


class EpisodicMemoryError(ARIAException):
    """Episodic memory operation error (500).

    Used for failures when storing or retrieving episodes from Graphiti.
    """

    def __init__(self, message: str = "Unknown error") -> None:
        """Initialize episodic memory error.

        Args:
            message: Error details.
        """
        super().__init__(
            message=f"Episodic memory operation failed: {message}",
            code="EPISODIC_MEMORY_ERROR",
            status_code=500,
        )


class EpisodeNotFoundError(NotFoundError):
    """Episode not found error (404)."""

    def __init__(self, episode_id: str) -> None:
        """Initialize episode not found error.

        Args:
            episode_id: The ID of the episode that was not found.
        """
        super().__init__(resource="Episode", resource_id=episode_id)


class SemanticMemoryError(ARIAException):
    """Semantic memory operation error (500).

    Used for failures when storing or retrieving facts from Graphiti.
    """

    def __init__(self, message: str = "Unknown error") -> None:
        """Initialize semantic memory error.

        Args:
            message: Error details.
        """
        super().__init__(
            message=f"Semantic memory operation failed: {message}",
            code="SEMANTIC_MEMORY_ERROR",
            status_code=500,
        )


class FactNotFoundError(NotFoundError):
    """Fact not found error (404)."""

    def __init__(self, fact_id: str) -> None:
        """Initialize fact not found error.

        Args:
            fact_id: The ID of the fact that was not found.
        """
        super().__init__(resource="Fact", resource_id=fact_id)


class ProceduralMemoryError(ARIAException):
    """Procedural memory operation error (500).

    Used for failures when storing or retrieving workflows from Supabase.
    """

    def __init__(self, message: str = "Unknown error") -> None:
        """Initialize procedural memory error.

        Args:
            message: Error details.
        """
        super().__init__(
            message=f"Procedural memory operation failed: {message}",
            code="PROCEDURAL_MEMORY_ERROR",
            status_code=500,
        )


class WorkflowNotFoundError(NotFoundError):
    """Workflow not found error (404)."""

    def __init__(self, workflow_id: str) -> None:
        """Initialize workflow not found error.

        Args:
            workflow_id: The ID of the workflow that was not found.
        """
        super().__init__(resource="Workflow", resource_id=workflow_id)


class ProspectiveMemoryError(ARIAException):
    """Prospective memory operation error (500).

    Used for failures when storing or retrieving tasks from Supabase.
    """

    def __init__(self, message: str = "Unknown error") -> None:
        """Initialize prospective memory error.

        Args:
            message: Error details.
        """
        super().__init__(
            message=f"Prospective memory operation failed: {message}",
            code="PROSPECTIVE_MEMORY_ERROR",
            status_code=500,
        )


class TaskNotFoundError(NotFoundError):
    """Prospective task not found error (404)."""

    def __init__(self, task_id: str) -> None:
        """Initialize task not found error.

        Args:
            task_id: The ID of the task that was not found.
        """
        super().__init__(resource="Task", resource_id=task_id)


class DigitalTwinError(ARIAException):
    """Digital twin operation error (500).

    Used for failures when analyzing writing style or managing fingerprints.
    """

    def __init__(self, message: str = "Unknown error") -> None:
        """Initialize digital twin error.

        Args:
            message: Error details.
        """
        super().__init__(
            message=f"Digital twin operation failed: {message}",
            code="DIGITAL_TWIN_ERROR",
            status_code=500,
        )


class FingerprintNotFoundError(NotFoundError):
    """Writing style fingerprint not found error (404)."""

    def __init__(self, fingerprint_id: str) -> None:
        """Initialize fingerprint not found error.

        Args:
            fingerprint_id: The ID of the fingerprint that was not found.
        """
        super().__init__(resource="Fingerprint", resource_id=fingerprint_id)


class AuditLogError(ARIAException):
    """Audit log operation error (500).

    Used for failures when writing or querying audit logs.
    """

    def __init__(self, message: str = "Unknown error") -> None:
        """Initialize audit log error.

        Args:
            message: Error details.
        """
        super().__init__(
            message=f"Audit log operation failed: {message}",
            code="AUDIT_LOG_ERROR",
            status_code=500,
        )


class CorporateMemoryError(ARIAException):
    """Corporate memory operation error (500).

    Used for failures when storing or retrieving company-level facts.
    """

    def __init__(self, message: str = "Unknown error") -> None:
        """Initialize corporate memory error.

        Args:
            message: Error details.
        """
        super().__init__(
            message=f"Corporate memory operation failed: {message}",
            code="CORPORATE_MEMORY_ERROR",
            status_code=500,
        )


class CorporateFactNotFoundError(NotFoundError):
    """Corporate fact not found error (404)."""

    def __init__(self, fact_id: str) -> None:
        """Initialize corporate fact not found error.

        Args:
            fact_id: The ID of the corporate fact that was not found.
        """
        super().__init__(resource="Corporate fact", resource_id=fact_id)


class LeadMemoryError(ARIAException):
    """Lead memory operation error (500).

    Used for failures in lead memory operations.
    """

    def __init__(self, message: str = "Unknown error") -> None:
        """Initialize lead memory error.

        Args:
            message: Error details.
        """
        super().__init__(
            message=f"Lead memory error: {message}",
            code="LEAD_MEMORY_ERROR",
            status_code=500,
        )


class LeadNotFoundError(NotFoundError):
    """Lead not found error (404)."""

    def __init__(self, lead_id: str) -> None:
        """Initialize lead not found error.

        Args:
            lead_id: The ID of the lead that was not found.
        """
        super().__init__(resource="Lead", resource_id=lead_id)


class LeadMemoryGraphError(ARIAException):
    """Lead memory graph operation error (500).

    Used for failures when storing or querying lead memory in the knowledge graph.
    """

    def __init__(self, message: str = "Unknown error") -> None:
        """Initialize lead memory graph error.

        Args:
            message: Error details.
        """
        super().__init__(
            message=f"Lead memory graph operation failed: {message}",
            code="LEAD_MEMORY_GRAPH_ERROR",
            status_code=500,
        )


class LeadMemoryNotFoundError(NotFoundError):
    """Lead memory not found error (404)."""

    def __init__(self, lead_id: str) -> None:
        """Initialize lead memory not found error.

        Args:
            lead_id: The ID of the lead memory that was not found.
        """
        super().__init__(resource="Lead memory", resource_id=lead_id)


class InvalidStageTransitionError(ARIAException):
    """Invalid lifecycle stage transition error (400).

    Raised when attempting an invalid stage transition
    (e.g., account -> lead).
    """

    def __init__(self, current_stage: str, target_stage: str) -> None:
        """Initialize invalid stage transition error.

        Args:
            current_stage: The current lifecycle stage.
            target_stage: The attempted target stage.
        """
        super().__init__(
            message=f"Cannot transition from '{current_stage}' to '{target_stage}'",
            code="INVALID_STAGE_TRANSITION",
            status_code=400,
            details={"current_stage": current_stage, "target_stage": target_stage},
        )


class OODALoopError(ARIAException):
    """OODA loop processing error (500).

    Used for failures during OODA loop execution phases.
    """

    def __init__(self, message: str = "Unknown error") -> None:
        """Initialize OODA loop error.

        Args:
            message: Error details.
        """
        super().__init__(
            message=f"OODA loop error: {message}",
            code="OODA_LOOP_ERROR",
            status_code=500,
        )


class OODAMaxIterationsError(ARIAException):
    """OODA loop exceeded maximum iterations (400).

    Raised when the OODA loop cannot achieve the goal within
    the configured maximum number of iterations.
    """

    def __init__(self, goal_id: str, iterations: int) -> None:
        """Initialize max iterations error.

        Args:
            goal_id: The goal that could not be achieved.
            iterations: Number of iterations attempted.
        """
        super().__init__(
            message=f"OODA loop for goal '{goal_id}' exceeded maximum iterations ({iterations})",
            code="OODA_MAX_ITERATIONS",
            status_code=400,
            details={"goal_id": goal_id, "iterations": iterations},
        )


class OODABlockedError(ARIAException):
    """OODA loop is blocked and cannot proceed (400).

    Raised when the OODA loop cannot find any viable actions
    to take toward the goal.
    """

    def __init__(self, goal_id: str, reason: str) -> None:
        """Initialize blocked error.

        Args:
            goal_id: The goal that is blocked.
            reason: Why the loop is blocked.
        """
        super().__init__(
            message=f"OODA loop for goal '{goal_id}' is blocked: {reason}",
            code="OODA_BLOCKED",
            status_code=400,
            details={"goal_id": goal_id, "reason": reason},
        )


class AgentError(ARIAException):
    """Agent operation error (500).

    Used for failures in agent execution.
    """

    def __init__(self, agent_name: str, message: str = "Unknown error") -> None:
        """Initialize agent error.

        Args:
            agent_name: Name of the agent that failed.
            message: Error details.
        """
        super().__init__(
            message=f"Agent '{agent_name}' failed: {message}",
            code="AGENT_ERROR",
            status_code=500,
            details={"agent_name": agent_name},
        )


class AgentExecutionError(ARIAException):
    """Agent execution error (500).

    Used for failures during task execution.
    """

    def __init__(
        self,
        agent_name: str,
        task_type: str,
        message: str = "Unknown error",
    ) -> None:
        """Initialize agent execution error.

        Args:
            agent_name: Name of the agent that failed.
            task_type: Type of task being executed.
            message: Error details.
        """
        super().__init__(
            message=f"Agent '{agent_name}' failed to execute {task_type}: {message}",
            code="AGENT_EXECUTION_ERROR",
            status_code=500,
            details={"agent_name": agent_name, "task_type": task_type},
        )


class EmailDraftError(ARIAException):
    """Exception for email draft generation errors."""

    def __init__(
        self,
        message: str = "Unknown error",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize email draft error.

        Args:
            message: Error details.
            details: Additional error details.
        """
        super().__init__(
            message=f"Email draft operation failed: {message}",
            code="EMAIL_DRAFT_ERROR",
            status_code=500,
            details=details,
        )


class EmailSendError(ARIAException):
    """Exception for email sending errors."""

    def __init__(
        self,
        message: str = "Unknown error",
        draft_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize email send error.

        Args:
            message: Error details.
            draft_id: Optional ID of the draft that failed to send.
            details: Additional error details.
        """
        error_details = details or {}
        if draft_id:
            error_details["draft_id"] = draft_id
        super().__init__(
            message=f"Email send failed: {message}",
            code="EMAIL_SEND_ERROR",
            status_code=502,
            details=error_details,
        )


class CRMSyncError(ARIAException):
    """CRM synchronization error (500).

    Used for failures during CRM sync operations.
    """

    def __init__(
        self,
        message: str = "Unknown error",
        provider: str | None = None,
    ) -> None:
        """Initialize CRM sync error.

        Args:
            message: Error details.
            provider: Optional CRM provider name.
        """
        details = {}
        if provider:
            details["provider"] = provider
        super().__init__(
            message=f"CRM sync error: {message}",
            code="CRM_SYNC_ERROR",
            status_code=500,
            details=details,
        )


class CRMConnectionError(ARIAException):
    """CRM connection error (502).

    Used when unable to connect to CRM provider.
    """

    def __init__(self, provider: str, message: str | None = None) -> None:
        """Initialize CRM connection error.

        Args:
            provider: The CRM provider name.
            message: Optional error message.
        """
        error_message = message or f"Failed to connect to {provider}"
        super().__init__(
            message=error_message,
            code="CRM_CONNECTION_ERROR",
            status_code=502,
            details={"provider": provider},
        )


class CRMSyncConflictError(ARIAException):
    """CRM sync conflict error (409).

    Raised when there are conflicting changes between ARIA and CRM.
    """

    def __init__(
        self,
        lead_id: str,
        conflicting_fields: list[str],
    ) -> None:
        """Initialize CRM sync conflict error.

        Args:
            lead_id: The lead ID with conflicts.
            conflicting_fields: List of fields with conflicts.
        """
        super().__init__(
            message=f"Sync conflict detected for lead '{lead_id}' on fields: {', '.join(conflicting_fields)}",
            code="CRM_SYNC_CONFLICT",
            status_code=409,
            details={
                "lead_id": lead_id,
                "conflicting_fields": conflicting_fields,
            },
        )


class CRMSyncNotFoundError(NotFoundError):
    """CRM sync state not found error (404)."""

    def __init__(self, lead_id: str) -> None:
        """Initialize CRM sync not found error.

        Args:
            lead_id: The lead ID with no sync state.
        """
        super().__init__(resource="CRM sync state", resource_id=lead_id)


class RateLimitError(ARIAException):
    """Rate limit exceeded error (429).

    Raised when a client exceeds their rate limit for API requests.
    """

    def __init__(
        self,
        retry_after: int,
        limit: str,
        message: str | None = None,
    ) -> None:
        """Initialize rate limit error.

        Args:
            retry_after: Seconds until the client can retry.
            limit: The rate limit that was exceeded (e.g., "100/hour").
            message: Optional custom error message.
        """
        error_message = (
            message or f"Rate limit exceeded: {limit}. Try again in {retry_after} seconds."
        )
        super().__init__(
            message=error_message,
            code="RATE_LIMIT_EXCEEDED",
            status_code=429,
            details={"retry_after": retry_after, "limit": limit},
        )
