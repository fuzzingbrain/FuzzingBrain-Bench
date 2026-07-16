"""Model knowledge: catalog, provider routing, and pricing — single source."""
from fbbench.models.catalog import (
    AGENT_PREFIX,
    CATALOG,
    LOCAL_PROVIDERS,
    OPENAI_COMPAT,
    PROVIDER_DEFAULT,
    PROVIDER_KEY_ENV,
    PROVIDERS,
    SUPPORTED_MODELS,
    agent_label,
    default_sweep,
    needs_key,
    provider_for,
    route_provider,
    strip_agent_label,
)
from fbbench.models.pricing import PRICES, cost_usd

__all__ = [
    "CATALOG", "PROVIDERS", "SUPPORTED_MODELS",
    "PROVIDER_KEY_ENV", "PROVIDER_DEFAULT",
    "OPENAI_COMPAT", "LOCAL_PROVIDERS", "needs_key",
    "provider_for", "route_provider", "default_sweep",
    "AGENT_PREFIX", "agent_label", "strip_agent_label",
    "PRICES", "cost_usd",
]
