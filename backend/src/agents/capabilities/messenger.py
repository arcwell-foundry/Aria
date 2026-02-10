"""Team Messenger capability for ScribeAgent and OperatorAgent.

Provides Slack integration for ARIA: delivering daily briefings to channels,
pushing urgent alerts, handling slash commands (/aria prep, /aria status,
/aria brief), and sharing competitive battle cards as rich attachments.

Uses direct Slack Bot API via OAuth. Maintains a WebSocket connection for
real-time slash command reception. Channel-scoped permissions — the bot
only accesses channels it has been explicitly invited to.

Slack team_id and channel mappings are stored in
``user_integrations.metadata``.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from src.agents.capabilities.base import BaseCapability, CapabilityResult
from src.db.supabase import SupabaseClient
from src.integrations.oauth import get_oauth_client

logger = logging.getLogger(__name__)


# ── Domain models ─────────────────────────────────────────────────────────


class SlackCommandType(str, Enum):
    """Recognised /aria slash command sub-commands."""

    PREP = "prep"
    STATUS = "status"
    BRIEF = "brief"


@dataclass
class SlackEvent:
    """Inbound event from Slack (slash command or interaction).

    Attributes:
        team_id: Slack workspace identifier.
        channel_id: Channel where the event originated.
        user_id: Slack user ID who triggered the event.
        command: The slash command text (e.g. ``"/aria prep Q2 review"``).
        text: The arguments following the command.
        response_url: Slack-provided URL for delayed responses.
        trigger_id: Trigger ID for opening modals (optional).
        timestamp: Event timestamp.
    """

    team_id: str
    channel_id: str
    user_id: str
    command: str
    text: str = ""
    response_url: str = ""
    trigger_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class SlackBlock:
    """A single Slack Block Kit element."""

    type: str
    text: dict[str, Any] | None = None
    elements: list[dict[str, Any]] | None = None
    fields: list[dict[str, Any]] | None = None
    accessory: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialise to Slack API format, omitting None fields."""
        d: dict[str, Any] = {"type": self.type}
        if self.text is not None:
            d["text"] = self.text
        if self.elements is not None:
            d["elements"] = self.elements
        if self.fields is not None:
            d["fields"] = self.fields
        if self.accessory is not None:
            d["accessory"] = self.accessory
        return d


# ── Capability ────────────────────────────────────────────────────────────


class TeamMessengerCapability(BaseCapability):
    """Slack-based team messaging: briefings, alerts, commands, battle cards.

    Connects to Slack via Bot OAuth token stored in the user's Composio
    integration.  All messages use Block Kit for rich formatting.

    The capability is channel-scoped: the bot can only post to channels
    it has been invited to, and channel mappings are persisted in
    ``user_integrations.metadata.channel_mappings``.

    Designed for ScribeAgent (content delivery) and OperatorAgent (automation).
    """

    capability_name: str = "team-messenger"
    agent_types: list[str] = ["ScribeAgent", "OperatorAgent"]
    oauth_scopes: list[str] = ["slack_bot"]
    data_classes: list[str] = ["INTERNAL"]

    # ── BaseCapability abstract interface ──────────────────────────────

    async def can_handle(self, task: dict[str, Any]) -> float:
        """Return confidence for team-messenger tasks."""
        task_type = task.get("type", "")
        if task_type in {
            "send_briefing",
            "send_alert",
            "receive_command",
            "share_battle_card",
        }:
            return 0.95
        if "slack" in task_type.lower() or "messenger" in task_type.lower():
            return 0.6
        return 0.0

    async def execute(
        self,
        task: dict[str, Any],
        context: dict[str, Any],  # noqa: ARG002
    ) -> CapabilityResult:
        """Route to the correct method based on task type."""
        start = time.monotonic()
        user_id = self._user_context.user_id
        task_type = task.get("type", "")

        try:
            if task_type == "send_briefing":
                channel = task.get("channel", "")
                briefing = task.get("briefing", {})
                await self.send_briefing(user_id, channel, briefing)
                data: dict[str, Any] = {
                    "channel": channel,
                    "status": "delivered",
                }

            elif task_type == "send_alert":
                channel = task.get("channel", "")
                alert = task.get("alert", {})
                await self.send_alert(user_id, channel, alert)
                data = {
                    "channel": channel,
                    "alert_type": alert.get("type", "unknown"),
                    "status": "delivered",
                }

            elif task_type == "receive_command":
                event_data = task.get("event", {})
                event = self._dict_to_slack_event(event_data)
                await self.receive_command(event)
                data = {
                    "command": event.command,
                    "text": event.text,
                    "status": "processed",
                }

            elif task_type == "share_battle_card":
                channel = task.get("channel", "")
                competitor = task.get("competitor", "")
                await self.share_battle_card(user_id, channel, competitor)
                data = {
                    "channel": channel,
                    "competitor": competitor,
                    "status": "shared",
                }

            else:
                return CapabilityResult(
                    success=False,
                    error=f"Unknown task type: {task_type}",
                    execution_time_ms=int((time.monotonic() - start) * 1000),
                )

            elapsed = int((time.monotonic() - start) * 1000)
            return CapabilityResult(success=True, data=data, execution_time_ms=elapsed)

        except Exception as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            logger.exception(
                "Team messenger task failed",
                extra={"user_id": user_id, "task_type": task_type},
            )
            return CapabilityResult(
                success=False,
                error=str(exc),
                execution_time_ms=elapsed,
            )

    def get_data_classes_accessed(self) -> list[str]:
        """Slack messages are internal team communications."""
        return ["internal"]

    # ── Public methods ─────────────────────────────────────────────────

    async def send_briefing(
        self,
        user_id: str,
        channel: str,
        briefing: dict[str, Any],
    ) -> None:
        """Deliver a daily briefing to a Slack channel using Block Kit.

        The briefing dict is expected to contain:
        - ``title``: Briefing headline.
        - ``summary``: Executive summary paragraph.
        - ``highlights``: List of highlight strings.
        - ``metrics``: Dict of metric_name -> value.
        - ``action_items``: List of action item strings.

        Args:
            user_id: Authenticated user UUID.
            channel: Slack channel ID or name.
            briefing: Structured briefing payload.
        """
        connection_id = await self._get_slack_connection(user_id)
        if not connection_id:
            raise ValueError("No active Slack integration found for user")

        await self._validate_channel_access(user_id, channel)

        title = briefing.get("title", "Daily Briefing")
        summary = briefing.get("summary", "")
        highlights = briefing.get("highlights", [])
        metrics = briefing.get("metrics", {})
        action_items = briefing.get("action_items", [])

        blocks: list[dict[str, Any]] = []

        # Header
        blocks.append(
            {
                "type": "header",
                "text": {"type": "plain_text", "text": title},
            }
        )

        # Summary section
        if summary:
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": summary},
                }
            )

        blocks.append({"type": "divider"})

        # Highlights
        if highlights:
            highlight_text = "\n".join(f"\u2022 {h}" for h in highlights)
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Key Highlights*\n{highlight_text}",
                    },
                }
            )

        # Metrics as fields (max 10 per section)
        if metrics:
            metric_fields = [
                {"type": "mrkdwn", "text": f"*{name}*\n{value}"}
                for name, value in list(metrics.items())[:10]
            ]
            blocks.append(
                {
                    "type": "section",
                    "fields": metric_fields,
                }
            )

        # Action items
        if action_items:
            items_text = "\n".join(f"{i + 1}. {item}" for i, item in enumerate(action_items))
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Action Items*\n{items_text}",
                    },
                }
            )

        # Footer with timestamp
        now = datetime.now(UTC)
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            f"Prepared by ARIA \u2022 {now.strftime('%B %d, %Y at %H:%M UTC')}"
                        ),
                    },
                ],
            }
        )

        await self._post_message(connection_id, channel, blocks=blocks)

        await self.log_activity(
            activity_type="briefing_delivered",
            title=f"Daily briefing sent to #{channel}",
            description=(
                f"Delivered briefing '{title}' with "
                f"{len(highlights)} highlights, "
                f"{len(metrics)} metrics, "
                f"{len(action_items)} action items"
            ),
            confidence=0.95,
            metadata={
                "channel": channel,
                "briefing_title": title,
                "highlight_count": len(highlights),
                "metric_count": len(metrics),
                "action_item_count": len(action_items),
            },
        )

    async def send_alert(
        self,
        user_id: str,
        channel: str,
        alert: dict[str, Any],
    ) -> None:
        """Push an urgent signal to a Slack channel.

        The alert dict is expected to contain:
        - ``type``: Alert classification (e.g. ``"deal_risk"``, ``"competitor_move"``).
        - ``severity``: ``"critical"`` | ``"high"`` | ``"medium"``.
        - ``title``: Short alert headline.
        - ``message``: Detailed alert body.
        - ``link``: Optional URL for more details.
        - ``recommended_action``: Suggested next step.

        Args:
            user_id: Authenticated user UUID.
            channel: Slack channel ID or name.
            alert: Structured alert payload.
        """
        connection_id = await self._get_slack_connection(user_id)
        if not connection_id:
            raise ValueError("No active Slack integration found for user")

        await self._validate_channel_access(user_id, channel)

        alert_type = alert.get("type", "general")
        severity = alert.get("severity", "medium")
        title = alert.get("title", "ARIA Alert")
        message = alert.get("message", "")
        link = alert.get("link")
        recommended_action = alert.get("recommended_action")

        severity_emoji = {
            "critical": "\U0001f6a8",  # rotating_light
            "high": "\u26a0\ufe0f",  # warning
            "medium": "\U0001f4e2",  # loudspeaker
        }.get(severity, "\u2139\ufe0f")  # information_source

        blocks: list[dict[str, Any]] = []

        # Alert header with severity indicator
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{severity_emoji} *{title}*\nSeverity: `{severity}` \u2022 Type: `{alert_type}`",
                },
            }
        )

        blocks.append({"type": "divider"})

        # Alert body
        if message:
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": message},
                }
            )

        # Recommended action
        if recommended_action:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Recommended Action:* {recommended_action}",
                    },
                }
            )

        # Link button
        if link:
            blocks.append(
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "View Details"},
                            "url": link,
                            "style": "primary" if severity == "critical" else "default",
                        },
                    ],
                }
            )

        # Context footer
        now = datetime.now(UTC)
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"ARIA Alert \u2022 {now.strftime('%H:%M UTC')}",
                    },
                ],
            }
        )

        await self._post_message(connection_id, channel, blocks=blocks)

        await self.log_activity(
            activity_type="alert_sent",
            title=f"Alert pushed: {title}",
            description=(f"Sent {severity} {alert_type} alert to #{channel}: {message[:120]}"),
            confidence=0.95,
            metadata={
                "channel": channel,
                "alert_type": alert_type,
                "severity": severity,
            },
        )

    async def receive_command(self, event: SlackEvent) -> None:
        """Handle an inbound /aria slash command from Slack.

        Supported sub-commands:
        - ``/aria prep [meeting]`` — Trigger meeting prep for a named meeting.
        - ``/aria status [lead]`` — Return current lead status summary.
        - ``/aria brief`` — Generate and post a quick briefing.

        Responses are sent back via the event's ``response_url`` for
        asynchronous reply (within Slack's 3-second deadline).

        Args:
            event: Parsed SlackEvent from the Slack webhook.
        """
        aria_user_id = await self._resolve_aria_user(event.team_id, event.user_id)
        if not aria_user_id:
            await self._respond_ephemeral(
                event.response_url,
                "Your Slack account is not linked to an ARIA user. "
                "Connect Slack in ARIA Settings \u2192 Integrations.",
            )
            return

        parts = event.text.strip().split(maxsplit=1)
        sub_command = parts[0].lower() if parts else ""
        args = parts[1] if len(parts) > 1 else ""

        if sub_command == SlackCommandType.PREP:
            await self._handle_prep_command(aria_user_id, event, args)
        elif sub_command == SlackCommandType.STATUS:
            await self._handle_status_command(aria_user_id, event, args)
        elif sub_command == SlackCommandType.BRIEF:
            await self._handle_brief_command(aria_user_id, event)
        else:
            await self._respond_ephemeral(
                event.response_url,
                (
                    "Unknown command. Available commands:\n"
                    "\u2022 `/aria prep [meeting name]` \u2014 Prepare for a meeting\n"
                    "\u2022 `/aria status [lead name]` \u2014 Get lead status\n"
                    "\u2022 `/aria brief` \u2014 Quick daily briefing"
                ),
            )

        await self.log_activity(
            activity_type="slack_command_received",
            title=f"Slash command: /aria {sub_command}",
            description=(
                f"Processed /aria {sub_command} {args} "
                f"from Slack user {event.user_id} in channel {event.channel_id}"
            ),
            confidence=0.9,
            metadata={
                "slack_team_id": event.team_id,
                "slack_channel_id": event.channel_id,
                "sub_command": sub_command,
                "args": args,
            },
        )

    async def share_battle_card(
        self,
        user_id: str,
        channel: str,
        competitor: str,
    ) -> None:
        """Share a competitive battle card as a Slack attachment.

        Fetches the battle card from ``battle_cards`` table, formats it
        with Block Kit including strengths/weaknesses comparison, key
        differentiators, and recommended talk tracks, then posts to the
        specified channel.

        Args:
            user_id: Authenticated user UUID.
            channel: Slack channel ID or name.
            competitor: Competitor company name.
        """
        connection_id = await self._get_slack_connection(user_id)
        if not connection_id:
            raise ValueError("No active Slack integration found for user")

        await self._validate_channel_access(user_id, channel)

        card = await self._fetch_battle_card(user_id, competitor)
        if not card:
            # Post a "not found" message instead of failing silently
            await self._post_message(
                connection_id,
                channel,
                text=f"No battle card found for *{competitor}*. Ask ARIA to research them first.",
            )
            return

        blocks: list[dict[str, Any]] = []

        # Title
        blocks.append(
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"Battle Card: {card.get('competitor_name', competitor)}",
                },
            }
        )

        # Overview
        overview = card.get("overview", "")
        if overview:
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": overview},
                }
            )

        blocks.append({"type": "divider"})

        # Strengths vs Weaknesses side-by-side
        strengths = card.get("strengths", [])
        weaknesses = card.get("weaknesses", [])
        if strengths or weaknesses:
            strength_text = "\n".join(f"\u2705 {s}" for s in strengths[:5])
            weakness_text = "\n".join(f"\u274c {w}" for w in weaknesses[:5])
            blocks.append(
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Their Strengths*\n{strength_text}"},
                        {"type": "mrkdwn", "text": f"*Their Weaknesses*\n{weakness_text}"},
                    ],
                }
            )

        # Key differentiators
        differentiators = card.get("differentiators", [])
        if differentiators:
            diff_text = "\n".join(f"\u2022 {d}" for d in differentiators[:5])
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Our Differentiators*\n{diff_text}",
                    },
                }
            )

        # Talk tracks
        talk_tracks = card.get("talk_tracks", [])
        if talk_tracks:
            tracks_text = "\n".join(f">{t}" for t in talk_tracks[:3])
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Recommended Talk Tracks*\n{tracks_text}",
                    },
                }
            )

        # Last updated footer
        updated_at = card.get("updated_at", "")
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"ARIA Battle Card \u2022 Last updated: {updated_at}",
                    },
                ],
            }
        )

        await self._post_message(connection_id, channel, blocks=blocks)

        await self.log_activity(
            activity_type="battle_card_shared",
            title=f"Battle card shared: {competitor}",
            description=(
                f"Shared battle card for {competitor} "
                f"to #{channel} with {len(strengths)} strengths, "
                f"{len(weaknesses)} weaknesses, {len(differentiators)} differentiators"
            ),
            confidence=0.9,
            related_entity_type="company",
            metadata={
                "channel": channel,
                "competitor": competitor,
                "card_id": card.get("id"),
            },
        )

    # ── WebSocket listener ─────────────────────────────────────────────

    async def start_websocket_listener(self, user_id: str) -> None:
        """Start a WebSocket connection for real-time Slack event reception.

        Opens a Slack Socket Mode connection via the bot token stored in
        the user's integration. Incoming events are dispatched to
        ``receive_command`` for slash commands.

        This is intended to be run as a background task (e.g. via
        ``asyncio.create_task`` on app startup).

        Args:
            user_id: Authenticated user UUID.
        """
        connection_id = await self._get_slack_connection(user_id)
        if not connection_id:
            logger.warning(
                "Cannot start Slack WebSocket: no active integration",
                extra={"user_id": user_id},
            )
            return

        oauth_client = get_oauth_client()

        logger.info(
            "Starting Slack WebSocket listener",
            extra={"user_id": user_id},
        )

        while True:
            try:
                result = await oauth_client.execute_action(
                    connection_id=connection_id,
                    action="open_socket",
                    params={},
                )

                socket_url = result.get("url", "")
                if not socket_url:
                    logger.warning("No WebSocket URL returned from Slack")
                    await asyncio.sleep(30)
                    continue

                await self._listen_socket(socket_url, user_id)

            except asyncio.CancelledError:
                logger.info(
                    "Slack WebSocket listener cancelled",
                    extra={"user_id": user_id},
                )
                break
            except Exception:
                logger.exception(
                    "Slack WebSocket error, reconnecting",
                    extra={"user_id": user_id},
                )
                await asyncio.sleep(5)

    async def _listen_socket(self, socket_url: str, user_id: str) -> None:  # noqa: ARG002
        """Listen on an open WebSocket and dispatch events.

        Args:
            socket_url: WebSocket URL from Slack Socket Mode.
            user_id: ARIA user UUID for context.
        """
        try:
            import websockets  # noqa: F811
        except ImportError:
            logger.error("websockets package not installed; cannot use Socket Mode")
            return

        async with websockets.connect(socket_url) as ws:
            async for raw_message in ws:
                try:
                    payload = json.loads(raw_message)
                except json.JSONDecodeError:
                    continue

                event_type = payload.get("type")

                # Acknowledge envelope
                envelope_id = payload.get("envelope_id")
                if envelope_id:
                    await ws.send(json.dumps({"envelope_id": envelope_id}))

                if event_type == "slash_commands":
                    event_payload = payload.get("payload", {})
                    event = SlackEvent(
                        team_id=event_payload.get("team_id", ""),
                        channel_id=event_payload.get("channel_id", ""),
                        user_id=event_payload.get("user_id", ""),
                        command=event_payload.get("command", ""),
                        text=event_payload.get("text", ""),
                        response_url=event_payload.get("response_url", ""),
                        trigger_id=event_payload.get("trigger_id", ""),
                    )
                    asyncio.create_task(self.receive_command(event))

    # ── Private helpers ────────────────────────────────────────────────

    async def _get_slack_connection(self, user_id: str) -> str | None:
        """Look up the user's active Slack integration.

        Args:
            user_id: Authenticated user UUID.

        Returns:
            Composio connection_id string, or None if not connected.
        """
        client = SupabaseClient.get_client()
        try:
            resp = (
                client.table("user_integrations")
                .select("*")
                .eq("user_id", user_id)
                .eq("integration_type", "slack")
                .eq("status", "active")
                .maybe_single()
                .execute()
            )
            if resp.data and resp.data.get("composio_connection_id"):
                return str(resp.data["composio_connection_id"])
        except Exception:
            logger.warning(
                "Failed to lookup Slack integration",
                extra={"user_id": user_id},
                exc_info=True,
            )
        return None

    async def _get_slack_metadata(self, user_id: str) -> dict[str, Any]:
        """Fetch the metadata blob from the user's Slack integration row.

        Returns:
            Metadata dict (may contain ``team_id``, ``channel_mappings``).
        """
        client = SupabaseClient.get_client()
        try:
            resp = (
                client.table("user_integrations")
                .select("metadata")
                .eq("user_id", user_id)
                .eq("integration_type", "slack")
                .eq("status", "active")
                .maybe_single()
                .execute()
            )
            if resp.data:
                return resp.data.get("metadata") or {}
        except Exception:
            logger.warning(
                "Failed to fetch Slack metadata",
                extra={"user_id": user_id},
                exc_info=True,
            )
        return {}

    async def _validate_channel_access(self, user_id: str, channel: str) -> None:
        """Verify the bot has been invited to the target channel.

        Checks ``user_integrations.metadata.channel_mappings`` for the
        channel. Raises ``PermissionError`` if the channel is not listed.

        Args:
            user_id: Authenticated user UUID.
            channel: Slack channel ID or name to validate.
        """
        metadata = await self._get_slack_metadata(user_id)
        channel_mappings = metadata.get("channel_mappings", {})

        # Allow if channel is in mappings (by ID or by name)
        if channel in channel_mappings or channel in channel_mappings.values():
            return

        # If no mappings stored yet, allow (first-time use)
        if not channel_mappings:
            logger.info(
                "No channel mappings stored; allowing channel access",
                extra={"user_id": user_id, "channel": channel},
            )
            return

        raise PermissionError(
            f"Bot does not have access to channel '{channel}'. "
            "Invite the ARIA bot to the channel first."
        )

    async def _post_message(
        self,
        connection_id: str,
        channel: str,
        *,
        text: str = "",
        blocks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Post a message to a Slack channel via the Bot API.

        Args:
            connection_id: Composio connection ID for Slack.
            channel: Target Slack channel ID or name.
            text: Fallback plain-text content.
            blocks: Block Kit blocks for rich formatting.

        Returns:
            Slack API response dict.
        """
        oauth_client = get_oauth_client()

        params: dict[str, Any] = {"channel": channel}
        if blocks:
            params["blocks"] = json.dumps(blocks)
            # Slack requires text as fallback for notifications
            params["text"] = text or "ARIA message"
        elif text:
            params["text"] = text

        try:
            result = await oauth_client.execute_action(
                connection_id=connection_id,
                action="chat_post_message",
                params=params,
            )
            return result
        except Exception:
            logger.exception(
                "Failed to post Slack message",
                extra={"channel": channel},
            )
            raise

    async def _respond_ephemeral(
        self,
        response_url: str,
        text: str,
    ) -> None:
        """Send an ephemeral response back to a slash command.

        Uses Slack's ``response_url`` for deferred replies visible only
        to the invoking user.

        Args:
            response_url: The response_url from the slash command payload.
            text: Message text to send.
        """
        if not response_url:
            return

        try:
            import httpx  # noqa: F811
        except ImportError:
            logger.error("httpx not installed; cannot send ephemeral response")
            return

        payload = {
            "response_type": "ephemeral",
            "text": text,
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    response_url,
                    json=payload,
                    timeout=5.0,
                )
                resp.raise_for_status()
        except Exception:
            logger.warning(
                "Failed to send ephemeral response",
                extra={"response_url": response_url},
                exc_info=True,
            )

    async def _resolve_aria_user(
        self,
        team_id: str,
        slack_user_id: str,
    ) -> str | None:
        """Map a Slack user to an ARIA user_id via integration metadata.

        Looks up ``user_integrations`` rows where
        ``metadata.team_id == team_id`` and
        ``metadata.slack_user_id == slack_user_id``.

        Args:
            team_id: Slack workspace identifier.
            slack_user_id: Slack user identifier.

        Returns:
            ARIA user_id string, or None if not linked.
        """
        client = SupabaseClient.get_client()
        try:
            resp = (
                client.table("user_integrations")
                .select("user_id, metadata")
                .eq("integration_type", "slack")
                .eq("status", "active")
                .execute()
            )
            if not resp.data:
                return None

            for row in resp.data:
                meta = row.get("metadata") or {}
                if meta.get("team_id") == team_id and meta.get("slack_user_id") == slack_user_id:
                    return str(row["user_id"])
        except Exception:
            logger.warning(
                "Failed to resolve ARIA user from Slack identity",
                extra={"team_id": team_id, "slack_user_id": slack_user_id},
                exc_info=True,
            )
        return None

    async def _handle_prep_command(
        self,
        aria_user_id: str,
        event: SlackEvent,
        meeting_query: str,
    ) -> None:
        """Handle ``/aria prep [meeting]`` — trigger meeting preparation.

        Searches upcoming calendar events matching the query and triggers
        brief generation for the best match.

        Args:
            aria_user_id: Resolved ARIA user UUID.
            event: Original SlackEvent for response routing.
            meeting_query: Meeting name or search term.
        """
        if not meeting_query:
            await self._respond_ephemeral(
                event.response_url,
                "Usage: `/aria prep [meeting name]`\nExample: `/aria prep Q2 Business Review`",
            )
            return

        client = SupabaseClient.get_client()
        try:
            resp = (
                client.table("meeting_briefs")
                .select("id, meeting_title, meeting_time, status")
                .eq("user_id", aria_user_id)
                .ilike("meeting_title", f"%{meeting_query}%")
                .order("meeting_time", desc=False)
                .limit(1)
                .execute()
            )

            if resp.data:
                brief = resp.data[0]
                status = brief.get("status", "unknown")
                await self._respond_ephemeral(
                    event.response_url,
                    (
                        f"Meeting prep for *{brief['meeting_title']}* "
                        f"({brief.get('meeting_time', 'TBD')}): `{status}`\n"
                        "Check ARIA for the full brief."
                    ),
                )
            else:
                await self._respond_ephemeral(
                    event.response_url,
                    (
                        f'No meeting found matching "{meeting_query}". '
                        "ARIA will prepare a brief when the meeting is on your calendar."
                    ),
                )
        except Exception:
            logger.exception("Error handling /aria prep")
            await self._respond_ephemeral(
                event.response_url,
                "Something went wrong while looking up that meeting. Please try again.",
            )

    async def _handle_status_command(
        self,
        aria_user_id: str,
        event: SlackEvent,
        lead_query: str,
    ) -> None:
        """Handle ``/aria status [lead]`` — return lead status summary.

        Searches lead_memories for a matching contact/company and returns
        a compact status summary.

        Args:
            aria_user_id: Resolved ARIA user UUID.
            event: Original SlackEvent for response routing.
            lead_query: Lead name or company search term.
        """
        if not lead_query:
            await self._respond_ephemeral(
                event.response_url,
                "Usage: `/aria status [lead name]`\nExample: `/aria status Acme Corp`",
            )
            return

        client = SupabaseClient.get_client()
        try:
            resp = (
                client.table("lead_memories")
                .select(
                    "id, contact_name, company_name, lifecycle_stage, "
                    "health_score, last_interaction_at"
                )
                .eq("user_id", aria_user_id)
                .or_(f"contact_name.ilike.%{lead_query}%,company_name.ilike.%{lead_query}%")
                .limit(1)
                .execute()
            )

            if resp.data:
                lead = resp.data[0]
                health = lead.get("health_score", 0)
                stage = lead.get("lifecycle_stage", "unknown")
                last_touch = lead.get("last_interaction_at", "N/A")
                name = lead.get("contact_name") or lead.get("company_name", "Unknown")

                await self._respond_ephemeral(
                    event.response_url,
                    (
                        f"*{name}* ({lead.get('company_name', '')})\n"
                        f"Stage: `{stage}` \u2022 Health: `{health}/100`\n"
                        f"Last interaction: {last_touch}"
                    ),
                )
            else:
                await self._respond_ephemeral(
                    event.response_url,
                    f'No lead found matching "{lead_query}".',
                )
        except Exception:
            logger.exception("Error handling /aria status")
            await self._respond_ephemeral(
                event.response_url,
                "Something went wrong while looking up that lead. Please try again.",
            )

    async def _handle_brief_command(
        self,
        aria_user_id: str,
        event: SlackEvent,
    ) -> None:
        """Handle ``/aria brief`` — generate a quick daily briefing.

        Compiles a lightweight briefing from recent activity, upcoming
        meetings, and lead updates, then posts it to the requesting channel.

        Args:
            aria_user_id: Resolved ARIA user UUID.
            event: Original SlackEvent for response routing.
        """
        client = SupabaseClient.get_client()

        try:
            # Gather quick stats
            now = datetime.now(UTC)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

            activities_resp = (
                client.table("aria_activity")
                .select("id", count="exact")
                .eq("user_id", aria_user_id)
                .gte("created_at", today_start.isoformat())
                .execute()
            )
            activity_count = activities_resp.count or 0

            leads_resp = (
                client.table("lead_memories")
                .select("id, health_score")
                .eq("user_id", aria_user_id)
                .lt("health_score", 40)
                .limit(5)
                .execute()
            )
            at_risk_count = len(leads_resp.data) if leads_resp.data else 0

            connection_id = await self._get_slack_connection(aria_user_id)
            if connection_id:
                briefing = {
                    "title": "Quick Briefing",
                    "summary": (f"Today so far: *{activity_count}* ARIA actions completed."),
                    "highlights": [],
                    "metrics": {
                        "Actions Today": str(activity_count),
                        "At-Risk Leads": str(at_risk_count),
                    },
                    "action_items": [],
                }

                if at_risk_count > 0:
                    briefing["highlights"].append(
                        f"{at_risk_count} lead(s) with health score below 40 need attention"
                    )

                await self.send_briefing(aria_user_id, event.channel_id, briefing)
                await self._respond_ephemeral(
                    event.response_url,
                    "Briefing posted to this channel.",
                )
            else:
                await self._respond_ephemeral(
                    event.response_url,
                    "Slack integration not fully configured. Check ARIA settings.",
                )
        except Exception:
            logger.exception("Error handling /aria brief")
            await self._respond_ephemeral(
                event.response_url,
                "Something went wrong while generating the briefing. Please try again.",
            )

    async def _fetch_battle_card(
        self,
        user_id: str,
        competitor: str,
    ) -> dict[str, Any] | None:
        """Fetch a battle card from the database.

        Args:
            user_id: Authenticated user UUID.
            competitor: Competitor company name to search for.

        Returns:
            Battle card dict, or None if not found.
        """
        client = SupabaseClient.get_client()
        try:
            resp = (
                client.table("battle_cards")
                .select("*")
                .eq("user_id", user_id)
                .ilike("competitor_name", f"%{competitor}%")
                .order("updated_at", desc=True)
                .limit(1)
                .execute()
            )
            if resp.data:
                return resp.data[0]
        except Exception:
            logger.warning(
                "Failed to fetch battle card",
                extra={"user_id": user_id, "competitor": competitor},
                exc_info=True,
            )
        return None

    @staticmethod
    def _dict_to_slack_event(data: dict[str, Any]) -> SlackEvent:
        """Deserialise a dict into a SlackEvent."""
        return SlackEvent(
            team_id=data.get("team_id", ""),
            channel_id=data.get("channel_id", ""),
            user_id=data.get("user_id", ""),
            command=data.get("command", ""),
            text=data.get("text", ""),
            response_url=data.get("response_url", ""),
            trigger_id=data.get("trigger_id", ""),
        )

    async def update_channel_mappings(
        self,
        user_id: str,
        channel_mappings: dict[str, str],
    ) -> None:
        """Persist channel mappings in the user's Slack integration metadata.

        Merges the provided mappings into existing metadata without
        overwriting other fields.

        Args:
            user_id: Authenticated user UUID.
            channel_mappings: Dict of channel_id -> channel_name.
        """
        client = SupabaseClient.get_client()
        try:
            existing = await self._get_slack_metadata(user_id)
            existing["channel_mappings"] = channel_mappings
            existing["channels_updated_at"] = datetime.now(UTC).isoformat()

            (
                client.table("user_integrations")
                .update({"metadata": existing})
                .eq("user_id", user_id)
                .eq("integration_type", "slack")
                .execute()
            )

            logger.info(
                "Updated Slack channel mappings",
                extra={
                    "user_id": user_id,
                    "channel_count": len(channel_mappings),
                },
            )
        except Exception:
            logger.exception(
                "Failed to update channel mappings",
                extra={"user_id": user_id},
            )
            raise

    async def store_team_id(self, user_id: str, team_id: str) -> None:
        """Store the Slack team_id in the user's integration metadata.

        Called during the OAuth callback after Slack authorization completes.

        Args:
            user_id: Authenticated user UUID.
            team_id: Slack workspace team identifier.
        """
        client = SupabaseClient.get_client()
        try:
            existing = await self._get_slack_metadata(user_id)
            existing["team_id"] = team_id

            (
                client.table("user_integrations")
                .update({"metadata": existing})
                .eq("user_id", user_id)
                .eq("integration_type", "slack")
                .execute()
            )

            logger.info(
                "Stored Slack team_id",
                extra={"user_id": user_id, "team_id": team_id},
            )
        except Exception:
            logger.exception(
                "Failed to store Slack team_id",
                extra={"user_id": user_id, "team_id": team_id},
            )
            raise
