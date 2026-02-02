"""ScribeAgent module for ARIA.

Drafts emails and documents with style matching using Digital Twin.
"""

import logging
from typing import TYPE_CHECKING, Any

from src.agents.base import AgentResult, BaseAgent

if TYPE_CHECKING:
    from src.core.llm import LLMClient

logger = logging.getLogger(__name__)


class ScribeAgent(BaseAgent):
    """Drafts emails and documents with style matching.

    The Scribe agent creates communications tailored to the user's
    writing style using Digital Twin, with support for multiple
    tones and templates.
    """

    name = "Scribe"
    description = "Drafts emails and documents with style matching"

    # Valid communication types and tones
    VALID_COMMUNICATION_TYPES = {"email", "document", "message"}
    VALID_TONES = {"formal", "friendly", "urgent"}

    def __init__(self, llm_client: "LLMClient", user_id: str) -> None:
        """Initialize the Scribe agent.

        Args:
            llm_client: LLM client for reasoning and generation.
            user_id: ID of the user this agent is working for.
        """
        self._templates: dict[str, str] = self._get_builtin_templates()
        super().__init__(llm_client=llm_client, user_id=user_id)

    def _get_builtin_templates(self) -> dict[str, str]:
        """Get built-in communication templates.

        Returns:
            Dictionary of template name to template string.
        """
        return {
            "follow_up_email": (
                "Hi {name},\n\n"
                "I wanted to follow up on {meeting_topic}. "
                "I hope you found our discussion valuable.\n\n"
                "Please let me know if you have any questions or would like to schedule a follow-up.\n\n"
                "Best regards"
            ),
            "meeting_request": (
                "Hi {name},\n\n"
                "I would like to schedule a meeting to {purpose}. "
                "Would you have time this week or next?\n\n"
                "Please let me know your availability.\n\n"
                "Best regards"
            ),
            "introduction": (
                "Hi {name},\n\n"
                "I'm {sender_name} from {company}. "
                "I'm reaching out because {reason}.\n\n"
                "I'd love to connect and discuss how we might work together.\n\n"
                "Best regards"
            ),
            "thank_you": (
                "Hi {name},\n\n"
                "Thank you for {reason}. "
                "I really appreciate your time and {detail}.\n\n"
                "Best regards"
            ),
        }

    def _register_tools(self) -> dict[str, Any]:
        """Register Scribe agent's drafting tools.

        Returns:
            Dictionary mapping tool names to callable functions.
        """
        return {
            "draft_email": self._draft_email,
            "draft_document": self._draft_document,
            "personalize": self._personalize,
            "apply_template": self._apply_template,
        }

    def validate_input(self, task: dict[str, Any]) -> bool:
        """Validate draft task input.

        Args:
            task: Task specification to validate.

        Returns:
            True if valid, False otherwise.
        """
        # Required fields
        if "communication_type" not in task:
            return False

        if "goal" not in task:
            return False

        # Validate communication_type
        comm_type = task["communication_type"]
        if comm_type not in self.VALID_COMMUNICATION_TYPES:
            return False

        # Validate tone if present
        if "tone" in task:
            tone = task["tone"]
            if tone not in self.VALID_TONES:
                return False

        # Validate recipient if present
        if "recipient" in task and task["recipient"] is not None:
            recipient = task["recipient"]
            if not isinstance(recipient, dict):
                return False

        return True

    async def execute(self, task: dict[str, Any]) -> AgentResult:  # noqa: ARG002
        """Execute the scribe agent's primary task.

        Args:
            task: Task specification with parameters.

        Returns:
            AgentResult with success status and output data.
        """
        return AgentResult(success=True, data={})

    async def _draft_email(
        self,
        recipient: dict[str, Any] | None = None,
        context: str = "",
        goal: str = "",
        tone: str = "formal",
    ) -> dict[str, Any]:
        """Draft an email.

        This is a mock implementation that generates template-based emails.
        In production, this would use the LLM with Digital Twin style.

        Args:
            recipient: Recipient information with name, title, company.
            context: Background context for the email.
            goal: What this email should achieve.
            tone: Tone of the email (formal, friendly, urgent).

        Returns:
            Drafted email with subject, body, and metadata.
        """
        recipient_name = "there"
        recipient_company = ""
        if recipient:
            recipient_name = recipient.get("name", "there")
            recipient_company = recipient.get("company", "")

        logger.info(
            f"Drafting email to {recipient_name}",
            extra={
                "recipient": recipient_name,
                "tone": tone,
                "goal": goal[:50] if goal else "",
            },
        )

        # Generate greeting based on tone
        if tone == "formal":
            greeting = f"Dear {recipient_name},"
        elif tone == "friendly":
            greeting = f"Hi {recipient_name},"
        else:  # urgent
            greeting = f"Dear {recipient_name},"

        # Generate subject based on tone and goal
        if tone == "urgent":
            subject = f"Urgent: {goal[:50]}" if goal else "Urgent: Action Required"
        else:
            subject = goal[:60] if goal else "Follow-up"

        # Generate body
        context_line = f"\n\n{context}" if context else ""

        if tone == "urgent":
            urgency_note = (
                "\n\nThis requires your immediate attention. Please respond as soon as possible."
            )
        else:
            urgency_note = ""

        # Generate call to action
        cta = "\n\nPlease let me know your availability to discuss further."

        # Closing based on tone
        if tone == "formal":
            closing = "\n\nBest regards"
        elif tone == "friendly":
            closing = "\n\nThanks!"
        else:  # urgent
            closing = "\n\nThank you for your prompt attention to this matter."

        body = f"{greeting}{context_line}{urgency_note}{cta}{closing}"

        word_count = len(body.split())

        return {
            "subject": subject,
            "body": body,
            "recipient_name": recipient_name if recipient else None,
            "recipient_company": recipient_company if recipient_company else None,
            "tone": tone,
            "word_count": word_count,
            "has_call_to_action": True,
        }

    async def _draft_document(
        self,
        document_type: str = "brief",
        context: str = "",
        goal: str = "",
        tone: str = "formal",
    ) -> dict[str, Any]:
        """Draft a document.

        This is a mock implementation that generates template-based documents.
        In production, this would use the LLM with Digital Twin style.

        Args:
            document_type: Type of document (brief, report, proposal).
            context: Background context for the document.
            goal: What this document should achieve.
            tone: Tone of the document.

        Returns:
            Drafted document with title, body, sections, and metadata.
        """
        logger.info(
            f"Drafting {document_type} document",
            extra={
                "document_type": document_type,
                "tone": tone,
                "goal": goal[:50] if goal else "",
            },
        )

        # Generate title from goal
        title = goal if goal else f"{document_type.capitalize()} Document"

        # Generate sections based on document type
        if document_type == "brief":
            sections = [
                {"heading": "Summary", "content": context if context else "Summary content here."},
                {"heading": "Key Points", "content": "• Point 1\n• Point 2\n• Point 3"},
            ]
        elif document_type == "report":
            sections = [
                {
                    "heading": "Executive Summary",
                    "content": context if context else "Executive summary.",
                },
                {"heading": "Background", "content": "Background information and context."},
                {"heading": "Analysis", "content": "Detailed analysis of the situation."},
                {"heading": "Recommendations", "content": "Recommended actions moving forward."},
            ]
        elif document_type == "proposal":
            sections = [
                {
                    "heading": "Introduction",
                    "content": context if context else "Introduction to the proposal.",
                },
                {"heading": "Proposed Solution", "content": "Details of the proposed solution."},
                {"heading": "Benefits", "content": "Expected benefits and outcomes."},
                {"heading": "Next Steps", "content": "Proposed next steps and timeline."},
            ]
        else:
            sections = [
                {"heading": "Content", "content": context if context else "Document content."},
            ]

        # Build body from sections
        body_parts = []
        for section in sections:
            body_parts.append(f"## {section['heading']}\n\n{section['content']}")
        body = "\n\n".join(body_parts)

        word_count = len(body.split())

        return {
            "title": title,
            "body": body,
            "sections": sections,
            "document_type": document_type,
            "word_count": word_count,
            "tone": tone,
        }

    async def _personalize(
        self,
        content: str,
        style: dict[str, Any] | None = None,
    ) -> str:
        """Personalize content to match a writing style.

        Applies Digital Twin style parameters to the content.
        In production, this would use the LLM for more sophisticated style matching.

        Currently supported style parameters:
            - signature: str - Appended to content if not already present
            - preferred_greeting: str - Replaces common greetings (Dear, Hello, Hi, Hey)

        Future LLM-based parameters (not yet implemented):
            - formality: "formal", "casual" - Adjusts overall tone
            - contractions: bool - Expands/contracts phrases

        Args:
            content: The content to personalize.
            style: Style parameters from Digital Twin.

        Returns:
            Personalized content matching the style.
        """
        if not style:
            return content

        logger.info(
            "Personalizing content with style",
            extra={"style_keys": list(style.keys())},
        )

        result = content

        # Apply greeting preference
        if "preferred_greeting" in style:
            preferred = style["preferred_greeting"]
            # Replace common greetings with preferred one
            greetings = ["Dear", "Hello", "Hi", "Hey"]
            for greeting in greetings:
                if result.startswith(f"{greeting} "):
                    result = result.replace(f"{greeting} ", f"{preferred} ", 1)
                    break

        # Apply signature
        if "signature" in style:
            sig = style["signature"]
            if sig not in result:
                result = f"{result}\n\n{sig}"

        return result

    async def _apply_template(
        self,
        template_name: str,
        variables: dict[str, Any],
    ) -> str:
        """Apply a template with variables.

        Substitutes variables into a named template.

        Args:
            template_name: Name of the template to use.
            variables: Variables to substitute in template.

        Returns:
            Rendered template content, or empty string if template not found.
        """
        if template_name not in self._templates:
            logger.warning(f"Template not found: {template_name}")
            return ""

        logger.info(
            f"Applying template: {template_name}",
            extra={"template": template_name, "variables": list(variables.keys())},
        )

        template = self._templates[template_name]

        # Substitute variables
        try:
            # Use str.format with partial substitution support
            result = template
            for key, value in variables.items():
                placeholder = "{" + key + "}"
                result = result.replace(placeholder, str(value))
            return result
        except KeyError as e:
            logger.warning(f"Missing variable in template: {e}")
            return template
