import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domain.models import Segment
from app.infrastructure.repositories import SegmentRepository


ALLOWED_FIELDS = {
    "city": "c.city",
    "state": "c.state",
    "country": "c.country",
    "gender": "c.gender",
    "preferred_category": "c.attributes ->> 'preferred_category'",
    "loyalty_tier": "c.attributes ->> 'loyalty_tier'",
    "whatsapp_consent": "(c.consent ->> 'whatsapp')::boolean",
    "sms_consent": "(c.consent ->> 'sms')::boolean",
    "email_consent": "(c.consent ->> 'email')::boolean",
    "rcs_consent": "(c.consent ->> 'rcs')::boolean",
    "last_purchase_days": "EXTRACT(days FROM now() - max(o.ordered_at))",
    "first_purchase_days": "EXTRACT(days FROM now() - min(o.ordered_at))",
    "total_spend": "coalesce(sum(DISTINCT o.total_amount),0)",
    "order_count": "count(DISTINCT o.id)",
    "avg_order_value": "coalesce(avg(DISTINCT o.total_amount),0)",
    "engagement_count": "count(DISTINCT e.id)",
    "click_count": "count(DISTINCT e.id) FILTER (WHERE e.event_type = 'clicked')",
    "conversion_count": "count(DISTINCT e.id) FILTER (WHERE e.event_type = 'converted')",
    "failure_count": "count(DISTINCT e.id) FILTER (WHERE e.event_type = 'failed')",
    "last_engagement_days": "EXTRACT(days FROM now() - max(e.occurred_at))",
}
OPERATORS = {"eq": "=", "neq": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "contains": "ILIKE"}
AGGREGATE_FIELDS = {
    "last_purchase_days",
    "first_purchase_days",
    "total_spend",
    "order_count",
    "avg_order_value",
    "engagement_count",
    "click_count",
    "conversion_count",
    "failure_count",
    "last_engagement_days",
}
CATEGORY_TERMS = {
    "skincare": "skincare",
    "skin care": "skincare",
    "beauty": "skincare",
    "apparel": "apparel",
    "clothing": "apparel",
    "fashion": "apparel",
    "grocery": "grocery",
    "pantry": "grocery",
    "food": "grocery",
    "footwear": "footwear",
    "shoes": "footwear",
    "wellness": "wellness",
    "health": "wellness",
    "home": "home",
}
CITY_TERMS = ["mumbai", "delhi", "bangalore", "pune", "hyderabad", "chennai", "ahmedabad", "kolkata"]
LOYALTY_TERMS = ["bronze", "silver", "gold", "platinum"]


@dataclass
class SegmentPlan:
    sql_text: str
    params: dict[str, Any]
    filters: dict[str, Any]
    explanation: str


class SegmentCompiler:
    def visual_to_sql(self, tenant_id: uuid.UUID, filters: dict[str, Any]) -> SegmentPlan:
        clauses = ["c.tenant_id = :tenant_id"]
        having = []
        params: dict[str, Any] = {"tenant_id": tenant_id}
        for index, rule in enumerate(filters.get("rules", [])):
            field = rule.get("field")
            op = rule.get("operator")
            value = rule.get("value")
            if field not in ALLOWED_FIELDS or op not in OPERATORS:
                continue
            key = f"p{index}"
            target = ALLOWED_FIELDS[field]
            operator = OPERATORS[op]
            if op == "contains":
                params[key] = f"%{value}%"
            else:
                params[key] = value
            clause = f"{target} {operator} :{key}"
            if field in AGGREGATE_FIELDS:
                having.append(clause)
            else:
                clauses.append(clause)
        sql = (
            "SELECT c.id FROM customers c "
            "LEFT JOIN orders o ON o.customer_id = c.id "
            "LEFT JOIN communication_events e ON e.customer_id = c.id "
            f"WHERE {' AND '.join(clauses)} GROUP BY c.id"
        )
        if having:
            sql += f" HAVING {' AND '.join(having)}"
        return SegmentPlan(sql, params, filters, "Compiled visual rules into tenant-scoped SQL with parameter binding.")

    def nl_to_sql(self, tenant_id: uuid.UUID, query: str, llm=None) -> SegmentPlan:
        normalized = re.sub(r"\s+", " ", query.lower()).strip()
        rules, intents = self._extract_rules(normalized)

        # If LLM client available, use it to refine intent detection
        if llm and getattr(llm, "is_llm_available", False):
            try:
                from app.agents.prompts import SYSTEM_PROMPTS, build_segmentation_prompt
                prompt = build_segmentation_prompt(query, rules)
                raw = llm.generate(prompt, system=SYSTEM_PROMPTS["segmentation"])
                # Try to parse LLM response for additional rules
                import json
                cleaned = raw.strip()
                if cleaned.startswith("```"):
                    lines = cleaned.split("\n")
                    lines = [l for l in lines if not l.strip().startswith("```")]
                    cleaned = "\n".join(lines)
                parsed = json.loads(cleaned)
                if parsed.get("suggested_rules"):
                    existing_keys = {
                        (r["field"], r["operator"], str(r["value"]))
                        for r in rules
                    }
                    for rule in parsed["suggested_rules"]:
                        key = (rule.get("field", ""), rule.get("operator", ""), str(rule.get("value", "")))
                        if key not in existing_keys and rule.get("field") in ALLOWED_FIELDS and rule.get("operator") in OPERATORS:
                            rules.append(rule)
                            existing_keys.add(key)
                if parsed.get("refined_intents"):
                    for ri in parsed["refined_intents"]:
                        if ri not in intents:
                            intents.append(ri)
            except Exception:
                pass  # Keep existing rule-based results as fallback

        filters = {"logic": "and", "rules": rules, "natural_language": query, "detected_intents": intents}
        plan = self.visual_to_sql(tenant_id, filters)
        plan.explanation = f"Detected {', '.join(intents)} intent and translated it into safe tenant-scoped SQL."
        return plan

    def _extract_rules(self, normalized: str) -> tuple[list[dict[str, Any]], list[str]]:
        rules: list[dict[str, Any]] = []
        intents: list[str] = []
        days = self._extract_days(normalized)

        if any(term in normalized for term in ["inactive", "lapsed", "win back", "winback", "bring back", "not purchased", "not purchase", "dormant"]):
            rules.append({"field": "last_purchase_days", "operator": "gte", "value": days or 90})
            intents.append("winback")
        if any(term in normalized for term in ["new shopper", "new customer", "first time", "first-time", "second purchase", "second-purchase"]):
            rules.append({"field": "order_count", "operator": "eq", "value": 1})
            if "recent" in normalized or "new" in normalized:
                rules.append({"field": "first_purchase_days", "operator": "lte", "value": days or 60})
            intents.append("second_purchase")
        if any(term in normalized for term in ["repeat", "loyal", "retention", "retain"]):
            rules.append({"field": "order_count", "operator": "gte", "value": 2})
            intents.append("retention")
        if any(term in normalized for term in ["vip", "high value", "high-value", "ltv", "big spender", "top spender", "premium"]):
            rules.append({"field": "total_spend", "operator": "gte", "value": self._money_threshold(normalized, 25000)})
            intents.append("high_value")
        if any(term in normalized for term in ["low value", "budget", "entry level"]):
            rules.append({"field": "total_spend", "operator": "lt", "value": self._money_threshold(normalized, 5000)})
            intents.append("value_builder")
        if any(term in normalized for term in ["churn", "at risk", "risk", "about to leave"]):
            rules.append({"field": "last_purchase_days", "operator": "gte", "value": days or 60})
            rules.append({"field": "order_count", "operator": "gte", "value": 1})
            intents.append("churn_prevention")
        if any(term in normalized for term in ["clicked", "clickers", "engaged", "opened", "read", "interested", "browse", "browsed", "viewed"]):
            rules.append({"field": "engagement_count", "operator": "gte", "value": 1})
            if "clicked" in normalized or "clickers" in normalized:
                rules.append({"field": "click_count", "operator": "gte", "value": 1})
            intents.append("engagement_based")
        if any(term in normalized for term in ["failed", "undelivered", "delivery issue"]):
            rules.append({"field": "failure_count", "operator": "gte", "value": 1})
            intents.append("deliverability_recovery")
        if any(term in normalized for term in ["converted", "purchased after campaign", "campaign buyers"]):
            rules.append({"field": "conversion_count", "operator": "gte", "value": 1})
            intents.append("post_conversion")
        if any(term in normalized for term in ["discount", "coupon", "offer", "sale", "clearance", "exclusive drop", "launch"]):
            rules.append({"field": "order_count", "operator": "gte", "value": 1})
            intents.append("promotion")

        for channel in ["whatsapp", "sms", "email", "rcs"]:
            if channel in normalized:
                rules.append({"field": f"{channel}_consent", "operator": "eq", "value": True})
                intents.append(f"{channel}_eligible")
        for city in CITY_TERMS:
            if city in normalized:
                rules.append({"field": "city", "operator": "contains", "value": city.title()})
                intents.append("geo_targeting")
        for tier in LOYALTY_TERMS:
            if tier in normalized:
                rules.append({"field": "loyalty_tier", "operator": "eq", "value": tier})
                intents.append("loyalty_tier")
        for term, category in CATEGORY_TERMS.items():
            if term in normalized:
                rules.append({"field": "preferred_category", "operator": "eq", "value": category})
                intents.append("category_affinity")
                break

        if "female" in normalized or "women" in normalized:
            rules.append({"field": "gender", "operator": "eq", "value": "female"})
            intents.append("demographic")
        if "male" in normalized or "men" in normalized:
            rules.append({"field": "gender", "operator": "eq", "value": "male"})
            intents.append("demographic")

        if not rules:
            rules.extend(
                [
                    {"field": "order_count", "operator": "gte", "value": 1},
                    {"field": "last_purchase_days", "operator": "lte", "value": 365},
                ]
            )
            intents.append("general_marketable_audience")
        return self._dedupe_rules(rules), list(dict.fromkeys(intents))

    def _extract_days(self, normalized: str) -> int | None:
        match = re.search(r"(\d{1,4})\s*(?:day|days|d)\b", normalized)
        if match:
            return int(match.group(1))
        month_match = re.search(r"(\d{1,2})\s*(?:month|months)\b", normalized)
        if month_match:
            return int(month_match.group(1)) * 30
        return None

    def _money_threshold(self, normalized: str, default: int) -> int:
        match = re.search(r"(?:rs\.?|₹|inr)?\s*(\d{1,3}(?:,\d{3})+|\d{4,7})", normalized)
        if not match:
            return default
        return int(match.group(1).replace(",", ""))

    def _dedupe_rules(self, rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple[str, str, str]] = set()
        result = []
        for rule in rules:
            key = (str(rule["field"]), str(rule["operator"]), str(rule["value"]))
            if key not in seen:
                result.append(rule)
                seen.add(key)
        return result


class SegmentationService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = SegmentRepository(db)
        self.compiler = SegmentCompiler()

    def create_segment(self, tenant_id: uuid.UUID, user_id: uuid.UUID | None, name: str, source: str, filters: dict[str, Any], nl_query: str | None = None) -> Segment:
        plan = self.compiler.nl_to_sql(tenant_id, nl_query or "") if source == "natural_language" else self.compiler.visual_to_sql(tenant_id, filters)
        estimated_size = self.repo.count(plan.sql_text, plan.params)
        return self.repo.create(
            Segment(
                tenant_id=tenant_id,
                name=name,
                description=plan.explanation,
                source=source,
                filters={**plan.filters, "params": {k: str(v) for k, v in plan.params.items()}},
                sql_text=plan.sql_text,
                estimated_size=estimated_size,
                created_by=user_id,
            )
        )

    def refresh_segment(self, segment_id: uuid.UUID) -> Segment | None:
        """Re-run the segment SQL to update estimated_size."""
        segment = self.repo.get(segment_id)
        if not segment:
            return None
        try:
            # Reconstruct params from stored filters
            stored_params = segment.filters.get("params", {})
            params: dict[str, Any] = {}
            for k, v in stored_params.items():
                if isinstance(v, str) and v.isdigit():
                    params[k] = int(v)
                else:
                    # Try to parse UUIDs
                    try:
                        params[k] = uuid.UUID(v)
                    except (ValueError, AttributeError):
                        params[k] = v

            new_size = self.repo.count(segment.sql_text, params)
            segment.estimated_size = new_size
            self.db.commit()
            self.db.refresh(segment)
        except Exception:
            pass
        return segment
