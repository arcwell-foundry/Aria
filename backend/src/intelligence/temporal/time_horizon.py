"""Time Horizon Analyzer for JARVIS Intelligence.

This module categorizes implications by when they'll materialize,
using life sciences domain knowledge and LLM-powered analysis.

Key features:
- Categorize implications into time horizons (immediate, short, medium, long)
- Detect time-sensitive "closing windows" where action timing matters
- Recommend optimal action timing based on user calendar and goal deadlines
- Life sciences domain knowledge for FDA, clinical trials, and business cycles
"""

import json
import logging
import re
import time
from datetime import date, datetime, timedelta
from typing import Any

from src.core.llm import LLMClient
from src.core.task_types import TaskType
from src.intelligence.temporal.models import (
    ActionTiming,
    TimeHorizon,
    TimeHorizonCategorization,
)

logger = logging.getLogger(__name__)

# Default confidence when LLM analysis is unavailable
DEFAULT_CONFIDENCE = 0.6

# Time thresholds for horizon categorization (in days)
HORIZON_THRESHOLDS = {
    TimeHorizon.IMMEDIATE: 7,  # 1-7 days
    TimeHorizon.SHORT_TERM: 28,  # 1-4 weeks
    TimeHorizon.MEDIUM_TERM: 180,  # 1-6 months
    TimeHorizon.LONG_TERM: 365,  # 6+ months
}


class TimeHorizonAnalyzer:
    """Analyzer for categorizing implications by time horizon.

    Uses a hybrid approach:
    1. Pattern matching for known life sciences timelines
    2. LLM-powered analysis for nuanced timing
    3. User context integration for action timing recommendations

    Attributes:
        DEFAULT_CONFIDENCE: Default confidence when pattern matching
    """

    def __init__(self, llm_client: LLMClient) -> None:
        """Initialize the time horizon analyzer.

        Args:
            llm_client: LLM client for temporal analysis
        """
        self._llm = llm_client

    async def categorize(
        self,
        implications: list[dict[str, Any]],
    ) -> dict[TimeHorizon, list[dict[str, Any]]]:
        """Categorize implications by their time horizon.

        Main entry point for temporal analysis. Assigns each implication
        to a time horizon category based on when it will materialize.

        Args:
            implications: List of implication dictionaries to categorize

        Returns:
            Dictionary mapping time horizons to lists of implications
        """
        start_time = time.monotonic()

        categorized: dict[TimeHorizon, list[dict[str, Any]]] = {
            TimeHorizon.IMMEDIATE: [],
            TimeHorizon.SHORT_TERM: [],
            TimeHorizon.MEDIUM_TERM: [],
            TimeHorizon.LONG_TERM: [],
        }

        for implication in implications:
            try:
                categorization = await self._categorize_single(implication)

                # Add categorization data to implication
                enriched = {
                    **implication,
                    "time_horizon": categorization.time_horizon.value,
                    "time_to_impact": categorization.time_to_impact,
                    "is_closing_window": categorization.is_closing_window,
                    "closing_window_reason": categorization.closing_window_reason,
                    "temporal_confidence": categorization.confidence,
                }

                categorized[categorization.time_horizon].append(enriched)

            except Exception as e:
                logger.warning(
                    "Failed to categorize implication, defaulting to medium_term",
                    extra={"error": str(e)},
                )
                # Default to medium_term on error
                enriched = {
                    **implication,
                    "time_horizon": TimeHorizon.MEDIUM_TERM.value,
                    "time_to_impact": "1-3 months",
                    "is_closing_window": False,
                    "closing_window_reason": None,
                    "temporal_confidence": DEFAULT_CONFIDENCE,
                }
                categorized[TimeHorizon.MEDIUM_TERM].append(enriched)

        elapsed_ms = (time.monotonic() - start_time) * 1000
        logger.info(
            "Time horizon categorization complete",
            extra={
                "total_implications": len(implications),
                "immediate": len(categorized[TimeHorizon.IMMEDIATE]),
                "short_term": len(categorized[TimeHorizon.SHORT_TERM]),
                "medium_term": len(categorized[TimeHorizon.MEDIUM_TERM]),
                "long_term": len(categorized[TimeHorizon.LONG_TERM]),
                "elapsed_ms": elapsed_ms,
            },
        )

        return categorized

    async def recommend_timing(
        self,
        user_id: str,  # noqa: ARG002 - Reserved for future calendar integration
        implication: dict[str, Any],
        calendar_events: list[dict[str, Any]] | None = None,
        goal_deadlines: list[dict[str, Any]] | None = None,
    ) -> ActionTiming:
        """Recommend optimal action timing for an implication.

        Combines time horizon with user's calendar and goal deadlines
        to suggest when to act for maximum effectiveness.

        Args:
            user_id: User ID for context (reserved for future calendar API integration)
            implication: Implication to analyze
            calendar_events: Optional list of user's upcoming calendar events
            goal_deadlines: Optional list of goal deadlines

        Returns:
            ActionTiming with recommended dates and reasoning
        """
        time_horizon_str = implication.get("time_horizon", TimeHorizon.MEDIUM_TERM.value)
        time_to_impact = implication.get("time_to_impact", "1-3 months")

        try:
            time_horizon = TimeHorizon(time_horizon_str)
        except ValueError:
            time_horizon = TimeHorizon.MEDIUM_TERM

        # Calculate base timing from time horizon
        today = date.today()
        optimal_date, window_open, window_close = self._calculate_base_timing(
            time_horizon, time_to_impact, today
        )

        # Adjust based on calendar and deadlines if available
        if calendar_events or goal_deadlines:
            optimal_date = self._adjust_for_context(
                optimal_date, window_open, window_close, calendar_events, goal_deadlines
            )

        # Generate reasoning
        reason = self._generate_timing_reason(
            time_horizon, time_to_impact, optimal_date, calendar_events, goal_deadlines
        )

        # Calculate confidence based on context availability
        confidence = 0.8 if (calendar_events or goal_deadlines) else 0.6

        return ActionTiming(
            optimal_action_date=optimal_date,
            window_opens=window_open,
            window_closes=window_close,
            reason=reason,
            confidence=confidence,
        )

    async def _categorize_single(
        self,
        implication: dict[str, Any],
    ) -> TimeHorizonCategorization:
        """Categorize a single implication.

        Uses pattern matching first, then LLM for nuanced cases.

        Args:
            implication: Implication to categorize

        Returns:
            TimeHorizonCategorization with horizon and timing details
        """
        content = implication.get("content", "")
        trigger_event = implication.get("trigger_event", "")
        causal_chain = implication.get("causal_chain", [])

        # Combine all text for analysis
        chain_text = " ".join(
            f"{hop.get('source_entity', '')} {hop.get('relationship', '')} {hop.get('target_entity', '')}"
            for hop in causal_chain
        )
        full_text = f"{trigger_event} {content} {chain_text}"

        # First try pattern matching for known life sciences patterns
        pattern_result = self._pattern_match_horizon(full_text)
        if pattern_result:
            return pattern_result

        # Fall back to LLM analysis
        return await self._llm_categorize(full_text)

    def _pattern_match_horizon(
        self,
        text: str,
    ) -> TimeHorizonCategorization | None:
        """Pattern match for known life sciences timelines.

        Checks for FDA, clinical trial, and business cycle patterns.

        Args:
            text: Text to analyze

        Returns:
            TimeHorizonCategorization if pattern matched, None otherwise
        """
        text_lower = text.lower()

        # FDA regulatory timelines
        if any(kw in text_lower for kw in ["pdufa", "fda decision", "approval decision"]):
            # PDUFA dates are typically known and imminent
            return TimeHorizonCategorization(
                time_horizon=TimeHorizon.SHORT_TERM,
                time_to_impact="2-4 weeks",
                is_closing_window=True,
                closing_window_reason="PDUFA date requires preparation",
                confidence=0.9,
            )

        if any(
            kw in text_lower for kw in ["bla submission", "nda submission", "510(k) submission"]
        ):
            return TimeHorizonCategorization(
                time_horizon=TimeHorizon.MEDIUM_TERM,
                time_to_impact="3-6 months",
                is_closing_window=False,
                closing_window_reason=None,
                confidence=0.8,
            )

        if any(kw in text_lower for kw in ["fda review", "regulatory review", "agency review"]):
            return TimeHorizonCategorization(
                time_horizon=TimeHorizon.MEDIUM_TERM,
                time_to_impact="6-12 months",
                is_closing_window=False,
                closing_window_reason=None,
                confidence=0.8,
            )

        # Clinical trial phases
        if any(kw in text_lower for kw in ["phase 3", "pivotal trial", "registration trial"]):
            return TimeHorizonCategorization(
                time_horizon=TimeHorizon.LONG_TERM,
                time_to_impact="3-4 years",
                is_closing_window=False,
                closing_window_reason=None,
                confidence=0.8,
            )

        if any(kw in text_lower for kw in ["phase 2", "phase ii"]):
            return TimeHorizonCategorization(
                time_horizon=TimeHorizon.LONG_TERM,
                time_to_impact="2-3 years",
                is_closing_window=False,
                closing_window_reason=None,
                confidence=0.8,
            )

        if any(kw in text_lower for kw in ["phase 1", "phase i", "first-in-human"]):
            return TimeHorizonCategorization(
                time_horizon=TimeHorizon.LONG_TERM,
                time_to_impact="1-2 years",
                is_closing_window=False,
                closing_window_reason=None,
                confidence=0.8,
            )

        # Conference deadlines
        if any(kw in text_lower for kw in ["asco abstract", "asco deadline"]):
            # ASCO abstracts typically due February
            return TimeHorizonCategorization(
                time_horizon=TimeHorizon.SHORT_TERM,
                time_to_impact="2-4 weeks",
                is_closing_window=True,
                closing_window_reason="Conference abstract deadline approaching",
                confidence=0.9,
            )

        if any(kw in text_lower for kw in ["jpmorgan", "jp morgan", "jpm conference"]):
            return TimeHorizonCategorization(
                time_horizon=TimeHorizon.MEDIUM_TERM,
                time_to_impact="1-2 months",
                is_closing_window=False,
                closing_window_reason=None,
                confidence=0.7,
            )

        # Budget cycles
        if any(kw in text_lower for kw in ["budget planning", "fiscal year", "budget cycle"]):
            return TimeHorizonCategorization(
                time_horizon=TimeHorizon.MEDIUM_TERM,
                time_to_impact="3-6 months",
                is_closing_window=False,
                closing_window_reason=None,
                confidence=0.7,
            )

        # Competitor response windows
        if any(
            kw in text_lower for kw in ["competitor launch", "competitive response", "market entry"]
        ):
            return TimeHorizonCategorization(
                time_horizon=TimeHorizon.SHORT_TERM,
                time_to_impact="2-4 weeks",
                is_closing_window=True,
                closing_window_reason="Competitive response window",
                confidence=0.7,
            )

        # Parse explicit time expressions
        time_result = self._parse_time_expression(text_lower)
        if time_result:
            return time_result

        return None

    def _parse_time_expression(
        self,
        text: str,
    ) -> TimeHorizonCategorization | None:
        """Parse explicit time expressions from text.

        Looks for patterns like "in 2 weeks", "within 3 months", etc.

        Args:
            text: Text to parse

        Returns:
            TimeHorizonCategorization if time expression found, None otherwise
        """
        # Days
        days_match = re.search(r"(\d+)\s*day", text)
        if days_match:
            days = int(days_match.group(1))
            if days <= 7:
                return TimeHorizonCategorization(
                    time_horizon=TimeHorizon.IMMEDIATE,
                    time_to_impact=f"{days} days",
                    is_closing_window=days <= 3,
                    closing_window_reason="Immediate action required" if days <= 3 else None,
                    confidence=0.9,
                )
            elif days <= 28:
                return TimeHorizonCategorization(
                    time_horizon=TimeHorizon.SHORT_TERM,
                    time_to_impact=f"{days} days",
                    is_closing_window=days <= 14,
                    closing_window_reason=None,
                    confidence=0.9,
                )

        # Weeks
        weeks_match = re.search(r"(\d+)\s*week", text)
        if weeks_match:
            weeks = int(weeks_match.group(1))
            if weeks <= 1:
                return TimeHorizonCategorization(
                    time_horizon=TimeHorizon.IMMEDIATE,
                    time_to_impact=f"{weeks} week",
                    is_closing_window=True,
                    closing_window_reason="This week",
                    confidence=0.9,
                )
            elif weeks <= 4:
                return TimeHorizonCategorization(
                    time_horizon=TimeHorizon.SHORT_TERM,
                    time_to_impact=f"{weeks} weeks",
                    is_closing_window=weeks <= 2,
                    closing_window_reason=None,
                    confidence=0.9,
                )
            else:
                return TimeHorizonCategorization(
                    time_horizon=TimeHorizon.MEDIUM_TERM,
                    time_to_impact=f"{weeks} weeks",
                    is_closing_window=False,
                    closing_window_reason=None,
                    confidence=0.9,
                )

        # Months
        months_match = re.search(r"(\d+)\s*month", text)
        if months_match:
            months = int(months_match.group(1))
            if months <= 6:
                return TimeHorizonCategorization(
                    time_horizon=TimeHorizon.MEDIUM_TERM,
                    time_to_impact=f"{months} months",
                    is_closing_window=months <= 2,
                    closing_window_reason=None,
                    confidence=0.9,
                )
            else:
                return TimeHorizonCategorization(
                    time_horizon=TimeHorizon.LONG_TERM,
                    time_to_impact=f"{months} months",
                    is_closing_window=False,
                    closing_window_reason=None,
                    confidence=0.9,
                )

        # Quarters
        quarters_match = re.search(r"(\d+)\s*quarter", text)
        if quarters_match:
            quarters = int(quarters_match.group(1))
            return TimeHorizonCategorization(
                time_horizon=TimeHorizon.LONG_TERM,
                time_to_impact=f"{quarters} quarters",
                is_closing_window=False,
                closing_window_reason=None,
                confidence=0.9,
            )

        # Keywords
        if any(kw in text for kw in ["immediate", "urgent", "asap", "now", "critical"]):
            return TimeHorizonCategorization(
                time_horizon=TimeHorizon.IMMEDIATE,
                time_to_impact="1-3 days",
                is_closing_window=True,
                closing_window_reason="Urgent timing indicated",
                confidence=0.8,
            )

        if any(kw in text for kw in ["soon", "shortly", "near term"]):
            return TimeHorizonCategorization(
                time_horizon=TimeHorizon.SHORT_TERM,
                time_to_impact="1-2 weeks",
                is_closing_window=False,
                closing_window_reason=None,
                confidence=0.7,
            )

        if any(kw in text for kw in ["long term", "eventually", "future"]):
            return TimeHorizonCategorization(
                time_horizon=TimeHorizon.LONG_TERM,
                time_to_impact="6+ months",
                is_closing_window=False,
                closing_window_reason=None,
                confidence=0.7,
            )

        return None

    async def _llm_categorize(
        self,
        text: str,
    ) -> TimeHorizonCategorization:
        """Use LLM to categorize time horizon when patterns don't match.

        Args:
            text: Text to analyze

        Returns:
            TimeHorizonCategorization from LLM analysis
        """
        try:
            system_prompt = """You are a life sciences business analyst specializing in timing analysis.
Categorize when the business impact of an event will materialize.

Consider these life sciences timelines:
- FDA regulatory: BLA/NDA review (6-12 months), 510(k) clearance (3-6 months), PDUFA dates
- Clinical trials: Phase 1 (1-2 yr), Phase 2 (2-3 yr), Phase 3 (3-4 yr)
- Business cycles: Budget planning in Q3, quarterly reviews, contract renewals
- Conferences: ASCO (June, abstract deadline Feb), JP Morgan Healthcare (January)
- Competitor response: Typically 2-4 week response window

Return ONLY a valid JSON object (no markdown, no explanation):
{
  "time_horizon": "immediate|short_term|medium_term|long_term",
  "time_to_impact": "human-readable estimate like '2-3 weeks'",
  "is_closing_window": true/false,
  "closing_window_reason": "why timing matters or null",
  "confidence": 0.0-1.0
}

Time horizon definitions:
- immediate: 1-7 days
- short_term: 1-4 weeks
- medium_term: 1-6 months
- long_term: 6+ months"""

            response = await self._llm.generate_response(
                messages=[
                    {
                        "role": "user",
                        "content": f"Analyze the timing of this business event:\n\n{text[:1000]}",
                    }
                ],
                system_prompt=system_prompt,
                temperature=0.1,
                max_tokens=200,
                task=TaskType.ANALYST_RESEARCH,
                agent_id="time_horizon",
            )

            # Clean and parse JSON response
            response_text = response.strip()
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                response_text = "\n".join(lines).strip()

            data = json.loads(response_text)

            # Map string to enum
            horizon_str = data.get("time_horizon", "medium_term")
            try:
                time_horizon = TimeHorizon(horizon_str)
            except ValueError:
                time_horizon = TimeHorizon.MEDIUM_TERM

            return TimeHorizonCategorization(
                time_horizon=time_horizon,
                time_to_impact=data.get("time_to_impact", "1-3 months"),
                is_closing_window=data.get("is_closing_window", False),
                closing_window_reason=data.get("closing_window_reason"),
                confidence=data.get("confidence", 0.7),
            )

        except Exception as e:
            logger.warning(f"LLM categorization failed: {e}")
            # Return default
            return TimeHorizonCategorization(
                time_horizon=TimeHorizon.MEDIUM_TERM,
                time_to_impact="1-3 months",
                is_closing_window=False,
                closing_window_reason=None,
                confidence=DEFAULT_CONFIDENCE,
            )

    def _calculate_base_timing(
        self,
        time_horizon: TimeHorizon,
        time_to_impact: str,  # noqa: ARG002 - Reserved for future nuanced timing
        today: date,
    ) -> tuple[date, date, date]:
        """Calculate base timing from time horizon.

        Args:
            time_horizon: Categorized time horizon
            time_to_impact: Natural language time estimate
            today: Current date

        Returns:
            Tuple of (optimal_date, window_open, window_close)
        """
        if time_horizon == TimeHorizon.IMMEDIATE:
            # Act within 1-2 days
            optimal_date = today + timedelta(days=1)
            window_open = today
            window_close = today + timedelta(days=3)
        elif time_horizon == TimeHorizon.SHORT_TERM:
            # Act within 1-2 weeks
            optimal_date = today + timedelta(days=7)
            window_open = today + timedelta(days=3)
            window_close = today + timedelta(days=14)
        elif time_horizon == TimeHorizon.MEDIUM_TERM:
            # Act within 1-2 months
            optimal_date = today + timedelta(days=30)
            window_open = today + timedelta(days=14)
            window_close = today + timedelta(days=60)
        else:  # LONG_TERM
            # Act within 2-3 months
            optimal_date = today + timedelta(days=60)
            window_open = today + timedelta(days=30)
            window_close = today + timedelta(days=90)

        return optimal_date, window_open, window_close

    def _adjust_for_context(
        self,
        optimal_date: date,
        window_open: date,
        window_close: date,
        calendar_events: list[dict[str, Any]] | None,
        goal_deadlines: list[dict[str, Any]] | None,
    ) -> date:
        """Adjust optimal date based on calendar and goal context.

        Args:
            optimal_date: Base optimal date
            window_open: Window open date
            window_close: Window close date
            calendar_events: User's calendar events
            goal_deadlines: Goal deadlines

        Returns:
            Adjusted optimal date
        """
        # If we have goal deadlines, prefer acting before them
        if goal_deadlines:
            for goal in goal_deadlines:
                deadline_str = goal.get("deadline")
                if deadline_str:
                    try:
                        if isinstance(deadline_str, str):
                            deadline = datetime.fromisoformat(deadline_str).date()
                        else:
                            deadline = deadline_str

                        # If deadline is within our window, act before it
                        if window_open <= deadline <= window_close:
                            # Act 1-2 weeks before deadline
                            adjusted = deadline - timedelta(days=7)
                            if adjusted >= window_open:
                                return adjusted
                    except (ValueError, TypeError):
                        pass

        # Avoid scheduling on busy days
        if calendar_events:
            event_dates = set()
            for event in calendar_events:
                event_date_str = event.get("date") or event.get("start")
                if event_date_str:
                    try:
                        if isinstance(event_date_str, str):
                            event_date = datetime.fromisoformat(event_date_str).date()
                        else:
                            event_date = event_date_str
                        event_dates.add(event_date)
                    except (ValueError, TypeError):
                        pass

            # If optimal date is busy, find next free day
            if optimal_date in event_dates:
                for i in range(1, 8):
                    candidate = optimal_date + timedelta(days=i)
                    if candidate not in event_dates and candidate <= window_close:
                        return candidate

        return optimal_date

    def _generate_timing_reason(
        self,
        time_horizon: TimeHorizon,
        time_to_impact: str,
        optimal_date: date,
        calendar_events: list[dict[str, Any]] | None,
        goal_deadlines: list[dict[str, Any]] | None,
    ) -> str:
        """Generate human-readable reason for timing recommendation.

        Args:
            time_horizon: Time horizon category
            time_to_impact: Time until impact
            optimal_date: Recommended action date
            calendar_events: Calendar events
            goal_deadlines: Goal deadlines

        Returns:
            Human-readable timing explanation
        """
        horizon_descriptions = {
            TimeHorizon.IMMEDIATE: "This requires immediate attention",
            TimeHorizon.SHORT_TERM: "This should be addressed soon",
            TimeHorizon.MEDIUM_TERM: "Plan for this in the coming weeks",
            TimeHorizon.LONG_TERM: "This is a longer-term consideration",
        }

        reasons = [f"{horizon_descriptions[time_horizon]} (impact expected in {time_to_impact})."]

        if goal_deadlines:
            for goal in goal_deadlines[:1]:
                deadline = goal.get("deadline")
                title = goal.get("title", "your goal")
                if deadline:
                    reasons.append(f"Aligns with deadline for '{title}'.")

        if calendar_events:
            reasons.append("Scheduled to avoid calendar conflicts.")

        reasons.append(f"Recommended action date: {optimal_date.strftime('%B %d, %Y')}.")

        return " ".join(reasons)
