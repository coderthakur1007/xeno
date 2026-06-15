"""
Unified LLM client with Gemini, OpenAI, and smart local fallback.

Supports three providers:
- gemini: Google Gemini 2.0 Flash via REST API
- openai: OpenAI GPT-4o-mini via REST API
- local: Smart template-based generation (no API required)

On any API failure the client transparently falls back to local mode.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Template banks for smart local generation
# ---------------------------------------------------------------------------

_GREETINGS = [
    "Hi {{first_name}}",
    "Hey {{first_name}}",
    "Hello {{first_name}}",
    "Dear {{first_name}}",
    "Hi there, {{first_name}}",
    "Welcome back, {{first_name}}",
    "Good news, {{first_name}}",
    "{{first_name}}, great to connect",
]

_CTAS_BY_INTENT = {
    "winback": ["Come back & save", "Rediscover your favourites", "Claim your return offer", "Shop again today"],
    "retention": ["Keep the streak going", "Unlock loyalty rewards", "See what's new for you", "Continue your journey"],
    "high_value": ["Explore exclusive picks", "Access VIP offers", "Shop the premium edit", "Claim your elite reward"],
    "promotion": ["Grab the deal", "Shop the sale", "Don't miss out", "Save now"],
    "churn_prevention": ["We miss you!", "Stay with us", "One more reason to shop", "Let's reconnect"],
    "second_purchase": ["Make it a habit", "Your second order awaits", "Complete the pair", "Try something new"],
    "default": ["Shop now", "Explore today", "Get started", "See more"],
}

_EMOJI_SETS = {
    "winback": ["🔙", "💫", "🎉", "✨"],
    "retention": ["🌟", "💎", "🏆", "🎯"],
    "high_value": ["👑", "💰", "🥂", "✨"],
    "promotion": ["🔥", "💥", "🛍️", "⚡"],
    "churn_prevention": ["💌", "🤗", "❤️", "🙏"],
    "second_purchase": ["🛒", "🎁", "🆕", "😊"],
    "default": ["📢", "⭐", "🎯", "💡"],
}

_URGENCY_PHRASES = [
    "Limited time only",
    "Ends soon",
    "While stocks last",
    "Today only",
    "This week only",
    "Don't wait",
    "Hurry",
    "Act fast",
]

_WHATSAPP_TEMPLATES = [
    "{greeting}! {emoji} {body} {cta} → {{shop_link}}",
    "{emoji} {greeting}! {body} Tap here: {{shop_link}} {cta}!",
    "{greeting}, {body} {emoji} Reply YES or visit {{shop_link}}",
    "{emoji}{emoji} {greeting}! {urgency}! {body} {cta}: {{shop_link}}",
    "{greeting}! {body} {emoji} Use code {{coupon_code}} for extra savings. {cta}!",
    "{emoji} {greeting} — {body} Check it out: {{shop_link}} {cta}",
    "{greeting}! {urgency}! {emoji} {body} Click {{shop_link}} now",
    "{greeting}, quick update {emoji} — {body} {{shop_link}}",
]

_EMAIL_TEMPLATES = [
    "{greeting},\n\n{body}\n\nAs a valued customer, we've curated something special just for you.\n\nBest regards,\nThe Team",
    "{greeting},\n\n{body}\n\nWe'd love to help you find exactly what you're looking for.\n\nWarm regards,\nYour Shopping Assistant",
    "{greeting},\n\nWe noticed something that might interest you. {body}\n\nClick below to explore.\n\nCheers,\nThe Team",
    "{greeting},\n\n{urgency} — {body}\n\nDon't miss this opportunity.\n\nBest,\nCustomer Experience Team",
    "{greeting},\n\n{body}\n\nBased on your preferences, we think you'll love what we've prepared.\n\nSincerely,\nThe Curation Team",
    "{greeting},\n\n{body}\n\nYour loyalty deserves to be rewarded. Explore your personalised picks.\n\nWith appreciation,\nThe Team",
    "{greeting},\n\nHere's something we think you'll enjoy:\n\n{body}\n\nLet us know what you think!\n\nThe Team",
    "{greeting},\n\nA quick note for you — {body}\n\nThank you for being part of our community.\n\nBest wishes,\nThe Team",
]

_SMS_TEMPLATES = [
    "{greeting}! {body} {cta}: {{shop_link}}",
    "{body} {urgency}! Visit {{shop_link}}",
    "{greeting}: {body} Reply SHOP or tap {{shop_link}}",
    "{urgency}! {greeting}, {body} {{shop_link}}",
    "{greeting}! {body} Code: {{coupon_code}}. {{shop_link}}",
    "{body} {cta}. {{shop_link}}",
    "{greeting}, {body} Ends today! {{shop_link}}",
    "{body} — {greeting}, tap {{shop_link}} now!",
]

_RCS_TEMPLATES = [
    "{emoji} {greeting}!\n\n{body}\n\n[{cta}]({{shop_link}}) | [Browse more]({{browse_link}})",
    "{greeting}! {emoji}\n\n{body}\n\n🖼️ {{product_image}}\n\n[{cta}]({{shop_link}})",
    "{emoji}{emoji} {greeting}\n\n{body}\n\n[{cta}]({{shop_link}}) | [View offer]({{offer_link}})",
    "{greeting}! {urgency}! {emoji}\n\n{body}\n\n[{cta}]({{shop_link}})",
    "{emoji} {greeting}!\n\n{body}\n\nCarousel: {{product_carousel}}\n\n[{cta}]({{shop_link}})",
    "{greeting}!\n\n{emoji} {body}\n\n[{cta}]({{shop_link}}) | [Help]({{help_link}})",
    "{greeting} {emoji}\n\n{body}\n\nVideo: {{video_link}}\n\n[{cta}]({{shop_link}})",
    "{emoji} {greeting}! {body}\n\n[{cta}]({{shop_link}}) | [Wishlist]({{wishlist_link}})",
]

_EMAIL_SUBJECTS_BY_INTENT = {
    "winback": [
        "We miss you, {{first_name}}!",
        "It's been a while — here's something special",
        "Your favourites are waiting",
        "Come back and save!",
    ],
    "retention": [
        "Thank you for being a loyal customer",
        "Something new, just for you",
        "Your loyalty rewards are here",
        "Keep the momentum going, {{first_name}}",
    ],
    "high_value": [
        "Exclusive picks for our top customers",
        "VIP access: new arrivals just dropped",
        "{{first_name}}, you deserve the best",
        "Premium collection — curated for you",
    ],
    "promotion": [
        "🔥 Sale alert — up to {{discount}}% off",
        "Don't miss our biggest sale yet",
        "Limited time offer inside",
        "{{first_name}}, your deal is waiting",
    ],
    "churn_prevention": [
        "We want you back, {{first_name}}",
        "Here's a reason to come back",
        "Your next order is on us",
        "Don't let your rewards expire",
    ],
    "second_purchase": [
        "Ready for your next order?",
        "Complete the set, {{first_name}}",
        "Your second purchase surprise",
        "More to explore — check this out",
    ],
    "default": [
        "Something special for you",
        "Check out what's new",
        "{{first_name}}, you'll love this",
        "New arrivals just for you",
    ],
}

_BODY_TEMPLATES_BY_INTENT = {
    "winback": [
        "It's been a while since your last visit. We've added new items in {{last_product_category}} that match your taste.",
        "We noticed you haven't shopped recently. Here's a personalised selection based on your previous purchases.",
        "Your favourite {{last_product_category}} collection has been refreshed with exciting new arrivals.",
        "Since your last order, we've launched several items we think you'll love.",
    ],
    "retention": [
        "As one of our valued repeat customers, you get early access to our newest {{last_product_category}} collection.",
        "Thank you for your continued loyalty! We've prepared exclusive picks just for you.",
        "Your shopping history tells us you love great quality. Here are curated recommendations.",
        "Because you're a regular, we've unlocked special rewards for your next purchase.",
    ],
    "high_value": [
        "As one of our top customers, you get first access to our premium {{last_product_category}} collection.",
        "Your taste is impeccable. We've handpicked exclusive items that match your style.",
        "Only our most valued customers get this: early access to limited-edition pieces.",
        "With your refined preferences, we've curated a VIP selection just for you.",
    ],
    "promotion": [
        "Our biggest {{last_product_category}} sale is here! Get up to {{discount}}% off on your favourites.",
        "Flash sale alert — handpicked deals on items you've browsed before.",
        "Special offer on {{last_product_category}}: save big on your next purchase.",
        "We're offering exclusive discounts on products matching your shopping history.",
    ],
    "churn_prevention": [
        "We miss having you around! Here's a special incentive to come back and explore.",
        "It's been {{recency}} days since we last saw you. We've saved something special for your return.",
        "Your loyalty rewards are about to expire — use them before they're gone!",
        "We haven't forgotten about you. Come back and see what's new in {{last_product_category}}.",
    ],
    "second_purchase": [
        "Loved your first purchase? Here are more items in {{last_product_category}} you might enjoy.",
        "Welcome to the family! As a new shopper, here's a special offer on your second order.",
        "Your first order was just the beginning — explore complementary items picked for you.",
        "Great taste! Based on your first purchase, we recommend these matching items.",
    ],
    "default": [
        "We've got exciting new arrivals that match your preferences. Check them out!",
        "Based on your shopping history, here are personalised recommendations just for you.",
        "Something special awaits — browse our latest collection curated to your taste.",
        "Discover new favourites from our latest drop, handpicked based on your interests.",
    ],
}


def _detect_intent(goal: str) -> str:
    """Detect the primary marketing intent from the goal string."""
    goal_lower = goal.lower()
    if any(kw in goal_lower for kw in ["inactive", "lapsed", "win back", "winback", "bring back", "dormant"]):
        return "winback"
    if any(kw in goal_lower for kw in ["churn", "at risk", "risk", "about to leave"]):
        return "churn_prevention"
    if any(kw in goal_lower for kw in ["new shopper", "new customer", "first time", "second purchase"]):
        return "second_purchase"
    if any(kw in goal_lower for kw in ["vip", "high value", "high-value", "premium", "top spender", "big spender"]):
        return "high_value"
    if any(kw in goal_lower for kw in ["repeat", "loyal", "retention", "retain"]):
        return "retention"
    if any(kw in goal_lower for kw in ["discount", "coupon", "offer", "sale", "clearance", "launch", "promote"]):
        return "promotion"
    return "default"


def _hash_select(goal: str, pool: list, offset: int = 0) -> Any:
    """Select from pool using goal hash + time-based entropy for variety across requests."""
    import time
    entropy = str(time.time_ns()) + str(offset)
    digest = int(hashlib.md5((goal + entropy).encode()).hexdigest(), 16)
    return pool[digest % len(pool)]


def _hash_index(goal: str, max_val: int, offset: int = 0) -> int:
    import time
    entropy = str(time.time_ns()) + str(offset)
    digest = int(hashlib.md5((goal + entropy).encode()).hexdigest(), 16)
    return digest % max_val


class LLMClient:
    """Unified LLM client with Gemini, OpenAI, and local fallback."""

    def __init__(self, provider: str = "local", gemini_key: str = "", openai_key: str = ""):
        self.provider = provider
        self._gemini_key = gemini_key
        self._openai_key = openai_key
        # Auto-detect: if provider is "local" but keys exist, upgrade
        if provider == "local" and gemini_key:
            self.provider = "gemini"
        elif provider == "local" and openai_key:
            self.provider = "openai"

    @property
    def is_llm_available(self) -> bool:
        return self.provider in ("gemini", "openai")

    def generate(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        """Generate text. Returns string response. Falls back to local on failure."""
        try:
            if self.provider == "gemini":
                return self._gemini(prompt, system, temperature, max_tokens)
            elif self.provider == "openai":
                return self._openai(prompt, system, temperature, max_tokens)
            else:
                return self._local(prompt, system)
        except Exception as exc:
            logger.warning("LLM call failed (%s), falling back to local: %s", self.provider, exc)
            return self._local(prompt, system)

    # -----------------------------------------------------------------------
    # Provider implementations
    # -----------------------------------------------------------------------

    def _gemini(self, prompt: str, system: str, temperature: float, max_tokens: int) -> str:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.0-flash:generateContent?key={self._gemini_key}"
        )
        combined_text = f"{system}\n\n{prompt}" if system else prompt
        payload = {
            "contents": [{"parts": [{"text": combined_text}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        with httpx.Client(timeout=30) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]

    def _openai(self, prompt: str, system: str, temperature: float, max_tokens: int) -> str:
        url = "https://api.openai.com/v1/chat/completions"
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": "gpt-4o-mini",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self._openai_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=30) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def _local(self, prompt: str, system: str) -> str:
        """
        Smart local generation that parses the prompt to extract context and
        generates varied content using template banks.
        """
        combined = f"{system}\n{prompt}".lower()

        # Add request-level entropy for varied responses
        import random
        _request_entropy = random.randint(0, 999999)

        # Detect intent from the combined text
        intent = _detect_intent(combined)

        # Try to parse structured data from the prompt
        context = self._parse_prompt_context(prompt)

        # Check what kind of output is requested
        if "json" in combined and ("variant" in combined or "content" in combined or "message" in combined):
            return self._generate_content_json(intent, context, prompt)
        if "json" in combined and ("insight" in combined or "intelligence" in combined):
            return self._generate_insights_json(intent, context)
        if "json" in combined and ("strategy" in combined or "recommend" in combined):
            return self._generate_strategy_json(intent, context)
        if "json" in combined and ("channel" in combined or "optimiz" in combined):
            return self._generate_channel_json(intent, context)
        if "json" in combined and ("segment" in combined):
            return self._generate_segment_json(intent, context)
        if "json" in combined and ("analytic" in combined or "metric" in combined):
            return self._generate_analytics_json(intent, context)

        # Default: generate a descriptive text response
        return self._generate_text_response(intent, context, prompt)

    def _parse_prompt_context(self, prompt: str) -> dict:
        """Extract key data values from the prompt text."""
        ctx: dict[str, Any] = {}
        lower = prompt.lower()

        # Extract numeric values
        import re
        for pattern, key in [
            (r"audience[_ ]?size[:\s]+(\d+)", "audience_size"),
            (r"(\d+)\s*customers?", "audience_size"),
            (r"avg[_\s]?spend[:\s]+[₹rs.]*\s*([\d,.]+)", "avg_spend"),
            (r"average\s*spend[:\s]+[₹rs.]*\s*([\d,.]+)", "avg_spend"),
            (r"avg[_\s]?orders?[:\s]+([\d.]+)", "avg_orders"),
            (r"avg[_\s]?recency[:\s]+([\d.]+)", "avg_recency"),
            (r"total[_\s]?customers?[:\s]+(\d+)", "total_customers"),
            (r"delivery[_\s]?rate[:\s]+([\d.]+)", "delivery_rate"),
            (r"open[_\s]?rate[:\s]+([\d.]+)", "open_rate"),
            (r"click[_\s]?rate[:\s]+([\d.]+)", "click_rate"),
            (r"conversion[_\s]?rate[:\s]+([\d.]+)", "conversion_rate"),
        ]:
            m = re.search(pattern, lower)
            if m:
                val = m.group(1).replace(",", "")
                ctx[key] = float(val) if "." in val else int(val)

        # Extract channels
        channels = []
        for ch in ["whatsapp", "sms", "email", "rcs"]:
            if ch in lower:
                channels.append(ch)
        if channels:
            ctx["channels"] = channels

        # Extract goal
        goal_match = re.search(r'goal[:\s]+"?([^"\n]+)"?', lower)
        if goal_match:
            ctx["goal"] = goal_match.group(1).strip()
        else:
            ctx["goal"] = prompt[:120]

        # Detect cities
        for city in ["mumbai", "delhi", "bangalore", "pune", "hyderabad", "chennai"]:
            if city in lower:
                ctx.setdefault("cities", []).append(city.title())

        return ctx

    def _generate_content_json(self, intent: str, ctx: dict, prompt: str) -> str:
        """Generate message variant content as JSON."""
        channels = ctx.get("channels", ["whatsapp", "email"])
        goal = ctx.get("goal", prompt[:80])
        variants = []

        for var_idx in range(2):
            content = {}
            for channel in channels:
                greeting = _hash_select(goal, _GREETINGS, var_idx)
                cta = _hash_select(goal, _CTAS_BY_INTENT.get(intent, _CTAS_BY_INTENT["default"]), var_idx)
                emoji = _hash_select(goal, _EMOJI_SETS.get(intent, _EMOJI_SETS["default"]), var_idx)
                urgency = _hash_select(goal, _URGENCY_PHRASES, var_idx)
                body = _hash_select(goal, _BODY_TEMPLATES_BY_INTENT.get(intent, _BODY_TEMPLATES_BY_INTENT["default"]), var_idx)

                if channel == "whatsapp":
                    template = _hash_select(goal, _WHATSAPP_TEMPLATES, var_idx)
                elif channel == "email":
                    template = _hash_select(goal, _EMAIL_TEMPLATES, var_idx)
                elif channel == "sms":
                    template = _hash_select(goal, _SMS_TEMPLATES, var_idx)
                elif channel == "rcs":
                    template = _hash_select(goal, _RCS_TEMPLATES, var_idx)
                else:
                    template = "{greeting}! {body} {cta}"

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
                "angle": intent if var_idx == 0 else f"{intent}_alternate",
                "channels": channels,
                "personalization_tokens": ["first_name", "last_product_category", "city", "recommended_offer"],
                "content": content,
            })

        return json.dumps({"variants": variants}, indent=2)

    def _generate_insights_json(self, intent: str, ctx: dict) -> str:
        avg_spend = ctx.get("avg_spend", 0)
        avg_orders = ctx.get("avg_orders", 0)
        avg_recency = ctx.get("avg_recency", 0)
        total = ctx.get("total_customers", ctx.get("audience_size", 0))

        insights = [
            f"Your customer base of {total} customers shows an average spend of ₹{avg_spend:.0f} with {avg_orders:.1f} average orders per customer.",
            f"Average recency of {avg_recency:.0f} days indicates {'active engagement' if avg_recency < 30 else 'potential re-engagement opportunity'}.",
        ]
        if avg_spend > 10000:
            insights.append("High average spend suggests a premium-oriented customer base — consider VIP-tier campaigns.")
        if avg_recency > 60:
            insights.append("Elevated recency suggests many customers haven't purchased recently — a winback campaign may be effective.")
        if avg_orders > 3:
            insights.append("Strong repeat-purchase behavior detected — loyalty programs and retention campaigns are recommended.")
        else:
            insights.append("Low average order frequency — second-purchase nudge campaigns could lift lifetime value.")

        return json.dumps({"insights": insights, "summary": insights[0]}, indent=2)

    def _generate_strategy_json(self, intent: str, ctx: dict) -> str:
        audience = ctx.get("audience_size", 0)
        return json.dumps({
            "narrative": f"For a {intent} campaign targeting {audience} customers, "
                         f"we recommend a multi-touch approach with evening send windows "
                         f"and A/B testing on messaging angles.",
            "reasoning": f"Based on the {intent} intent and audience profile.",
        }, indent=2)

    def _generate_channel_json(self, intent: str, ctx: dict) -> str:
        return json.dumps({
            "explanation": f"Channel recommendations are based on observed delivery and engagement rates. "
                          f"For {intent} campaigns, channels with highest historical conversion are preferred.",
        }, indent=2)

    def _generate_segment_json(self, intent: str, ctx: dict) -> str:
        return json.dumps({
            "refined_intents": [intent],
            "confidence": 0.85,
        }, indent=2)

    def _generate_analytics_json(self, intent: str, ctx: dict) -> str:
        insights = [
            "Revenue per customer shows healthy distribution across segments.",
            "Recent campaign performance indicates room for open-rate optimization.",
            "Customer retention rates could be improved with targeted lifecycle campaigns.",
        ]
        return json.dumps({"insights": insights}, indent=2)

    def _generate_text_response(self, intent: str, ctx: dict, prompt: str) -> str:
        """Generate a descriptive text response for general queries."""
        audience = ctx.get("audience_size", "your target audience")
        spend = ctx.get("avg_spend", 0)
        import random

        response_pools = {
            "winback": [
                f"For a winback campaign, focus on re-engaging lapsed customers with personalized offers based on their purchase history. With an average spend of ₹{spend:.0f}, consider tiered incentives.",
                f"Re-engage dormant customers by highlighting what they've been missing. Personalized discounts based on their ₹{spend:.0f} average spend can drive strong returns.",
                f"Winback campaigns perform best when they acknowledge the gap. Use 'We miss you' messaging combined with category-specific offers tied to their ₹{spend:.0f} spending pattern.",
                f"Target lapsed buyers with a 2-step re-engagement: first a soft reminder, then an exclusive offer. Their ₹{spend:.0f} average spend suggests mid-tier incentives will work best.",
            ],
            "retention": [
                f"Retention campaigns work best with loyalty rewards and exclusive early access. Your repeat customers averaging ₹{spend:.0f} spend are ideal for VIP treatment.",
                f"Keep your best customers engaged with surprise-and-delight moments. At ₹{spend:.0f} average spend, consider experiential rewards over pure discounts.",
                f"Build long-term loyalty by recognizing milestones. Customers spending ₹{spend:.0f} on average respond well to tier-based benefits and early access.",
                f"Strengthen retention through personalized product recommendations. With ₹{spend:.0f} average spend, cross-sell and bundle strategies drive repeat value.",
            ],
            "high_value": [
                f"High-value customer campaigns should emphasize exclusivity and premium experiences. Target audience with ₹{spend:.0f}+ average spend deserves white-glove treatment.",
                f"Your premium customers spending ₹{spend:.0f}+ want to feel special. Curate exclusive collections, early access, and concierge-style communication.",
                f"VIP campaigns for ₹{spend:.0f}+ spenders should focus on aspiration, not discounts. Limited editions, personal shopping, and priority service drive engagement.",
                f"Treat your high-value segment like insiders. With ₹{spend:.0f}+ average spend, behind-the-scenes content and exclusive previews build emotional connection.",
            ],
            "promotion": [
                f"Promotional campaigns drive urgency. Use time-limited offers with clear value propositions. Focus on channels with highest engagement rates.",
                f"Structure your promotion with a countdown and scarcity signals. Flash sales with 48-hour windows create FOMO that drives immediate action.",
                f"Layer your promotional strategy: tease → launch → last chance. Each phase should use different messaging angles to maximize reach.",
                f"For maximum promotional impact, combine channel-specific offers. Email for details, WhatsApp for urgency reminders, SMS for last-chance alerts.",
            ],
            "churn_prevention": [
                f"Churn prevention requires timely intervention. Identify at-risk customers based on declining activity and deploy personalized re-engagement.",
                f"Early churn signals include reduced email opens and longer purchase gaps. Intervene with value-add content before offering discounts.",
                f"Prevent churn by addressing the root cause — survey at-risk customers to understand pain points, then deploy targeted solutions.",
                f"Churn prevention works best as a multi-touch sequence: acknowledgment → value reminder → exclusive offer → personal outreach.",
            ],
            "second_purchase": [
                f"Converting first-time buyers into repeat customers is critical for LTV. Offer complementary product suggestions based on initial purchase.",
                f"The window for second purchase conversion is 14-30 days post-first-order. Time your outreach with product recommendations and social proof.",
                f"Drive second purchases by showcasing complementary items and sharing user reviews. New customers respond to 'customers also bought' messaging.",
                f"Second purchase campaigns should reduce friction. Offer free shipping, easy reorder, and personalized suggestions based on their first purchase category.",
            ],
            "default": [
                f"Based on the campaign objectives, we recommend a data-driven approach targeting {audience} with personalized multi-channel messaging.",
                f"Design a customer-centric campaign that leverages behavioral data to deliver relevant messaging across the most effective channels.",
                f"Build a responsive campaign that adapts messaging based on customer engagement signals. Start broad, then narrow focus to highest-intent segments.",
                f"Create a campaign that combines personalization with timing optimization. Reach {audience} through their preferred channels at peak engagement windows.",
            ],
        }
        pool = response_pools.get(intent, response_pools["default"])
        return random.choice(pool)
