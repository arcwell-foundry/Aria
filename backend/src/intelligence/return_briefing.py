"""
'What Changed While You Were Away' Intelligence.
Generates a prioritized briefing when user returns after absence.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class ReturnBriefingGenerator:
    """Generates a 'what changed' briefing when user returns after absence."""

    def __init__(self, supabase_client):
        self._db = supabase_client

    async def generate_return_briefing(self, user_id: str, last_active: datetime = None) -> Optional[dict]:
        """
        Generate a briefing of what changed since the user was last active.
        Returns None if user was active within the last 4 hours.
        """
        if not last_active:
            last_active = await self._get_last_active(user_id)

        if not last_active:
            return None

        now = datetime.now(timezone.utc)
        hours_away = (now - last_active).total_seconds() / 3600

        if hours_away < 4:
            return None

        logger.info(f"[ReturnBriefing] User away for {hours_away:.1f} hours. Generating briefing.")

        changes = {}

        new_signals = await self._get_new_signals(user_id, last_active)
        if new_signals:
            changes['new_signals'] = new_signals

        new_insights = await self._get_new_insights(user_id, last_active)
        if new_insights:
            changes['new_insights'] = new_insights

        competitive_changes = await self._get_competitive_changes(user_id, last_active)
        if competitive_changes:
            changes['competitive_changes'] = competitive_changes

        email_intel = await self._get_email_intel(user_id, last_active)
        if email_intel:
            changes['email_intel'] = email_intel

        if not changes:
            return None

        return {
            'hours_away': round(hours_away, 1),
            'last_active': last_active.isoformat(),
            'generated_at': now.isoformat(),
            'changes': changes,
            'summary': self._build_summary(changes, hours_away),
            'priority_items': self._extract_priority_items(changes),
        }

    async def _get_last_active(self, user_id: str) -> Optional[datetime]:
        try:
            result = self._db.table("user_sessions")\
                .select("updated_at")\
                .eq("user_id", user_id)\
                .order("updated_at", desc=True)\
                .limit(1)\
                .execute()
            if result.data and result.data[0].get("updated_at"):
                return datetime.fromisoformat(result.data[0]["updated_at"].replace("Z", "+00:00"))
            return None
        except Exception as e:
            logger.warning(f"[ReturnBriefing] Failed to get last active: {e}")
            return None

    async def _get_new_signals(self, user_id: str, since: datetime) -> Optional[dict]:
        try:
            result = self._db.table("market_signals")\
                .select("company_name, headline, signal_type, relevance_score, detected_at")\
                .eq("user_id", user_id)\
                .gte("detected_at", since.isoformat())\
                .order("relevance_score", desc=True)\
                .limit(10)\
                .execute()
            if not result.data:
                return None
            by_company = {}
            for s in result.data:
                company = s["company_name"]
                if company not in by_company:
                    by_company[company] = []
                by_company[company].append(s)
            return {'total': len(result.data), 'by_company': by_company, 'top_signals': result.data[:5]}
        except Exception:
            return None

    async def _get_new_insights(self, user_id: str, since: datetime) -> Optional[dict]:
        try:
            result = self._db.table("jarvis_insights")\
                .select("classification, content, engine_source, confidence, created_at")\
                .eq("user_id", user_id)\
                .gte("created_at", since.isoformat())\
                .order("confidence", desc=True)\
                .limit(5)\
                .execute()
            if not result.data:
                return None
            return {'total': len(result.data), 'top_insights': result.data[:3]}
        except Exception:
            return None

    async def _get_competitive_changes(self, user_id: str, since: datetime) -> Optional[list]:
        try:
            result = self._db.table("market_signals")\
                .select("company_name, signal_type, headline")\
                .eq("user_id", user_id)\
                .gte("detected_at", since.isoformat())\
                .in_("signal_type", ["product", "funding", "leadership", "fda_approval", "earnings"])\
                .execute()
            if not result.data:
                return None
            changes = []
            seen = set()
            for s in result.data:
                if s["company_name"] not in seen:
                    seen.add(s["company_name"])
                    changes.append({'company': s['company_name'], 'signal_type': s['signal_type'], 'headline': s['headline']})
            return changes if changes else None
        except Exception:
            return None

    async def _get_email_intel(self, user_id: str, since: datetime) -> Optional[dict]:
        try:
            result = self._db.table("cross_email_intelligence")\
                .select("pattern_type, insight, confidence")\
                .eq("user_id", user_id)\
                .gte("detected_at", since.isoformat())\
                .order("confidence", desc=True)\
                .limit(5)\
                .execute()
            if not result.data:
                return None
            return {'total': len(result.data), 'top_items': result.data[:3]}
        except Exception:
            return None

    def _build_summary(self, changes: dict, hours_away: float) -> str:
        parts = []
        days = hours_away / 24
        if days >= 1:
            parts.append(f"You were away for {days:.0f} day{'s' if days > 1 else ''}.")
        else:
            parts.append(f"You were away for {hours_away:.0f} hours.")
        if 'new_signals' in changes:
            t = changes['new_signals']['total']
            c = len(changes['new_signals']['by_company'])
            parts.append(f"{t} new market signals across {c} companies.")
        if 'new_insights' in changes:
            parts.append(f"{changes['new_insights']['total']} new intelligence insights.")
        if 'competitive_changes' in changes:
            parts.append(f"Competitive changes at {len(changes['competitive_changes'])} companies.")
        return ' '.join(parts)

    def _extract_priority_items(self, changes: dict) -> list:
        items = []
        if 'new_signals' in changes:
            for s in changes['new_signals']['top_signals'][:2]:
                items.append({'type': 'signal', 'priority': s.get('relevance_score', 0.5),
                    'text': f"[{s['signal_type'].upper()}] {s['company_name']}: {s['headline'][:100]}"})
        if 'new_insights' in changes:
            for i in changes['new_insights']['top_insights'][:2]:
                items.append({'type': 'insight', 'priority': i.get('confidence', 0.5),
                    'text': f"[{i['classification'].upper()}] {i['content'][:100]}"})
        items.sort(key=lambda x: x['priority'], reverse=True)
        return items[:3]
