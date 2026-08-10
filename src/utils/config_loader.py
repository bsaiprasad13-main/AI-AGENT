"""Typed configuration loaders for pipeline settings and product definitions."""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()


class IngestionConfig(BaseModel):
    default_rolling_window_weeks: int = Field(default=10)
    min_rolling_window_weeks: int = Field(default=8)
    max_rolling_window_weeks: int = Field(default=12)
    language: str = Field(default="en")
    country: str = Field(default="in")
    max_reviews_per_fetch: int = Field(default=5000)
    rate_limit_retries: int = Field(default=3)
    rate_limit_backoff_seconds: float = Field(default=2.0)


class PreprocessingConfig(BaseModel):
    min_word_count: int = Field(default=8)
    filter_all_emojis: bool = Field(default=True)
    filter_non_english: bool = Field(default=True)
    filter_emojis_only: bool = Field(default=True)
    mask_usernames: bool = Field(default=True)
    enable_prompt_injection_shield: bool = Field(default=True)
    redact_phone: bool = Field(default=True)
    redact_email: bool = Field(default=True)
    redact_upi: bool = Field(default=True)
    redact_bank_demat: bool = Field(default=True)
    redact_pan_aadhaar: bool = Field(default=True)


class EmbeddingConfig(BaseModel):
    model_name: str = Field(default="sentence-transformers/all-MiniLM-L6-v2")
    batch_size: int = Field(default=64)
    normalize_embeddings: bool = Field(default=True)


class UMAPConfig(BaseModel):
    n_neighbors: int = Field(default=15)
    n_components: int = Field(default=5)
    min_dist: float = Field(default=0.1)
    metric: str = Field(default="cosine")
    random_state: int = Field(default=42)


class HDBSCANConfig(BaseModel):
    min_cluster_size: int = Field(default=10)
    min_samples: int = Field(default=5)
    metric: str = Field(default="euclidean")
    cluster_selection_method: str = Field(default="eom")


class FallbackHierarchyConfig(BaseModel):
    enabled: bool = Field(default=True)
    min_cluster_size_fallback: int = Field(default=5)


class ImpactScoringConfig(BaseModel):
    count_weight: float = Field(default=1.0)
    rating_invert_scale: float = Field(default=5.0)
    thumbs_up_log_base: int = Field(default=10)


class SynthesisConfig(BaseModel):
    max_themes: int = Field(default=5)
    min_themes: int = Field(default=3)
    reviews_per_cluster_sample: int = Field(default=8)
    max_tokens_per_review: int = Field(default=150)


class QuoteGroundingConfig(BaseModel):
    similarity_threshold: float = Field(default=0.95)
    use_fuzzy_fallback: bool = Field(default=True)
    quotes_per_theme: int = Field(default=2)


class ReasoningConfig(BaseModel):
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    umap: UMAPConfig = Field(default_factory=UMAPConfig)
    hdbscan: HDBSCANConfig = Field(default_factory=HDBSCANConfig)
    fallback_hierarchy: FallbackHierarchyConfig = Field(
        default_factory=FallbackHierarchyConfig
    )
    impact_scoring: ImpactScoringConfig = Field(default_factory=ImpactScoringConfig)
    synthesis: SynthesisConfig = Field(default_factory=SynthesisConfig)
    quote_grounding: QuoteGroundingConfig = Field(default_factory=QuoteGroundingConfig)


class RenderingConfig(BaseModel):
    doc_heading_prefix: str = Field(default="Week")
    anchor_id_template: str = Field(default="h.{product_id}_{iso_week}")
    enable_dark_mode_email_css: bool = Field(default=True)


class StorageConfig(BaseModel):
    cache_dir: str = Field(default="data/cache")
    audit_db_path: str = Field(default="data/audit.db")


class MCPToolDefinition(BaseModel):
    endpoint: str
    method: str = Field(default="POST")
    required_parameters: List[str] = Field(default_factory=list)


class MCPConfig(BaseModel):
    server_url: str = Field(default="https://web-production-c16ea.up.railway.app")
    api_key: str = Field(default="")
    timeout_seconds: float = Field(default=30.0)
    max_retries: int = Field(default=3)
    retry_backoff_seconds: float = Field(default=2.0)
    tools: Dict[str, MCPToolDefinition] = Field(default_factory=dict)


class PipelineSettings(BaseModel):
    ingestion: IngestionConfig = Field(default_factory=IngestionConfig)
    preprocessing: PreprocessingConfig = Field(default_factory=PreprocessingConfig)
    reasoning: ReasoningConfig = Field(default_factory=ReasoningConfig)
    rendering: RenderingConfig = Field(default_factory=RenderingConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)


class ProductTarget(BaseModel):
    product_id: str
    display_name: str
    package_name: str
    platform: str = Field(default="play_store")
    google_doc_id: str
    recipients: List[str] = Field(default_factory=list)
    valid_verticals: List[str] = Field(default_factory=list)


class ProductsConfig(BaseModel):
    products: Dict[str, ProductTarget] = Field(default_factory=dict)


def get_project_root() -> Path:
    """Returns absolute root path of the project."""
    return Path(__file__).resolve().parent.parent.parent


def load_settings(custom_path: Optional[str] = None) -> PipelineSettings:
    """Loads and validates pipeline settings from settings.yaml."""
    settings_file = (
        Path(custom_path)
        if custom_path
        else get_project_root() / "config" / "settings.yaml"
    )

    if not settings_file.exists():
        settings = PipelineSettings()
    else:
        with open(settings_file, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f) or {}
        settings = PipelineSettings(**raw_data)

    # Environment variable overrides
    env_mcp_url = os.getenv("MCP_SERVER_URL")
    if env_mcp_url:
        settings.mcp.server_url = env_mcp_url

    env_mcp_key = os.getenv("MCP_API_KEY") or os.getenv("API_KEY")
    if env_mcp_key:
        settings.mcp.api_key = env_mcp_key

    return settings


def load_products(custom_path: Optional[str] = None) -> ProductsConfig:
    """Loads and validates products definitions from products.yaml."""
    products_file = (
        Path(custom_path)
        if custom_path
        else get_project_root() / "config" / "products.yaml"
    )

    if not products_file.exists():
        return ProductsConfig()

    with open(products_file, "r", encoding="utf-8") as f:
        raw_data = yaml.safe_load(f) or {}

    products_config = ProductsConfig(**raw_data)
    env_doc_id = os.getenv("GOOGLE_DOC_ID")
    if env_doc_id and "groww" in products_config.products:
        products_config.products["groww"].google_doc_id = env_doc_id

    return products_config


def get_product(product_key: str = "groww") -> ProductTarget:
    """Convenience helper to retrieve a specific product configuration."""
    products_cfg = load_products()
    if product_key not in products_cfg.products:
        raise KeyError(
            f"Product '{product_key}' not found in products.yaml. Available: {list(products_cfg.products.keys())}"
        )
    return products_cfg.products[product_key]
