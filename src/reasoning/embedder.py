"""Semantic vector embedding engine supporting Gemini, SentenceTransformers, and SVD."""

import logging
import os
from typing import List, Optional
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import normalize

from src.utils.config_loader import EmbeddingConfig, load_settings

logger = logging.getLogger(__name__)


class SemanticEmbedder:
    """Generates dense semantic vector embeddings for review texts."""

    def __init__(self, config: Optional[EmbeddingConfig] = None):
        settings = load_settings()
        self.config = config or settings.reasoning.embedding
        self._gemini_client = None
        self._st_model = None
        self._init_backend()

    def _init_backend(self):
        """Initializes the preferred embedding backend with graceful fallbacks."""
        # 1. Try Gemini Embedding API if API key is provided
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key and api_key != "your_gemini_api_key_here":
            try:
                from google import genai
                self._gemini_client = genai.Client(api_key=api_key)
                logger.info("Initialized Gemini Embedding API backend.")
                return
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini API: {e}")

        # 2. Try SentenceTransformers if installed
        try:
            from sentence_transformers import SentenceTransformer
            self._st_model = SentenceTransformer(self.config.model_name)
            logger.info(f"Initialized SentenceTransformer backend ({self.config.model_name}).")
            return
        except Exception:
            pass

        # 3. Default fallback: TF-IDF + TruncatedSVD dense projection
        logger.info("Initialized high-speed local TF-IDF + SVD semantic projection backend.")

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        """Embeds a list of review texts into an (N, D) float32 numpy array.
        
        Guarantees L2-normalized vectors.
        """
        if not texts:
            return np.empty((0, 384), dtype=np.float32)

        # Non-empty fallback handling for empty or whitespace strings
        cleaned_texts = [t.strip() if t.strip() else "neutral review" for t in texts]

        # Case 1: Gemini API
        if self._gemini_client:
            try:
                embeddings = []
                for text in cleaned_texts:
                    res = self._gemini_client.models.embed_content(
                        model="text-embedding-004",
                        contents=text,
                    )
                    embeddings.append(res.embeddings[0].values)
                arr = np.array(embeddings, dtype=np.float32)
                return normalize(arr, norm="l2")
            except Exception as e:
                logger.warning(f"Gemini embedding API call failed: {e}. Falling back to local backend.")

        # Case 2: Sentence Transformers
        if self._st_model:
            try:
                arr = self._st_model.encode(
                    cleaned_texts,
                    batch_size=self.config.batch_size,
                    normalize_embeddings=self.config.normalize_embeddings,
                    show_progress_bar=False,
                )
                return np.array(arr, dtype=np.float32)
            except Exception as e:
                logger.warning(f"SentenceTransformer encoding failed: {e}")

        # Case 3: Built-in deterministic TF-IDF + SVD projection
        return self._embed_tfidf_svd(cleaned_texts)

    def _embed_tfidf_svd(self, texts: List[str], target_dim: int = 64) -> np.ndarray:
        """Produces dense L2-normalized vector embeddings using sublinear TF-IDF and SVD."""
        n_samples = len(texts)
        if n_samples == 1:
            # Single sample vector
            vec = np.zeros((1, target_dim), dtype=np.float32)
            vec[0, 0] = 1.0
            return vec

        vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            max_features=2000,
            sublinear_tf=True,
            token_pattern=r"(?u)\b\w+\b",
        )
        tfidf_matrix = vectorizer.fit_transform(texts)

        n_components = min(target_dim, tfidf_matrix.shape[1] - 1, n_samples - 1)
        if n_components < 2:
            # Dense array directly from tfidf
            dense = tfidf_matrix.toarray().astype(np.float32)
            if dense.shape[1] < target_dim:
                pad_width = target_dim - dense.shape[1]
                dense = np.pad(dense, ((0, 0), (0, pad_width)), mode="constant")
            return normalize(dense[:, :target_dim], norm="l2")

        svd = TruncatedSVD(n_components=n_components, random_state=42)
        reduced = svd.fit_transform(tfidf_matrix).astype(np.float32)

        # Pad to target_dim if needed
        if reduced.shape[1] < target_dim:
            pad = np.zeros((n_samples, target_dim - reduced.shape[1]), dtype=np.float32)
            reduced = np.hstack([reduced, pad])

        return normalize(reduced, norm="l2")
