"""LLM Synthesis Engine for theme extraction and cross-functional recommendations."""

import json
import logging
import os
import re
from typing import List, Optional

from src.models.cluster import ClusterInfo, ClusterTheme
from src.utils.config_loader import SynthesisConfig, get_product, load_settings

logger = logging.getLogger(__name__)


class ReviewSynthesizer:
    """Uses LLM (or deterministic heuristic fallback) to synthesize clusters into actionable themes."""

    def __init__(self, config: Optional[SynthesisConfig] = None):
        settings = load_settings()
        self.config = config or settings.reasoning.synthesis
        self._gemini_client = None
        self._model_name = "gemini-2.5-flash"
        self._init_llm()

    def _init_llm(self):
        """Initializes the Gemini LLM client if configured."""
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key and api_key != "your_gemini_api_key_here":
            try:
                from google import genai
                self._gemini_client = genai.Client(api_key=api_key)
                self._model_name = os.getenv("LLM_MODEL", "gemini-2.5-flash")
                logger.info(f"Initialized Gemini model: {self._model_name}")
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini model: {e}")

    def synthesize_clusters(
        self,
        clusters: List[ClusterInfo],
        product_id: str = "groww",
    ) -> List[ClusterTheme]:
        """Synthesizes top clusters into structured ClusterTheme objects."""
        if not clusters:
            return []

        # Cap to max_themes (e.g. 5)
        target_clusters = clusters[: self.config.max_themes]

        themes: List[ClusterTheme] = []
        for cluster in target_clusters:
            theme = self._synthesize_single_cluster(cluster, product_id)
            themes.append(theme)

        return themes

    def _synthesize_single_cluster(
        self, cluster: ClusterInfo, product_id: str
    ) -> ClusterTheme:
        """Synthesizes a single cluster using LLM or rule-based fallback."""
        if self._gemini_client:
            try:
                return self._call_llm_for_cluster(cluster, product_id)
            except Exception as e:
                logger.warning(
                    f"LLM synthesis failed for cluster {cluster.metrics.cluster_id}: {e}. Using deterministic fallback."
                )

        return self._heuristic_fallback_synthesis(cluster)

    def _call_llm_for_cluster(
        self, cluster: ClusterInfo, product_id: str
    ) -> ClusterTheme:
        """Calls Gemini with strict JSON schema instructions."""
        product_cfg = get_product(product_id)
        verticals_str = ", ".join(product_cfg.valid_verticals)

        reviews_context = "\n".join(
            [f"- {txt}" for txt in cluster.representative_texts[:8]]
        )

        prompt = f"""You are the Principal Product Review Analyst for {product_cfg.display_name}.
Analyze the following customer reviews belonging to an issue cluster (Avg Rating: {cluster.metrics.average_score}/5, Total Complaints: {cluster.metrics.review_count}).

Valid Product Verticals: {verticals_str}

<customer_reviews>
{reviews_context}
</customer_reviews>

Respond STRICTLY with a valid JSON object matching this structure:
{{
  "theme_title": "Action-oriented 1-line headline summarizing the core issue",
  "root_cause_summary": "1-sentence explanation of what is failing or missing for the customer",
  "candidate_quotes": ["Exact verbatim excerpt from the reviews above", "Second exact verbatim excerpt"],
  "product_action": "Specific UX or feature roadmap improvement",
  "support_action": "Support team triage rule, macro update, or SLA target",
  "engineering_action": "Backend/Infra fix, socket latency optimization, or crash resolution"
}}

Rules:
1. Do NOT hallucinate quotes. Extract exact substrings from the provided review text.
2. Focus on actionable fixes for product, support, and engineering.
3. Return ONLY valid JSON, with no markdown code fences or commentary.
"""

        response = self._gemini_client.models.generate_content(
            model=self._model_name,
            contents=prompt,
        )
        text = response.text.strip()

        # Clean JSON fences if present
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]

        data = json.loads(text.strip())
        return ClusterTheme(
            cluster_id=cluster.metrics.cluster_id,
            theme_title=data.get("theme_title", f"Issue Theme #{cluster.metrics.cluster_id}"),
            root_cause_summary=data.get(
                "root_cause_summary", "Frequent user friction identified in customer reviews."
            ),
            candidate_quotes=data.get("candidate_quotes", cluster.representative_texts[:2]),
            product_action=data.get("product_action"),
            support_action=data.get("support_action"),
            engineering_action=data.get("engineering_action"),
        )

    def _heuristic_fallback_synthesis(self, cluster: ClusterInfo) -> ClusterTheme:
        """Deterministic heuristic fallback when LLM is offline or unconfigured."""
        texts = cluster.representative_texts
        c_id = cluster.metrics.cluster_id

        # Categorize common themes from text keywords
        all_text = " ".join(texts).lower()
        if any(k in all_text for k in ["kyc", "otp", "aadhaar", "pan", "verification", "onboard"]):
            title = "KYC & Verification Delays / OTP Timeouts"
            root_cause = "Users experience SMS OTP latency and document upload failures during onboarding verification."
            prod_act = "Implement alternative Digilocker verification flow and retry wizard."
            supp_act = "Create priority SLA queue for stuck verification tickets (> 2 hours)."
            eng_act = "Add redundant SMS gateway fallback and increase webhook timeout."
        elif any(k in all_text for k in ["chart", "lag", "f&o", "option", "candle", "tradingview"]):
            title = "F&O Chart Rendering Lag & Order Latency"
            root_cause = "Real-time candlestick chart lag and execution latency during peak market opening hours."
            prod_act = "Introduce lightweight trading mode with reduced chart DOM elements."
            supp_act = "Publish live market status banner for known exchange connectivity delays."
            eng_act = "Scale WebSocket chart streaming cluster and optimize client-side canvas rendering."
        elif any(k in all_text for k in ["withdraw", "bank", "deposit", "wallet", "upi", "mandate"]):
            title = "Fund Withdrawal & UPI Payment Glitches"
            root_cause = "Pending bank withdrawal confirmations and UPI settlement synchronization delays."
            prod_act = "Add real-time transaction timeline tracker in the Groww wallet."
            supp_act = "Auto-trigger refund status lookup for failed UPI mandates within 15 minutes."
            eng_act = "Implement automated bank webhook reconciliation job."
        elif any(k in all_text for k in ["crash", "freeze", "black screen", "login", "pin", "fingerprint"]):
            title = "App Crash on Launch & Biometric Login Failure"
            root_cause = "Intermittent app freezes and biometric authentication timeouts on recent Android builds."
            prod_act = "Provide instant PIN fallback if biometric sensor fails twice."
            supp_act = "Guide users to clear app cache in quick-response support macros."
            eng_act = "Resolve null pointer crash in splash screen initialization."
        elif any(k in all_text for k in ["margin", "mtf", "pledge", "leverage"]):
            title = "MTF Margin Changes & Unexpected Leverage Reduction"
            root_cause = "Traders report sudden MTF margin adjustments and unexpected interest rates without prior notice."
            prod_act = "Provide in-app notification before MTF margin requirement changes take effect."
            supp_act = "Create dedicated margin call and MTF interest calculation FAQ macro."
            eng_act = "Expose real-time MTF margin utilization API endpoint to trading frontend."
        elif any(k in all_text for k in ["charge", "charges", "brokerage", "fee", "hidden", "annual"]):
            title = "Unclear Brokerage Fees & Hidden Charge Concerns"
            root_cause = "Users express frustration over unexpected account maintenance or order transaction charges."
            prod_act = "Display itemized fee and tax estimate directly in the order confirmation modal."
            supp_act = "Improve transparent breakdown in monthly ledger statements."
            eng_act = "Enhance ledger fee calculation service response time."
        elif any(k in all_text for k in ["refer", "referral", "reward", "bonus", "invite"]):
            title = "Referral Reward & Bonus Credit Inconsistencies"
            root_cause = "Users experience delays in receiving credited referral bonuses post friend onboarding."
            prod_act = "Add clear referral progress timeline with milestone statuses (Invited, KYC Done, Traded)."
            supp_act = "Empower support agents with instant referral dispute crediting tool."
            eng_act = "Implement automated referral reward reconciliation cron job."
        elif any(k in all_text for k in ["dividend", "yield", "split", "bonus share", "corporate"]):
            title = "Corporate Action & Dividend Yield Data Discrepancies"
            root_cause = "Outdated financial metrics and unadjusted dividend yields shown post stock splits."
            prod_act = "Add corporate action adjustment banner on company overview page."
            supp_act = "Route corporate action data discrepancy reports directly to market data ops."
            eng_act = "Sync real-time corporate action feeds directly from exchange master databases."
        else:
            title = f"High-Impact Review Friction Cluster #{c_id + 1}"
            root_cause = "Significant user dissatisfaction reported regarding app responsiveness and usability."
            prod_act = "Review UX friction points and simplify navigation workflow."
            supp_act = "Tag and track customer feedback in weekly support triage."
            eng_act = "Audit client logs for latency spikes and unhandled exceptions."

        candidate_quotes = texts[:2] if texts else ["App needs major improvements."]

        return ClusterTheme(
            cluster_id=c_id,
            theme_title=title,
            root_cause_summary=root_cause,
            candidate_quotes=candidate_quotes,
            product_action=prod_act,
            support_action=supp_act,
            engineering_action=eng_act,
        )
