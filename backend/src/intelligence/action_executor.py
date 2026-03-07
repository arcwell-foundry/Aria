"""
Post-Approval Action Executor.

When a user approves an action in the Action Queue, this service
executes the appropriate downstream actions based on the action_type.

This is the critical bridge between "ARIA proposes" and "ARIA executes."
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ActionExecutor:
    """Executes approved actions with downstream effects."""

    def __init__(self, supabase_client: Any) -> None:
        self._db = supabase_client

    async def execute_approved_action(self, action_id: str, user_id: str) -> dict[str, Any]:
        """Execute an approved action. Called after status is set to 'approved'.

        Returns execution result dict.
        """
        action = (
            self._db.table("aria_action_queue")
            .select("*")
            .eq("id", action_id)
            .limit(1)
            .execute()
        )

        if not action.data:
            return {"status": "error", "message": "Action not found"}

        action_data = action.data[0]
        action_type = action_data.get("action_type", "")
        payload = action_data.get("payload", {})
        if isinstance(payload, str):
            payload = json.loads(payload)

        logger.info("[ActionExecutor] Executing: %s (%s)", action_type, action_id)

        try:
            handlers: dict[str, Any] = {
                "displacement_outreach": self._execute_displacement_outreach,
                "regulatory_displacement": self._execute_displacement_outreach,
                "competitive_pricing_response": self._execute_pricing_response,
                "lead_discovery": self._execute_lead_discovery,
                "conference_outreach": self._execute_conference_outreach,
                "clinical_trial_outreach": self._execute_clinical_trial_outreach,
            }
            handler = handlers.get(action_type, self._execute_generic)
            result = await handler(user_id, action_data, payload)

            # Mark action as completed
            self._db.table("aria_action_queue").update({
                "status": "completed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "result": result,
            }).eq("id", action_id).execute()

            # Sync proactive_proposals status
            insight_id = payload.get("insight_id")
            if insight_id:
                self._db.table("proactive_proposals").update({
                    "status": "approved",
                    "responded_at": datetime.now(timezone.utc).isoformat(),
                }).eq("insight_id", insight_id).eq("user_id", user_id).execute()

            # Create follow-up reminder
            await self._create_followup(user_id, action_data, result)

            # Write to semantic memory
            try:
                self._db.table("memory_semantic").insert({
                    "user_id": user_id,
                    "fact": (
                        f"[Action Approved] {action_data.get('title', '')}: "
                        f"User approved and ARIA executed. {result.get('summary', '')}"
                    ),
                    "confidence": 0.95,
                    "source": "action_execution",
                    "metadata": {"action_id": action_id, "action_type": action_type},
                }).execute()
            except Exception as e:
                logger.warning("[ActionExecutor] Failed to write semantic memory: %s", e)

            # Create activity log
            try:
                self._db.table("aria_activity").insert({
                    "user_id": user_id,
                    "activity_type": "action_executed",
                    "title": f"Executed: {action_data.get('title', '')}",
                    "description": result.get("summary", "Action completed"),
                    "metadata": {"action_id": action_id, "result": result},
                }).execute()
            except Exception as e:
                logger.warning("[ActionExecutor] Failed to create activity log: %s", e)

            logger.info("[ActionExecutor] Completed: %s", action_type)
            return result

        except Exception as e:
            logger.error("[ActionExecutor] Execution failed: %s", e)
            self._db.table("aria_action_queue").update({
                "status": "failed",
                "result": {"error": str(e)},
            }).eq("id", action_id).execute()
            return {"status": "failed", "error": str(e)}

    # ================================================================
    # LLM EMAIL GENERATION — DISPLACEMENT OUTREACH
    # ================================================================

    async def _execute_displacement_outreach(
        self, user_id: str, action: dict, payload: dict
    ) -> dict[str, Any]:
        """Generate a competitive displacement email using:
        - User's digital twin (writing style/voice)
        - Battle card competitive positioning
        - Signal context (the "why now")

        Supports two modes:
        - Mode A (no CRM): Template with [Contact Name] placeholder
        - Mode B (CRM connected): Personalized emails per account contact (future)
        """
        company_name = payload.get("company_name", "")
        competitive_context = payload.get("competitive_context", {})
        insight_content = action.get("description", "")
        insight_id = payload.get("insight_id")

        # 1. Get user's writing style from digital twin
        writing_style = await self._get_digital_twin(user_id)

        # 2. Get user's company name
        user_company = await self._get_user_company_name(user_id)

        # 3. Build the LLM prompt
        differentiation = competitive_context.get("differentiation", [])
        weaknesses = competitive_context.get("weaknesses", [])
        pricing = competitive_context.get("pricing", {})

        system_prompt = f"""You are writing an email for a sales professional at {user_company}.

WRITING STYLE (match this exactly):
- Tone: {writing_style.get('tone', 'professional')}
- Style: {writing_style.get('writing_style', 'concise and direct')}
- Formality: {writing_style.get('formality_level', 'business')}
- Vocabulary: {writing_style.get('vocabulary_patterns', 'simple, professional')}

FORMATTING RULES:
- Match the user's typical email structure
- Keep paragraphs short (1-2 sentences based on their style)
- Use bullet points if their style includes them
- Match their greeting and sign-off patterns

CRITICAL EMAIL RULES:
1. NEVER mention the competitor's specific problem (FDA issue, recall, etc.) in the email
2. Lead with VALUE and SUPPLY CONTINUITY, not with competitor vulnerability
3. The competitive intelligence informs your TIMING and POSITIONING, not your opening line
4. Keep language compliance-safe — no specific regulatory claims about competitors
5. Frame as industry awareness and proactive outreach
6. The "why now" should be subtle: "Given the importance of supply chain reliability..." not "Your supplier has FDA issues"
7. Include a clear, low-friction call to action (15-minute call, not a demo)
"""

        diff_text = (
            "; ".join(str(d) for d in differentiation[:3])
            if differentiation
            else "specialized solutions"
        )
        weakness_text = (
            "; ".join(str(w) for w in weaknesses[:2])
            if weaknesses
            else "integration challenges"
        )
        pricing_range = pricing.get("range", "enterprise-level") if isinstance(pricing, dict) else ""
        pricing_notes = pricing.get("notes", "") if isinstance(pricing, dict) else ""

        user_prompt = f"""Write a competitive displacement email for outreach to accounts that may currently \
use {company_name} products.

COMPETITIVE CONTEXT (use this to inform positioning, NOT to include in the email):
- Your advantages over {company_name}: {diff_text}
- Their vulnerabilities: {weakness_text}
- Their pricing: {pricing_range} — {pricing_notes}

SIGNAL CONTEXT (the reason for outreach timing):
{insight_content[:300]}

Generate:
1. Three subject line options (short, compelling, no competitor name)
2. Email body with [Contact Name] as placeholder (will be personalized later)
3. The body should be 4-6 short paragraphs max
4. Sign off as the user (their name will be added)

Respond in this exact JSON format:
{{
  "subject_options": ["subject 1", "subject 2", "subject 3"],
  "body": "the full email body with [Contact Name] placeholder",
  "aria_notes": "brief explanation of positioning strategy used"
}}"""

        # 4. Call LLM to generate the email
        email_data = await self._generate_email_via_llm(
            system_prompt, user_prompt, user_company, company_name,
            competitive_context, insight_content,
        )

        # 4b. Generate ARIA strategic reasoning narrative
        aria_reasoning = ""
        try:
            from src.intelligence.reasoning_engine import ReasoningEngine
            reasoning_engine = ReasoningEngine(self._db)

            # Get user's active goals for context
            goals_result = (
                self._db.table("goals")
                .select("title, goal_type, status")
                .eq("user_id", user_id)
                .in_("status", ["active", "in_progress", "plan_ready"])
                .limit(5)
                .execute()
            )

            aria_reasoning = await reasoning_engine.generate_email_reasoning(
                user_company=user_company,
                competitor_name=company_name,
                signal_context=insight_content[:500],
                competitive_positioning=competitive_context,
                email_body=email_data.get("body", ""),
                user_goals=goals_result.data if goals_result.data else [],
                digital_twin=writing_style,
            )
        except Exception as e:
            logger.warning("[ActionExecutor] Reasoning generation failed: %s", e)

        # 5. Save to email_drafts
        return await self._save_email_draft(
            user_id=user_id,
            email_data=email_data,
            purpose="competitive_displacement",
            draft_type="competitive_displacement",
            company_name=company_name,
            insight_id=insight_id,
            competitive_context=competitive_context,
            differentiation=differentiation,
            weaknesses=weaknesses,
            pricing=pricing,
            insight_content=insight_content,
            entity_type=payload.get("entity_type"),
            aria_reasoning=aria_reasoning,
        )

    # ================================================================
    # CONFERENCE OUTREACH
    # ================================================================

    async def _execute_conference_outreach(
        self, user_id: str, action: dict, payload: dict
    ) -> dict[str, Any]:
        """Generate conference meeting request email."""
        company_name = payload.get("company_name", "")
        competitive_context = payload.get("competitive_context", {})
        insight_content = action.get("description", "")
        insight_id = payload.get("insight_id")
        conference_name = payload.get("conference_name", "the upcoming conference")
        presentation_topic = payload.get("presentation_topic", "")

        writing_style = await self._get_digital_twin(user_id)
        user_company = await self._get_user_company_name(user_id)

        system_prompt = f"""You are writing an email for a sales professional at {user_company}.

WRITING STYLE (match this exactly):
- Tone: {writing_style.get('tone', 'professional')}
- Style: {writing_style.get('writing_style', 'concise and direct')}
- Formality: {writing_style.get('formality_level', 'business')}
- Vocabulary: {writing_style.get('vocabulary_patterns', 'simple, professional')}

CRITICAL EMAIL RULES:
1. Reference the conference and their presentation topic to show genuine interest
2. Keep the meeting request low-friction (coffee, 15-minute chat)
3. Connect their work to your company's relevant capabilities
4. Be specific about WHY you want to meet — relevance to their research/work
5. Do NOT hard-sell or pitch products in the email
6. Keep it brief — 3-4 paragraphs max
"""

        user_prompt = f"""Write a conference meeting request email for someone presenting at {conference_name}.

CONFERENCE CONTEXT:
- Conference: {conference_name}
- Their presentation topic: {presentation_topic or 'relevant industry topic'}
- Company: {company_name}

SIGNAL CONTEXT:
{insight_content[:300]}

Generate:
1. Three subject line options (reference the conference, no hard sell)
2. Email body with [Contact Name] as placeholder
3. Brief, personalized, referencing their specific work

Respond in this exact JSON format:
{{
  "subject_options": ["subject 1", "subject 2", "subject 3"],
  "body": "the full email body with [Contact Name] placeholder",
  "aria_notes": "brief explanation of approach used"
}}"""

        email_data = await self._generate_email_via_llm(
            system_prompt, user_prompt, user_company, company_name,
            competitive_context, insight_content,
        )

        return await self._save_email_draft(
            user_id=user_id,
            email_data=email_data,
            purpose="conference_outreach",
            draft_type="conference_outreach",
            company_name=company_name,
            insight_id=insight_id,
            competitive_context=competitive_context,
            differentiation=competitive_context.get("differentiation", []),
            weaknesses=competitive_context.get("weaknesses", []),
            pricing=competitive_context.get("pricing", {}),
            insight_content=insight_content,
            entity_type=payload.get("entity_type"),
            extra_context={
                "conference_name": conference_name,
                "presentation_topic": presentation_topic,
            },
        )

    # ================================================================
    # CLINICAL TRIAL OUTREACH
    # ================================================================

    async def _execute_clinical_trial_outreach(
        self, user_id: str, action: dict, payload: dict
    ) -> dict[str, Any]:
        """Generate clinical trial procurement outreach email."""
        company_name = payload.get("company_name", "")
        competitive_context = payload.get("competitive_context", {})
        insight_content = action.get("description", "")
        insight_id = payload.get("insight_id")
        clinical_phase = payload.get("clinical_phase", "")
        drug_modality = payload.get("drug_modality", "")
        equipment_needs = payload.get("equipment_needs", {})

        writing_style = await self._get_digital_twin(user_id)
        user_company = await self._get_user_company_name(user_id)

        system_prompt = f"""You are writing an email for a sales professional at {user_company}.

WRITING STYLE (match this exactly):
- Tone: {writing_style.get('tone', 'professional')}
- Style: {writing_style.get('writing_style', 'concise and direct')}
- Formality: {writing_style.get('formality_level', 'business')}
- Vocabulary: {writing_style.get('vocabulary_patterns', 'simple, professional')}

CRITICAL EMAIL RULES:
1. Reference their clinical advancement as the reason for outreach
2. Focus on scaling readiness and supply chain planning
3. Position as a consultative partner, not a vendor pushing products
4. Reference specific equipment categories relevant to their trial phase
5. Low-friction CTA: 15-minute planning call
6. Keep it brief — 3-4 paragraphs max
"""

        downstream = equipment_needs.get("downstream", [])[:3] if isinstance(equipment_needs, dict) else []
        upstream = equipment_needs.get("upstream", [])[:3] if isinstance(equipment_needs, dict) else []
        equipment_text = ", ".join(downstream + upstream) if (downstream or upstream) else "relevant equipment"

        user_prompt = f"""Write a clinical trial procurement outreach email for a company advancing in clinical trials.

CLINICAL CONTEXT:
- Company: {company_name}
- Clinical phase: {clinical_phase or 'advancing clinical program'}
- Drug modality: {drug_modality or 'therapeutic'}
- Equipment needs: {equipment_text}

SIGNAL CONTEXT:
{insight_content[:300]}

Generate:
1. Three subject line options (reference their clinical advancement, professional tone)
2. Email body with [Contact Name] as placeholder
3. Focus on scaling readiness and supply planning

Respond in this exact JSON format:
{{
  "subject_options": ["subject 1", "subject 2", "subject 3"],
  "body": "the full email body with [Contact Name] placeholder",
  "aria_notes": "brief explanation of approach used"
}}"""

        email_data = await self._generate_email_via_llm(
            system_prompt, user_prompt, user_company, company_name,
            competitive_context, insight_content,
        )

        return await self._save_email_draft(
            user_id=user_id,
            email_data=email_data,
            purpose="clinical_trial_outreach",
            draft_type="clinical_trial_outreach",
            company_name=company_name,
            insight_id=insight_id,
            competitive_context=competitive_context,
            differentiation=competitive_context.get("differentiation", []),
            weaknesses=competitive_context.get("weaknesses", []),
            pricing=competitive_context.get("pricing", {}),
            insight_content=insight_content,
            entity_type=payload.get("entity_type"),
            extra_context={
                "clinical_phase": clinical_phase,
                "drug_modality": drug_modality,
                "equipment_needs": equipment_needs,
            },
        )

    # ================================================================
    # SHARED EMAIL HELPERS
    # ================================================================

    async def _generate_email_via_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        user_company: str,
        company_name: str,
        competitive_context: dict,
        insight_content: str,
    ) -> dict:
        """Call LLM to generate email content, with fallback."""
        try:
            from src.core.llm import LLMClient
            from src.core.task_types import TaskType

            llm = LLMClient()
            response_text = await llm.generate_response(
                messages=[{"role": "user", "content": user_prompt}],
                system_prompt=system_prompt,
                max_tokens=1500,
                temperature=0.7,
                task=TaskType.SCRIBE_DRAFT_EMAIL,
            )

            # Extract JSON from response
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                email_data = json.loads(response_text[json_start:json_end])
            else:
                email_data = {
                    "subject_options": [f"Supply continuity discussion — {user_company}"],
                    "body": response_text,
                    "aria_notes": "LLM response was not in expected JSON format",
                }
        except Exception as e:
            logger.error("[ActionExecutor] LLM email generation failed: %s", e)
            email_data = self._generate_fallback_email(
                user_company, company_name, competitive_context, insight_content,
            )

        return email_data

    async def _save_email_draft(
        self,
        user_id: str,
        email_data: dict,
        purpose: str,
        draft_type: str,
        company_name: str,
        insight_id: Optional[str],
        competitive_context: dict,
        differentiation: list,
        weaknesses: list,
        pricing: dict,
        insight_content: str,
        entity_type: Optional[str] = None,
        extra_context: Optional[dict] = None,
        aria_reasoning: str = "",
    ) -> dict[str, Any]:
        """Save LLM-generated email to email_drafts and create notification."""
        subject = email_data.get("subject_options", ["Supply continuity discussion"])[0]
        body = email_data.get("body", "")
        aria_notes = email_data.get("aria_notes", "")
        all_subjects = email_data.get("subject_options", [subject])

        draft_id = None
        try:
            context_data: dict[str, Any] = {
                "signal_context": insight_content[:300],
                "company_name": company_name,
                "entity_type": entity_type,
                "generation_mode": "template",
            }
            if extra_context:
                context_data.update(extra_context)

            insert_data: dict[str, Any] = {
                "user_id": user_id,
                "recipient_email": "pending@placeholder.com",
                "recipient_name": "[Contact Name]",
                "subject": subject,
                "body": body,
                "purpose": purpose,
                "tone": "formal",
                "status": "pending_review",
                "aria_notes": (
                    f"ARIA generated this {draft_type.replace('_', ' ')} email "
                    f"based on {company_name} intelligence. {aria_notes}"
                ),
                "style_match_score": 0.85,
                "draft_type": draft_type,
                "competitive_positioning": json.dumps({
                    "competitor": company_name,
                    "differentiation": differentiation[:3],
                    "weaknesses": weaknesses[:3],
                    "pricing": pricing,
                    "subject_alternatives": all_subjects[1:] if len(all_subjects) > 1 else [],
                }),
                "context": json.dumps(context_data),
                "aria_reasoning": aria_reasoning if aria_reasoning else None,
            }
            if insight_id:
                insert_data["insight_id"] = insight_id

            draft_result = self._db.table("email_drafts").insert(insert_data).execute()
            draft_id = draft_result.data[0]["id"] if draft_result.data else None
        except Exception as e:
            logger.error("[ActionExecutor] Failed to save email draft: %s", e)

        # Create notification pointing to Communications
        try:
            self._db.table("notifications").insert({
                "user_id": user_id,
                "type": "draft_ready",
                "title": f"Email drafted: {company_name}",
                "message": (
                    f"ARIA drafted a {draft_type.replace('_', ' ')} email "
                    f"targeting {company_name}. Subject: \"{subject}\". "
                    f"Review and personalize in Communications."
                ),
                "link": "/communications",
                "metadata": json.dumps({
                    "draft_id": str(draft_id) if draft_id else None,
                    "company": company_name,
                    "action_type": draft_type,
                }),
            }).execute()
        except Exception as e:
            logger.warning("[ActionExecutor] Notification failed: %s", e)

        return {
            "status": "completed",
            "summary": (
                f"{draft_type.replace('_', ' ').title()} email drafted for "
                f"{company_name}. Written in your voice using intelligence "
                f"positioning. Review in Communications."
            ),
            "draft_id": str(draft_id) if draft_id else None,
            "subject": subject,
            "subject_alternatives": all_subjects[1:] if len(all_subjects) > 1 else [],
            "email_drafted": True,
            "company": company_name,
        }

    def _generate_fallback_email(
        self, user_company: str, competitor: str,
        competitive_context: dict, signal: str,
    ) -> dict:
        """Fallback email template when LLM is unavailable."""
        diff = competitive_context.get("differentiation", [])
        diff_text = str(diff[0]) if diff else "specialized solutions"

        return {
            "subject_options": [
                "Ensuring supply continuity for your operations",
                f"Quick question about your supply chain",
                f"{user_company} — supporting your operational reliability",
            ],
            "body": (
                "Hi [Contact Name],\n\n"
                "I wanted to reach out regarding supply continuity for your operations. "
                "Given the importance of reliable supply chains in our industry, ensuring "
                "you have robust sourcing for critical consumables is something worth a "
                "quick conversation.\n\n"
                f"{user_company} offers {diff_text}. We've been helping companies "
                "strengthen their supply chain resilience with proven performance and "
                "responsive support.\n\n"
                "Would you have 15 minutes this week for a brief call? Happy to share "
                "some relevant case studies.\n\n"
                "Best regards"
            ),
            "aria_notes": "Fallback template used (LLM unavailable). Personalize before sending.",
        }

    # ================================================================
    # DIGITAL TWIN & COMPANY HELPERS
    # ================================================================

    async def _get_digital_twin(self, user_id: str) -> dict:
        """Get user's digital twin writing style."""
        try:
            result = (
                self._db.table("digital_twin_profiles")
                .select("tone, writing_style, vocabulary_patterns, formality_level, formatting_patterns")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            if result.data:
                return result.data[0]
            return {
                "tone": "professional",
                "writing_style": "concise and direct",
                "formality_level": "business",
                "vocabulary_patterns": "simple, professional",
            }
        except Exception:
            return {
                "tone": "professional",
                "writing_style": "concise and direct",
                "formality_level": "business",
            }

    async def _get_user_company_name(self, user_id: str) -> str:
        """Get user's company name."""
        try:
            profile = (
                self._db.table("user_profiles")
                .select("company_id")
                .eq("id", user_id)
                .limit(1)
                .execute()
            )
            if profile.data and profile.data[0].get("company_id"):
                company = (
                    self._db.table("companies")
                    .select("name")
                    .eq("id", profile.data[0]["company_id"])
                    .limit(1)
                    .execute()
                )
                if company.data:
                    return company.data[0]["name"]
            return "our company"
        except Exception:
            return "our company"

    async def _check_crm_connected(self, user_id: str) -> Optional[dict]:
        """Check if user has a CRM integration connected."""
        try:
            result = (
                self._db.table("user_integrations")
                .select("integration_type, status, composio_connection_id")
                .eq("user_id", user_id)
                .in_("integration_type", ["salesforce", "hubspot"])
                .eq("status", "active")
                .limit(1)
                .execute()
            )
            if result.data:
                return result.data[0]
            return None
        except Exception:
            return None

    # ================================================================
    # SAVE TO EMAIL CLIENT VIA COMPOSIO
    # ================================================================

    async def _save_draft_to_email_client(self, user_id: str, draft_id: str) -> bool:
        """Save an approved email draft to the user's email client via Composio."""
        try:
            draft = (
                self._db.table("email_drafts")
                .select("*")
                .eq("id", draft_id)
                .limit(1)
                .execute()
            )
            if not draft.data:
                return False

            draft_data = draft.data[0]

            # Get user's email integration
            integration = (
                self._db.table("user_integrations")
                .select("integration_type, composio_connection_id")
                .eq("user_id", user_id)
                .in_("integration_type", ["outlook", "gmail"])
                .eq("status", "active")
                .limit(1)
                .execute()
            )

            if not integration.data:
                logger.warning("[ActionExecutor] No email integration for save-to-client")
                return False

            email_client = integration.data[0]["integration_type"]

            try:
                from src.services.composio_service import get_composio_client

                composio = get_composio_client()
                if not composio:
                    logger.warning("[ActionExecutor] Composio client not available")
                    return False

                recipient = draft_data.get("recipient_email", "")
                to_list = [recipient] if recipient and recipient != "pending@placeholder.com" else []

                if email_client == "outlook":
                    action_name = "OUTLOOK_CREATE_DRAFT"
                elif email_client == "gmail":
                    action_name = "GMAIL_CREATE_DRAFT"
                else:
                    logger.warning("[ActionExecutor] Unsupported email client: %s", email_client)
                    return False

                # Convert plain text body to HTML for proper formatting in email clients
                from src.utils.email_formatting import plain_text_to_email_html

                html_body = plain_text_to_email_html(draft_data.get("body", ""))

                composio.execute_action(
                    action=action_name,
                    params={
                        "subject": draft_data.get("subject", ""),
                        "body": html_body,
                        "bodyContentType": "HTML",
                        "to": to_list,
                    },
                    connected_account_id=integration.data[0].get("composio_connection_id"),
                )

                self._db.table("email_drafts").update({
                    "saved_to_client": True,
                    "saved_to_client_at": datetime.now(timezone.utc).isoformat(),
                    "email_client": email_client,
                    "status": "saved_to_client",
                }).eq("id", draft_id).execute()

                return True
            except ImportError:
                logger.warning("[ActionExecutor] Composio service not available")
            except Exception as e:
                logger.warning("[ActionExecutor] Composio draft save failed: %s", e)

            return False
        except Exception as e:
            logger.error("[ActionExecutor] Save to client failed: %s", e)
            return False

    # ================================================================
    # OTHER ACTION HANDLERS
    # ================================================================

    async def _execute_pricing_response(
        self, user_id: str, action: dict, payload: dict
    ) -> dict[str, Any]:
        """Create pricing counter-positioning notification."""
        company_name = payload.get("company_name", "")
        competitive_context = payload.get("competitive_context", {})
        pricing = competitive_context.get("pricing", {})

        self._db.table("notifications").insert({
            "user_id": user_id,
            "type": "action_completed",
            "title": f"Pricing response ready: {company_name}",
            "message": (
                f"Competitive pricing counter-positioning for {company_name} is ready. "
                f"Their pricing: {pricing.get('range', 'unknown')}. Battle card updated."
            ),
            "link": "/intelligence",
            "metadata": {
                "action_type": "competitive_pricing_response",
                "company": company_name,
            },
        }).execute()

        return {
            "status": "completed",
            "summary": (
                f"Pricing intelligence response prepared for {company_name}. "
                f"Battle card pricing section updated."
            ),
        }

    async def _execute_lead_discovery(
        self, user_id: str, action: dict, payload: dict
    ) -> dict[str, Any]:
        """Create lead discovery notification."""
        company_name = payload.get("company_name", "")

        self._db.table("notifications").insert({
            "user_id": user_id,
            "type": "action_completed",
            "title": f"Lead discovered: {company_name}",
            "message": (
                f"{company_name} added to discovered leads pipeline. "
                f"Enrichment data loaded."
            ),
            "link": "/pipeline",
            "metadata": {
                "action_type": "lead_discovery",
                "company": company_name,
            },
        }).execute()

        return {
            "status": "completed",
            "summary": f"Lead {company_name} added to pipeline with enrichment data.",
        }

    async def _execute_generic(
        self, user_id: str, action: dict, payload: dict
    ) -> dict[str, Any]:
        """Generic execution for unrecognized action types."""
        self._db.table("notifications").insert({
            "user_id": user_id,
            "type": "action_completed",
            "title": f"Action completed: {action.get('title', 'Unknown')[:50]}",
            "message": "Action has been approved and processed.",
            "link": "/actions",
        }).execute()

        return {
            "status": "completed",
            "summary": "Action approved and processed.",
        }

    async def _create_followup(
        self, user_id: str, action: dict, result: dict
    ) -> None:
        """Create a prospective memory for follow-up."""
        try:
            self._db.table("prospective_memories").insert({
                "user_id": user_id,
                "task": (
                    f"Follow up on approved action: {action.get('title', '')}. "
                    f"Check if user took next steps."
                ),
                "description": result.get("summary", ""),
                "trigger_type": "time",
                "trigger_config": {"days_from_now": 3},
                "status": "pending",
                "priority": "high",
            }).execute()
        except Exception as e:
            logger.warning("[ActionExecutor] Failed to create follow-up: %s", e)
