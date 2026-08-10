"""Review text sanitization, quality filtering, and prompt injection defense."""

import html
import re
from datetime import datetime, timezone
from typing import List, Optional, Tuple
import os
import json
from groq import Groq

from src.models.review import RawReview, ReviewBatch, SanitizedReview
from src.preprocessing.pii_scrubber import PIIScrubber
from src.utils.config_loader import PreprocessingConfig, load_settings
from src.utils.token_manager import TokenManager


class ReviewSanitizationPipeline:
    """Sanitizes raw reviews, filters noise, scrubs PII, and applies prompt injection shields."""

    def __init__(
        self,
        config: Optional[PreprocessingConfig] = None,
        scrubber: Optional[PIIScrubber] = None,
    ):
        settings = load_settings()
        self.config = config or settings.preprocessing
        self.scrubber = scrubber or PIIScrubber()
        
        # Initialize Groq for advanced filtering
        self.groq_client = None
        self.model_name = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        api_key = os.getenv("GROQ_API_KEY")
        if api_key:
            try:
                self.groq_client = Groq(api_key=api_key)
            except Exception:
                pass

        # Regex for any emojis (Pictographs, Emoticons, Transport, Symbols, Dingbats, Variations)
        self.emoji_regex = re.compile(
            r"[\U00010000-\U0010ffff\u2600-\u26ff\u2700-\u27bf\ufe00-\ufe0f\u200d]+",
            flags=re.UNICODE,
        )

        # Regex for non-Latin native scripts (Devanagari, Bengali, Tamil, Telugu, Arabic, etc.)
        self.non_latin_regex = re.compile(
            r"[\u0900-\u097F\u0980-\u09FF\u0A80-\u0AFF\u0B80-\u0BFF\u0C00-\u0C7F"
            r"\u0C80-\u0CFF\u0D00-\u0D7F\u0600-\u06FF\u0400-\u04FF\u4E00-\u9FFF]"
        )

        # High-frequency transliterated Hindi/Hinglish vocabulary indicators (strictly unambiguous)
        self.hinglish_words = {
            "kardo", "karo", "karna", "karta", "karti", "kare", "karen", "kiya", "kiye", "lekin",
            "thik", "theek", "nahi", "nhi", "nahin", "mera", "meri", "mere", "mujhe", "mujhko",
            "humko", "aapko", "bahut", "bohot", "bhut", "paisa", "paise", "bakwas", "ghatiya",
            "pagal", "bandh", "dekho", "bhai", "kuch", "kuchh", "kyun", "kya", "kaisa", "kaise",
            "kisi", "hoga", "hogi", "honge", "batao", "bataye", "chahiye", "waala", "wali",
            "nikalo", "lagta", "lagti", "lagte", "raha", "rahi", "rahe", "fhaltu", "faltu",
            "bekar", "hamesha", "chalta", "chalti", "chalana", "achha", "accha", "achhe", "achhi",
            "cheez", "cheeze", "hota", "hoti", "hote", "aaya", "aayi", "aaye", "gaya", "gayi",
            "gaye", "dikkat", "pareshani", "samajh", "baje", "bje", "bataiye", "bheja",
        }

        # Suspicious prompt injection phrases
        self.injection_patterns = [
            re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.IGNORECASE),
            re.compile(r"system\s*prompt", re.IGNORECASE),
            re.compile(r"you\s+are\s+now\s+a", re.IGNORECASE),
            re.compile(r"<\s*/?\s*(script|style|review_data|system|prompt)\s*>", re.IGNORECASE),
        ]

    def is_quality_review(self, text: str) -> bool:
        """Returns True if the review meets the length, emoji-free, and English language criteria."""
        if not text:
            return False

        stripped = text.strip()
        words = stripped.split()

        # 1. Minimum word count filter (e.g. >= 8 words)
        if len(words) < self.config.min_word_count:
            return False

        # 2. Emoji filter (remove reviews containing any emojis)
        if self.config.filter_all_emojis and self.emoji_regex.search(stripped):
            return False

        # 3. Non-Latin native script filter (e.g. Hindi, Tamil, Arabic)
        if self.config.filter_non_english and self.non_latin_regex.search(stripped):
            return False

        # 4. Transliterated / non-English language filter
        if self.config.filter_non_english and self._is_non_english_transliteration(words):
            return False

        # 5. Check if text contains at least basic alphabetical characters
        if not re.search(r"[a-zA-Z]", stripped):
            return False

        return True

    def _is_non_english_transliteration(self, words: List[str]) -> bool:
        """Detects whether Romanized text is predominantly transliterated Hindi/non-English."""
        clean_words = [re.sub(r"[^a-zA-Z]", "", w.lower()) for w in words]
        clean_words = [w for w in clean_words if w]
        if not clean_words:
            return True

        hinglish_match_count = sum(1 for w in clean_words if w in self.hinglish_words)
        ratio = hinglish_match_count / len(clean_words)

        # Flag if 20% or more words are Hinglish markers or 2+ distinct markers present
        if ratio >= 0.20 or hinglish_match_count >= 2:
            return True

        return False

    def shield_prompt_injection(self, text: str) -> str:
        """Neutralizes prompt injection payloads and escapes XML control characters."""
        if not text:
            return ""

        sanitized = text

        if self.config.enable_prompt_injection_shield:
            for pattern in self.injection_patterns:
                sanitized = pattern.sub("[FILTERED_INSTRUCTION]", sanitized)

            # XML escape to prevent escaping XML boundary tags in LLM prompts
            sanitized = html.escape(sanitized, quote=False)

        return sanitized

    def sanitize_single(self, raw: RawReview) -> Optional[SanitizedReview]:
        """Processes a single RawReview into a SanitizedReview. Returns None if filtered out."""
        content = raw.content.strip()

        if not self.is_quality_review(content):
            return None

        # 1. Scrub PII
        scrubbed_content = self.scrubber.redact(content)

        # 2. Shield Prompt Injections
        safe_content = self.shield_prompt_injection(scrubbed_content)

        # 3. Anonymize user display name
        masked_user = self.scrubber.mask_username(raw.user_name)

        return SanitizedReview(
            review_id=raw.review_id,
            masked_user_name=masked_user,
            score=raw.score,
            original_content=raw.content,
            sanitized_content=safe_content,
            thumbs_up_count=raw.thumbs_up_count,
            app_version=raw.review_created_version,
            at=raw.at,
            is_negative=(raw.score <= 2),
            token_count=len(safe_content.split()),
        )

    def process_batch(
        self,
        raw_reviews: List[RawReview],
        product_id: str = "groww",
        iso_week: str = "2026-W32",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> ReviewBatch:
        """Processes a list of raw reviews into a validated ReviewBatch."""
        sanitized_list: List[SanitizedReview] = []

        # 1. Deterministic Filtering & Scrubbing
        for raw in raw_reviews:
            sanitized = self.sanitize_single(raw)
            if sanitized is not None:
                sanitized_list.append(sanitized)
                
        # 2. Groq-based LLM filtering (batch classification of spam/noise)
        if self.groq_client and sanitized_list:
            sanitized_list = self._groq_bulk_filter(sanitized_list)

        total_scraped = len(raw_reviews)
        total_sanitized = len(sanitized_list)

        avg_rating = 0.0
        neg_ratio = 0.0
        if total_sanitized > 0:
            avg_rating = round(
                sum(r.score for r in sanitized_list) / total_sanitized, 2
            )
            neg_count = sum(1 for r in sanitized_list if r.is_negative)
            neg_ratio = round(neg_count / total_sanitized, 3)

        effective_start = start_date or datetime.now(timezone.utc)
        effective_end = end_date or datetime.now(timezone.utc)

        return ReviewBatch(
            product_id=product_id,
            iso_week=iso_week,
            start_date=effective_start,
            end_date=effective_end,
            total_scraped=total_scraped,
            total_sanitized=total_sanitized,
            average_rating=avg_rating,
            negative_ratio=neg_ratio,
            reviews=sanitized_list,
        )

    def _groq_bulk_filter(self, reviews: List[SanitizedReview]) -> List[SanitizedReview]:
        """Uses Groq LLM to filter out remaining spam or non-actionable reviews."""
        if not reviews:
            return []

        # Use 6000 as safe buffer for Llama 3 70B (8192 token window)
        batches = TokenManager.chunk_data(
            items=reviews,
            max_tokens=6000,
            text_extractor=lambda r: f"ID {r.review_id}: {r.sanitized_content}"
        )

        all_spam_ids = set()

        for batch in batches:
            reviews_text = "\n".join([f"ID {r.review_id}: {r.sanitized_content}" for r in batch])
            prompt = f"""Identify the review IDs that are pure spam, gibberish, or completely non-actionable.
Reviews:
{reviews_text}

Respond with a JSON object containing a "spam_ids" key mapped to a list of string IDs. Return ONLY valid JSON."""

            try:
                response = self.groq_client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model=self.model_name,
                    response_format={"type": "json_object"}
                )
                data = json.loads(response.choices[0].message.content)
                spam_ids = set(data.get("spam_ids", []))
                all_spam_ids.update(spam_ids)
            except Exception as e:
                pass

        return [r for r in reviews if str(r.review_id) not in all_spam_ids]

