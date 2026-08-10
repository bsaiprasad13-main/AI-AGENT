"""Unit tests for configuration loaders."""

from src.utils.config_loader import load_settings, load_products, get_product


def test_load_settings():
    settings = load_settings()
    assert settings.ingestion.default_rolling_window_weeks == 10
    assert settings.preprocessing.redact_phone is True
    assert settings.preprocessing.redact_upi is True
    assert settings.reasoning.quote_grounding.similarity_threshold == 0.95
    assert settings.reasoning.hdbscan.min_cluster_size == 10
    assert settings.mcp.server_url == "https://web-production-c16ea.up.railway.app"
    assert "append_to_doc" in settings.mcp.tools
    assert "create_email_draft" in settings.mcp.tools


def test_load_products():
    products_cfg = load_products()
    assert "groww" in products_cfg.products
    groww = products_cfg.products["groww"]
    assert groww.package_name == "com.nextbillion.groww"
    assert groww.platform == "play_store"
    assert "Stocks & Equity" in groww.valid_verticals


def test_get_product_helper():
    product = get_product("groww")
    assert product.product_id == "groww"
    assert product.package_name == "com.nextbillion.groww"
