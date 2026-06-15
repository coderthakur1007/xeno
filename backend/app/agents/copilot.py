"""
Marketing Copilot Graph — 7-agent orchestration pipeline.

Agents:
1. CustomerIntelligenceAgent — analyses live customer purchase behaviour
2. SegmentationAgent — NL → segment SQL with rule-based compiler + optional LLM
3. ChannelOptimizationAgent — data-driven channel scoring from real delivery stats
4. StrategyAgent — campaign strategy from historical performance
5. ContentGenerationAgent — channel-native message variants via LLM / smart local
6. AnalyticsAgent — RFM / cohort / campaign insight generation
7. ExecutionAgent — pre-launch validation and readiness assessment
"""

from __future__ import annotations

import json
import logging
import math
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.agents.llm_client import LLMClient, _detect_intent, _hash_select
from app.agents.prompts import (
    SYSTEM_PROMPTS,
    build_analytics_prompt,
    build_channel_prompt,
    build_content_prompt,
    build_customer_intelligence_prompt,
    build_segmentation_prompt,
    build_strategy_prompt,
)
from app.services.segmentation import SegmentCompiler

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared data structures
# ---------------------------------------------------------------------------


@dataclass
class AgentResult:
    name: str
    output: dict[str, Any]
    rationale: str
    status: str = "success"
    duration_ms: int = 0


def _timed(fn):
    """Decorator that measures execution time and catches errors."""
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            result: AgentResult = fn(*args, **kwargs)
            result.duration_ms = int((time.perf_counter() - start) * 1000)
            return result
        except Exception as exc:
            duration = int((time.perf_counter() - start) * 1000)
            logger.exception("Agent %s failed", fn.__name__)
            return AgentResult(
                name=fn.__name__.replace("_run_", ""),
                output={},
                rationale=f"Agent error: {exc}",
                status="error",
                duration_ms=duration,
            )
    return wrapper


def _safe_json_parse(text_content: str) -> dict:
    """Try to parse JSON from LLM output, stripping markdown fences."""
    cleaned = text_content.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return {}


# ---------------------------------------------------------------------------
# Individual Agents
# ---------------------------------------------------------------------------


class CustomerIntelligenceAgent:
    """Agent 1: Query REAL customer data and generate behavioural insights."""

    def run(self, db: Session, tenant_id: uuid.UUID, goal: str, llm: LLMClient) -> AgentResult:
        # Query real aggregate stats
        row = db.execute(
            text("""
                SELECT
                  count(DISTINCT c.id)::int AS customers,
                  coalesce(avg(order_stats.orders), 0)::float AS avg_orders,
                  coalesce(avg(order_stats.spend), 0)::float AS avg_spend,
                  coalesce(avg(order_stats.recency), 0)::float AS avg_recency
                FROM customers c
                LEFT JOIN (
                  SELECT customer_id, count(*) orders, sum(total_amount) spend,
                    EXTRACT(days FROM now() - max(ordered_at)) recency
                  FROM orders WHERE tenant_id = :tenant_id AND status='paid' GROUP BY customer_id
                ) order_stats ON order_stats.customer_id = c.id
                WHERE c.tenant_id = :tenant_id
            """),
            {"tenant_id": tenant_id},
        ).mappings().one()
        stats = dict(row)

        # Top cities
        try:
            city_rows = db.execute(
                text("""
                    SELECT city, count(*)::int AS cnt
                    FROM customers
                    WHERE tenant_id = :tenant_id AND city IS NOT NULL
                    GROUP BY city ORDER BY cnt DESC LIMIT 5
                """),
                {"tenant_id": tenant_id},
            ).mappings().all()
            stats["top_cities"] = [r["city"] for r in city_rows]
        except Exception:
            stats["top_cities"] = []

        # Top categories
        try:
            cat_rows = db.execute(
                text("""
                    SELECT attributes->>'preferred_category' AS cat, count(*)::int AS cnt
                    FROM customers
                    WHERE tenant_id = :tenant_id
                      AND attributes->>'preferred_category' IS NOT NULL
                    GROUP BY cat ORDER BY cnt DESC LIMIT 5
                """),
                {"tenant_id": tenant_id},
            ).mappings().all()
            stats["top_categories"] = [r["cat"] for r in cat_rows]
        except Exception:
            stats["top_categories"] = []

        # Generate insights
        if llm.is_llm_available:
            prompt = build_customer_intelligence_prompt(stats)
            raw = llm.generate(prompt, system=SYSTEM_PROMPTS["customer_intelligence"])
            parsed = _safe_json_parse(raw)
            if parsed:
                stats["insights"] = parsed.get("insights", [])
                stats["summary"] = parsed.get("summary", "")
                stats["risk_factors"] = parsed.get("risk_factors", [])
                stats["opportunities"] = parsed.get("opportunities", [])

        # Local fallback for insights
        if "insights" not in stats:
            insights = []
            customers = stats.get("customers", 0)
            avg_spend = stats.get("avg_spend", 0)
            avg_orders = stats.get("avg_orders", 0)
            avg_recency = stats.get("avg_recency", 0)
            top_cities = stats.get("top_cities", [])

            insights.append(
                f"Customer base of {customers:,} with average spend of ₹{avg_spend:,.0f} "
                f"and {avg_orders:.1f} avg orders per customer."
            )
            if top_cities:
                insights.append(f"Highest customer concentration in {', '.join(top_cities[:3])}.")
            if avg_recency > 60:
                insights.append(
                    f"Average recency of {avg_recency:.0f} days suggests many customers are lapsing — "
                    "consider winback campaigns."
                )
            elif avg_recency < 15:
                insights.append(
                    f"Average recency of {avg_recency:.0f} days shows a highly active customer base."
                )
            else:
                insights.append(
                    f"Average recency of {avg_recency:.0f} days indicates moderate engagement."
                )
            if avg_orders > 3:
                insights.append("Strong repeat-purchase behaviour — loyalty and retention campaigns are well-suited.")
            elif avg_orders >= 1:
                insights.append("Moderate order frequency — second-purchase nudges could lift lifetime value.")
            if avg_spend > 15000:
                insights.append("High average spend indicates a premium customer segment.")

            stats["insights"] = insights
            stats["summary"] = insights[0] if insights else "Customer data analysed."

        return AgentResult(
            "customer_intelligence",
            stats,
            f"Analysed live customer purchase behaviour for goal: {goal}",
        )


class SegmentationAgent:
    """Agent 2: NL → SQL with existing SegmentCompiler + optional LLM refinement."""

    def run(self, db: Session, tenant_id: uuid.UUID, goal: str, llm: LLMClient) -> AgentResult:
        compiler = SegmentCompiler()
        plan = compiler.nl_to_sql(tenant_id, goal)

        # LLM refinement if available
        if llm.is_llm_available:
            try:
                prompt = build_segmentation_prompt(goal, plan.filters.get("rules", []))
                raw = llm.generate(prompt, system=SYSTEM_PROMPTS["segmentation"])
                parsed = _safe_json_parse(raw)
                if parsed and parsed.get("suggested_rules"):
                    # Merge any new rules the LLM suggests
                    existing_keys = {
                        (r["field"], r["operator"], str(r["value"]))
                        for r in plan.filters.get("rules", [])
                    }
                    for rule in parsed["suggested_rules"]:
                        key = (rule.get("field", ""), rule.get("operator", ""), str(rule.get("value", "")))
                        if key not in existing_keys:
                            from app.services.segmentation import ALLOWED_FIELDS, OPERATORS
                            if rule.get("field") in ALLOWED_FIELDS and rule.get("operator") in OPERATORS:
                                plan.filters.setdefault("rules", []).append(rule)
                                existing_keys.add(key)
                    # Re-compile with merged rules
                    plan = compiler.visual_to_sql(tenant_id, plan.filters)
                    plan.explanation += " (LLM-refined)"
            except Exception as exc:
                logger.warning("LLM segmentation refinement failed: %s", exc)

        return AgentResult(
            "segmentation",
            {
                "sql_text": plan.sql_text,
                "params": plan.params,
                "filters": plan.filters,
            },
            plan.explanation,
        )


class ChannelOptimizationAgent:
    """Agent 3: Data-driven channel scoring from real delivery stats."""

    def run(self, db: Session, tenant_id: uuid.UUID, goal: str, llm: LLMClient) -> AgentResult:
        # Query REAL delivery stats from communication_events
        try:
            channel_stats_rows = db.execute(
                text("""
                    SELECT
                      channel,
                      count(*)::int AS total_events,
                      count(*) FILTER (WHERE event_type = 'delivered')::int AS delivered,
                      count(*) FILTER (WHERE event_type IN ('opened', 'read'))::int AS opened,
                      count(*) FILTER (WHERE event_type = 'clicked')::int AS clicked,
                      count(*) FILTER (WHERE event_type = 'converted')::int AS converted,
                      count(*) FILTER (WHERE event_type = 'failed')::int AS failed,
                      count(*) FILTER (WHERE event_type = 'sent')::int AS sent
                    FROM communication_events
                    WHERE tenant_id = :tenant_id
                    GROUP BY channel
                """),
                {"tenant_id": tenant_id},
            ).mappings().all()
        except Exception:
            channel_stats_rows = []

        delivery_stats: dict[str, dict] = {}
        scores: dict[str, float] = {}

        for row in channel_stats_rows:
            ch = row["channel"]
            total = max(row["total_events"], 1)
            sent = max(row["sent"], 1)
            delivery_rate = row["delivered"] / sent if row["sent"] > 0 else 0.5
            open_rate = row["opened"] / max(row["delivered"], 1) if row["delivered"] > 0 else 0.0
            click_rate = row["clicked"] / max(row["opened"], 1) if row["opened"] > 0 else 0.0
            conversion_rate = row["converted"] / sent if row["sent"] > 0 else 0.0
            failure_rate = row["failed"] / sent if row["sent"] > 0 else 0.0

            delivery_stats[ch] = {
                "total_events": row["total_events"],
                "delivery_rate": delivery_rate,
                "open_rate": open_rate,
                "click_rate": click_rate,
                "conversion_rate": conversion_rate,
                "failure_rate": failure_rate,
            }

            # Composite score weighted by conversion impact
            score = (
                delivery_rate * 0.25
                + open_rate * 0.20
                + click_rate * 0.25
                + conversion_rate * 0.20
                - failure_rate * 0.10
            )
            scores[ch] = round(max(0.0, min(1.0, score)), 4)

        # If no data, use balanced defaults (not hardcoded preferences)
        if not scores:
            for ch in ["whatsapp", "email", "sms", "rcs"]:
                scores[ch] = 0.50
                delivery_stats[ch] = {
                    "total_events": 0,
                    "delivery_rate": 0.5,
                    "open_rate": 0.0,
                    "click_rate": 0.0,
                    "conversion_rate": 0.0,
                    "failure_rate": 0.0,
                }

        recommended = sorted(scores, key=scores.get, reverse=True)[:2]

        # LLM explanation
        rationale = "Ranked channels from observed delivery and engagement performance data."
        if llm.is_llm_available:
            try:
                prompt = build_channel_prompt(goal, list(scores.keys()), delivery_stats)
                raw = llm.generate(prompt, system=SYSTEM_PROMPTS["channel_optimization"])
                parsed = _safe_json_parse(raw)
                if parsed and parsed.get("explanation"):
                    rationale = parsed["explanation"]
            except Exception:
                pass
        else:
            # Data-driven local explanation
            if channel_stats_rows:
                best = recommended[0]
                best_stats = delivery_stats[best]
                rationale = (
                    f"Top channel '{best}' selected with "
                    f"{best_stats['delivery_rate']:.0%} delivery rate, "
                    f"{best_stats['open_rate']:.0%} open rate, "
                    f"and {best_stats['click_rate']:.0%} click rate "
                    f"based on {best_stats['total_events']} historical events."
                )
            else:
                rationale = "No historical delivery data — using balanced channel scores. Performance data will refine recommendations over time."

        return AgentResult(
            "channel_optimization",
            {
                "scores": scores,
                "recommended_channels": recommended,
                "delivery_stats": delivery_stats,
            },
            rationale,
        )


class StrategyAgent:
    """Agent 4: Campaign strategy from real historical data."""

    def run(
        self,
        db: Session,
        tenant_id: uuid.UUID,
        audience_size: int,
        intelligence: dict[str, Any],
        channels: list[str],
        goal: str,
        llm: LLMClient,
    ) -> AgentResult:
        # Query real campaign history
        historical: dict[str, Any] = {"campaign_count": 0, "avg_conversion_rate": 0.0, "best_channel": "N/A"}
        try:
            hist_row = db.execute(
                text("""
                    SELECT
                      count(DISTINCT c.id)::int AS campaign_count,
                      count(DISTINCT m.id)::int AS total_messages,
                      count(DISTINCT e.id) FILTER (WHERE e.event_type = 'converted')::int AS conversions
                    FROM campaigns c
                    LEFT JOIN messages m ON m.campaign_id = c.id
                    LEFT JOIN communication_events e ON e.campaign_id = c.id
                    WHERE c.tenant_id = :tenant_id
                """),
                {"tenant_id": tenant_id},
            ).mappings().one()
            historical["campaign_count"] = hist_row["campaign_count"]
            total_msgs = max(hist_row["total_messages"], 1)
            historical["avg_conversion_rate"] = hist_row["conversions"] / total_msgs
        except Exception:
            pass

        # Best channel from history
        try:
            best_ch_row = db.execute(
                text("""
                    SELECT channel,
                      count(*) FILTER (WHERE event_type = 'converted')::float /
                      GREATEST(count(*) FILTER (WHERE event_type = 'sent'), 1) AS conv_rate
                    FROM communication_events
                    WHERE tenant_id = :tenant_id
                    GROUP BY channel
                    ORDER BY conv_rate DESC LIMIT 1
                """),
                {"tenant_id": tenant_id},
            ).mappings().first()
            if best_ch_row:
                historical["best_channel"] = best_ch_row["channel"]
        except Exception:
            pass

        # Read admin settings for frequency cap, AB split, attribution
        frequency_cap = {"max_messages": 2, "window_days": 7}
        ab_test = {"enabled": True, "split": [50, 50], "success_metric": "conversion_rate"}
        attribution = "7_day_click_or_read_last_touch"

        try:
            settings_rows = db.execute(
                text("SELECT key, value FROM admin_settings WHERE tenant_id = :tenant_id"),
                {"tenant_id": tenant_id},
            ).mappings().all()
            for sr in settings_rows:
                if sr["key"] == "frequency_cap" and isinstance(sr["value"], dict):
                    frequency_cap.update(sr["value"])
                elif sr["key"] == "ab_test" and isinstance(sr["value"], dict):
                    ab_test.update(sr["value"])
                elif sr["key"] == "attribution_window" and isinstance(sr["value"], dict):
                    attribution = sr["value"].get("model", attribution)
        except Exception:
            pass

        # Calculate conversion probability from historical data
        if historical["avg_conversion_rate"] > 0:
            base = historical["avg_conversion_rate"]
        else:
            # Reasonable data-derived default from audience size
            base = min(0.35, 0.05 + math.log10(max(audience_size, 10)) / 30)

        # Adjust based on intent
        goal_lower = goal.lower()
        if any(kw in goal_lower for kw in ["inactive", "lapsed", "winback", "win back"]):
            base *= 0.85
        elif any(kw in goal_lower for kw in ["vip", "high value", "premium"]):
            base *= 1.15
        elif any(kw in goal_lower for kw in ["churn", "at risk"]):
            base *= 0.80

        base = min(base, 0.50)
        expected = round(audience_size * base)

        strategy = {
            "objective": goal,
            "send_window": "next_best_local_evening",
            "frequency_cap": frequency_cap,
            "ab_test": ab_test,
            "conversion_probability": round(base, 4),
            "expected_conversions": int(expected),
            "attribution": attribution,
            "channels": channels,
            "historical_data": historical,
        }

        # LLM narrative
        rationale = "Forecasted response from current audience size and historical customer value distribution."
        if llm.is_llm_available:
            try:
                prompt = build_strategy_prompt(
                    goal, audience_size,
                    {"channels": channels, "scores": {}},
                    historical,
                )
                raw = llm.generate(prompt, system=SYSTEM_PROMPTS["strategy"])
                parsed = _safe_json_parse(raw)
                if parsed:
                    strategy["narrative"] = parsed.get("narrative", "")
                    strategy["risks"] = parsed.get("risks", [])
                    strategy["optimizations"] = parsed.get("optimizations", [])
                    rationale = parsed.get("reasoning", rationale)
            except Exception:
                pass
        else:
            # Local narrative
            strategy["narrative"] = (
                f"For this {_detect_intent(goal)} campaign targeting {audience_size:,} customers, "
                f"we recommend sending via {' and '.join(channels)} during evening hours. "
                f"A/B test with {ab_test['split'][0]}/{ab_test['split'][1]} split on messaging angles. "
                f"Expected conversion rate: {base:.1%} ({expected:,} conversions)."
            )

        return AgentResult("campaign_strategy", strategy, rationale)


class ContentGenerationAgent:
    """Agent 5: Channel-native message variants via LLM or smart local templates."""

    def run(
        self,
        goal: str,
        channels: list[str],
        intelligence: dict[str, Any],
        strategy: dict[str, Any],
        llm: LLMClient,
    ) -> AgentResult:
        avg_spend = round(float(intelligence.get("avg_spend") or 0))
        intent = _detect_intent(goal)
        variants = []

        if llm.is_llm_available:
            try:
                prompt = build_content_prompt(goal, channels, intelligence, strategy)
                raw = llm.generate(prompt, system=SYSTEM_PROMPTS["content_generation"], max_tokens=2048)
                parsed = _safe_json_parse(raw)
                if parsed and parsed.get("variants"):
                    llm_variants = parsed["variants"]
                    for v in llm_variants:
                        v.setdefault("personalization_tokens", [
                            "first_name", "last_product_category", "city", "recommended_offer"
                        ])
                    variants = llm_variants
            except Exception as exc:
                logger.warning("LLM content generation failed: %s", exc)

        # Local fallback / supplement
        if not variants:
            variants = self._generate_local_variants(goal, channels, intent, avg_spend)

        return AgentResult(
            "content_generation",
            {"variants": variants},
            f"Generated {len(variants)} channel-native variants with runtime personalization tokens.",
        )

    def _generate_local_variants(
        self,
        goal: str,
        channels: list[str],
        intent: str,
        avg_spend: int,
    ) -> list[dict]:
        """Generate variants using the smart template system."""
        from app.agents.llm_client import (
            _BODY_TEMPLATES_BY_INTENT,
            _CTAS_BY_INTENT,
            _EMAIL_SUBJECTS_BY_INTENT,
            _EMAIL_TEMPLATES,
            _EMOJI_SETS,
            _GREETINGS,
            _RCS_TEMPLATES,
            _SMS_TEMPLATES,
            _URGENCY_PHRASES,
            _WHATSAPP_TEMPLATES,
        )

        angles = [intent, f"{intent}_alternate", f"{intent}_creative"]
        variants = []

        for var_idx, angle in enumerate(angles):
            content: dict[str, dict] = {}
            for channel in channels:
                greeting = _hash_select(goal, _GREETINGS, var_idx)
                cta = _hash_select(goal, _CTAS_BY_INTENT.get(intent, _CTAS_BY_INTENT["default"]), var_idx)
                emoji = _hash_select(goal, _EMOJI_SETS.get(intent, _EMOJI_SETS["default"]), var_idx)
                urgency = _hash_select(goal, _URGENCY_PHRASES, var_idx)
                body = _hash_select(
                    goal,
                    _BODY_TEMPLATES_BY_INTENT.get(intent, _BODY_TEMPLATES_BY_INTENT["default"]),
                    var_idx,
                )

                template_map = {
                    "whatsapp": _WHATSAPP_TEMPLATES,
                    "email": _EMAIL_TEMPLATES,
                    "sms": _SMS_TEMPLATES,
                    "rcs": _RCS_TEMPLATES,
                }
                templates = template_map.get(channel, _WHATSAPP_TEMPLATES)
                template = _hash_select(goal, templates, var_idx)

                rendered = template.format(
                    greeting=greeting,
                    cta=cta,
                    emoji=emoji,
                    urgency=urgency,
                    body=body,
                )

                subject = None
                if channel == "email":
                    subject = _hash_select(
                        goal,
                        _EMAIL_SUBJECTS_BY_INTENT.get(intent, _EMAIL_SUBJECTS_BY_INTENT["default"]),
                        var_idx,
                    )

                content[channel] = {
                    "subject": subject,
                    "body": rendered,
                    "cta": cta,
                }

            variants.append({
                "key": f"variant_{var_idx + 1}",
                "angle": angle,
                "channels": channels,
                "personalization_tokens": [
                    "first_name", "last_product_category", "city", "recommended_offer"
                ],
                "content": content,
                "why": (
                    f"Uses lifecycle intent from '{goal}' "
                    f"and average customer value around ₹{avg_spend:,}."
                ),
            })

        return variants


class AnalyticsAgent:
    """Agent 6: RFM, cohort, and campaign performance insights."""

    def run(self, db: Session, tenant_id: uuid.UUID, llm: LLMClient) -> AgentResult:
        # Query RFM distribution
        rfm_summary: dict[str, Any] = {}
        try:
            rfm_row = db.execute(
                text("""
                    SELECT
                      count(*)::int AS total,
                      coalesce(avg(EXTRACT(days FROM now() - max_ordered)), 0)::float AS avg_recency,
                      coalesce(avg(freq), 0)::float AS avg_frequency,
                      coalesce(avg(monetary), 0)::float AS avg_monetary,
                      count(*) FILTER (WHERE monetary > 10000)::int AS high_value_count
                    FROM (
                      SELECT c.id,
                        max(o.ordered_at) AS max_ordered,
                        count(o.id) AS freq,
                        coalesce(sum(o.total_amount), 0) AS monetary
                      FROM customers c
                      LEFT JOIN orders o ON o.customer_id = c.id AND o.status = 'paid'
                      WHERE c.tenant_id = :tenant_id
                      GROUP BY c.id
                    ) sub
                """),
                {"tenant_id": tenant_id},
            ).mappings().one()
            rfm_summary = dict(rfm_row)
        except Exception:
            rfm_summary = {"total": 0, "avg_recency": 0, "avg_frequency": 0, "avg_monetary": 0, "high_value_count": 0}

        # Cohort trends
        cohort_summary: dict[str, Any] = {}
        try:
            cohort_rows = db.execute(
                text("""
                    WITH first_orders AS (
                      SELECT customer_id, date_trunc('month', min(ordered_at)) cohort_month
                      FROM orders WHERE tenant_id = :tenant_id AND status='paid' GROUP BY customer_id
                    )
                    SELECT count(DISTINCT cohort_month)::int AS total_cohorts,
                      avg(CASE WHEN retained > 0 THEN 1.0 ELSE 0.0 END)::float AS avg_retention
                    FROM (
                      SELECT f.cohort_month,
                        count(*) FILTER (WHERE EXISTS (
                          SELECT 1 FROM orders o WHERE o.customer_id = f.customer_id
                          AND o.ordered_at >= f.cohort_month + interval '30 days'
                        )) AS retained
                      FROM first_orders f
                      GROUP BY f.cohort_month
                    ) sub
                """),
                {"tenant_id": tenant_id},
            ).mappings().one()
            cohort_summary = dict(cohort_rows)
            cohort_summary.setdefault("trend", "stable")
        except Exception:
            cohort_summary = {"total_cohorts": 0, "avg_retention": 0.0, "trend": "stable"}

        # Recent campaign performance
        campaign_summary: dict[str, Any] = {}
        try:
            camp_row = db.execute(
                text("""
                    SELECT
                      count(DISTINCT c.id)::int AS total,
                      count(DISTINCT m.id)::int AS total_sent,
                      count(DISTINCT e.id) FILTER (WHERE e.event_type = 'converted')::int AS conversions
                    FROM campaigns c
                    LEFT JOIN messages m ON m.campaign_id = c.id
                    LEFT JOIN communication_events e ON e.campaign_id = c.id
                    WHERE c.tenant_id = :tenant_id
                """),
                {"tenant_id": tenant_id},
            ).mappings().one()
            campaign_summary = dict(camp_row)
            sent = max(campaign_summary.get("total_sent", 0), 1)
            campaign_summary["conversion_rate"] = campaign_summary.get("conversions", 0) / sent
        except Exception:
            campaign_summary = {"total": 0, "total_sent": 0, "conversions": 0, "conversion_rate": 0.0}

        metrics = {
            "rfm_summary": rfm_summary,
            "cohort_summary": cohort_summary,
            "campaign_summary": campaign_summary,
        }

        # Generate insights
        analytics_insights: list[str] = []
        if llm.is_llm_available:
            try:
                prompt = build_analytics_prompt(metrics)
                raw = llm.generate(prompt, system=SYSTEM_PROMPTS["analytics"])
                parsed = _safe_json_parse(raw)
                if parsed and parsed.get("insights"):
                    analytics_insights = parsed["insights"]
            except Exception:
                pass

        if not analytics_insights:
            # Local pattern detection
            avg_recency = rfm_summary.get("avg_recency", 0)
            avg_frequency = rfm_summary.get("avg_frequency", 0)
            avg_monetary = rfm_summary.get("avg_monetary", 0)
            hv_count = rfm_summary.get("high_value_count", 0)
            total = rfm_summary.get("total", 0)
            retention = cohort_summary.get("avg_retention", 0)
            conv_rate = campaign_summary.get("conversion_rate", 0)

            if total > 0 and hv_count / max(total, 1) > 0.15:
                analytics_insights.append(
                    f"{hv_count} high-value customers ({hv_count / total:.0%} of base) — "
                    "consider VIP loyalty programs to retain this segment."
                )
            if avg_recency > 45:
                analytics_insights.append(
                    f"Average recency of {avg_recency:.0f} days signals declining engagement — "
                    "launch targeted winback campaigns."
                )
            if retention > 0 and retention < 0.3:
                analytics_insights.append(
                    f"30-day retention rate of {retention:.0%} is below optimal — "
                    "invest in post-purchase nurture sequences."
                )
            elif retention >= 0.3:
                analytics_insights.append(
                    f"Healthy 30-day retention of {retention:.0%} — maintain momentum with loyalty rewards."
                )
            if conv_rate > 0 and conv_rate < 0.02:
                analytics_insights.append(
                    f"Campaign conversion rate of {conv_rate:.1%} suggests room for optimisation — "
                    "test different messaging angles and send times."
                )
            if avg_monetary > 0:
                analytics_insights.append(
                    f"Average customer monetary value of ₹{avg_monetary:,.0f} — "
                    "segment by spend tiers for targeted offers."
                )

            if not analytics_insights:
                analytics_insights.append(
                    "Insufficient historical data for pattern detection. "
                    "Insights will improve as more campaigns are executed."
                )

        return AgentResult(
            "analytics",
            {**metrics, "insights": analytics_insights},
            f"Generated {len(analytics_insights)} actionable insights from RFM, cohort, and campaign data.",
        )


class ExecutionAgent:
    """Agent 7: Pre-launch validation and readiness assessment."""

    def run(
        self,
        db: Session,
        tenant_id: uuid.UUID,
        audience_size: int,
        channels: list[str],
        variants: list[dict],
        strategy: dict,
    ) -> AgentResult:
        checks = []
        blockers = []
        recommendations = []

        # Check 1: Audience has members
        if audience_size > 0:
            checks.append({"check": "audience_size", "status": "pass", "detail": f"{audience_size:,} customers in segment"})
        else:
            checks.append({"check": "audience_size", "status": "fail", "detail": "Segment has 0 customers"})
            blockers.append("No customers match the segment criteria.")

        # Check 2: Channels are valid
        valid_channels = {"whatsapp", "sms", "email", "rcs"}
        invalid = [ch for ch in channels if ch not in valid_channels]
        if not invalid and channels:
            checks.append({"check": "channels_valid", "status": "pass", "detail": f"Channels: {', '.join(channels)}"})
        elif invalid:
            checks.append({"check": "channels_valid", "status": "fail", "detail": f"Invalid channels: {', '.join(invalid)}"})
            blockers.append(f"Invalid channels detected: {', '.join(invalid)}")
        else:
            checks.append({"check": "channels_valid", "status": "fail", "detail": "No channels selected"})
            blockers.append("No channels selected for the campaign.")

        # Check 3: Content exists for all channels
        if variants:
            content_channels = set()
            for v in variants:
                content_channels.update(v.get("content", {}).keys())
            missing = set(channels) - content_channels
            if not missing:
                checks.append({"check": "content_coverage", "status": "pass", "detail": f"Content exists for all {len(channels)} channels"})
            else:
                checks.append({"check": "content_coverage", "status": "warn", "detail": f"Missing content for: {', '.join(missing)}"})
                recommendations.append(f"Create content for missing channels: {', '.join(missing)}")
        else:
            checks.append({"check": "content_coverage", "status": "fail", "detail": "No content variants generated"})
            blockers.append("No message variants available.")

        # Check 4: AB test validity
        ab_test = strategy.get("ab_test", {})
        if ab_test.get("enabled"):
            split = ab_test.get("split", [])
            if split and sum(split) == 100:
                checks.append({"check": "ab_test_config", "status": "pass", "detail": f"A/B split: {split}"})
            else:
                checks.append({"check": "ab_test_config", "status": "warn", "detail": f"A/B split {split} doesn't sum to 100"})
                recommendations.append("Adjust A/B test splits to sum to 100%.")

        # Check 5: Feature flags
        autonomous = False
        try:
            ff_row = db.execute(
                text("SELECT enabled FROM feature_flags WHERE tenant_id = :tenant_id AND key = 'ai_autonomous_execution'"),
                {"tenant_id": tenant_id},
            ).mappings().first()
            if ff_row:
                autonomous = ff_row["enabled"]
        except Exception:
            pass

        if autonomous:
            checks.append({"check": "autonomous_execution", "status": "pass", "detail": "AI autonomous execution enabled"})
        else:
            checks.append({"check": "autonomous_execution", "status": "warn", "detail": "Autonomous execution disabled — manual approval required"})
            recommendations.append("Enable 'ai_autonomous_execution' feature flag for automated campaign launch.")

        # Check 6: Estimated execution time
        est_minutes = max(1, audience_size // 500)
        checks.append({"check": "execution_time", "status": "pass", "detail": f"Estimated execution: ~{est_minutes} minute(s)"})

        ready = len(blockers) == 0

        return AgentResult(
            "execution",
            {
                "ready": ready,
                "checks": checks,
                "blockers": blockers,
                "recommendations": recommendations,
                "autonomous_execution": autonomous,
            },
            f"Execution readiness: {'READY' if ready else 'BLOCKED'} — {len(checks)} checks performed.",
        )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class MarketingCopilotGraph:
    """Orchestrates the 7-agent pipeline for campaign planning."""

    def __init__(self, db: Session, tenant_id: str | None = None, settings=None):
        self.db = db
        self.tenant_id = tenant_id
        if settings is None:
            from app.core.config import get_settings
            settings = get_settings()
        self.llm = LLMClient(
            provider=getattr(settings, "llm_provider", "local"),
            gemini_key=getattr(settings, "gemini_api_key", ""),
            openai_key=getattr(settings, "openai_api_key", ""),
        )

    def plan(self, tenant_id: uuid.UUID, goal: str, audience_size: int | None = None) -> dict[str, Any]:
        """Run the full 7-agent pipeline and return a comprehensive campaign plan."""
        agents_log: list[dict] = []

        # Agent 1: Customer Intelligence
        ci_agent = CustomerIntelligenceAgent()
        intelligence = ci_agent.run(self.db, tenant_id, goal, self.llm)
        agents_log.append({"name": intelligence.name, "status": intelligence.status, "duration_ms": intelligence.duration_ms})

        # Agent 2: Segmentation
        seg_agent = SegmentationAgent()
        segmentation = seg_agent.run(self.db, tenant_id, goal, self.llm)
        agents_log.append({"name": segmentation.name, "status": segmentation.status, "duration_ms": segmentation.duration_ms})

        # Compute audience size if not provided
        if audience_size is None:
            try:
                audience_size = int(
                    self.db.execute(
                        text(f"SELECT count(*) FROM ({segmentation.output['sql_text']}) a"),
                        segmentation.output["params"],
                    ).scalar_one()
                )
            except Exception:
                audience_size = 0

        # Agent 3: Channel Optimization
        ch_agent = ChannelOptimizationAgent()
        channel = ch_agent.run(self.db, tenant_id, goal, self.llm)
        agents_log.append({"name": channel.name, "status": channel.status, "duration_ms": channel.duration_ms})

        recommended_channels = channel.output.get("recommended_channels", ["whatsapp", "email"])

        # Agent 4: Strategy
        strat_agent = StrategyAgent()
        strategy = strat_agent.run(
            self.db, tenant_id, audience_size, intelligence.output,
            recommended_channels, goal, self.llm,
        )
        agents_log.append({"name": strategy.name, "status": strategy.status, "duration_ms": strategy.duration_ms})

        # Agent 5: Content Generation
        content_agent = ContentGenerationAgent()
        content = content_agent.run(goal, recommended_channels, intelligence.output, strategy.output, self.llm)
        agents_log.append({"name": content.name, "status": content.status, "duration_ms": content.duration_ms})

        # Agent 6: Analytics
        analytics_agent = AnalyticsAgent()
        analytics = analytics_agent.run(self.db, tenant_id, self.llm)
        agents_log.append({"name": analytics.name, "status": analytics.status, "duration_ms": analytics.duration_ms})

        # Agent 7: Execution Readiness
        exec_agent = ExecutionAgent()
        execution = exec_agent.run(
            self.db, tenant_id, audience_size,
            recommended_channels,
            content.output.get("variants", []),
            strategy.output,
        )
        agents_log.append({"name": execution.name, "status": execution.status, "duration_ms": execution.duration_ms})

        return {
            "goal": goal,
            "audience_size": audience_size,
            "conversion_probability": strategy.output.get("conversion_probability", 0),
            "expected_conversions": strategy.output.get("expected_conversions", 0),
            "recommended_channels": recommended_channels,
            "strategy": strategy.output,
            "variants": content.output.get("variants", []),
            "segment": segmentation.output,
            "customer_insights": {
                "summary": intelligence.output.get("summary", ""),
                "insights": intelligence.output.get("insights", []),
                "customers": intelligence.output.get("customers", 0),
                "avg_spend": intelligence.output.get("avg_spend", 0),
                "avg_orders": intelligence.output.get("avg_orders", 0),
                "avg_recency": intelligence.output.get("avg_recency", 0),
                "top_cities": intelligence.output.get("top_cities", []),
                "top_categories": intelligence.output.get("top_categories", []),
            },
            "analytics_insights": analytics.output.get("insights", []),
            "execution_readiness": execution.output,
            "explainability": [
                item.rationale for item in
                [intelligence, segmentation, channel, strategy, content, analytics, execution]
            ],
            "agents": agents_log,
        }
