"""Custom exceptions for ARIA backend."""

from typing import Any


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
