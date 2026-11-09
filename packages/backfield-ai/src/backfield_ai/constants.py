"""Stable AI model constants shared by API, worker, and future Stylebook code."""

AI_MODEL_KIND_GENERATIVE = "generative"
AI_MODEL_KIND_EMBEDDING = "embedding"
AI_MODEL_KIND_DECISION = "decision"

AI_CAPABILITY_TEXT = "text"
AI_CAPABILITY_JSON = "json"
AI_CAPABILITY_VISION = "vision"
AI_CAPABILITY_EMBEDDING = "embedding"
AI_CAPABILITY_DECISION = "decision"

DEFAULT_AI_CURRENCY = "USD"

# ``BackfieldAiCallRecord.cost_estimate_source`` — how ``estimated_cost`` was produced.
COST_ESTIMATE_SOURCE_LITELLM = "litellm"
COST_ESTIMATE_SOURCE_MANUAL = "manual"
# Token counts priced with the per-token prices saved on the catalog model config, used when
# LiteLLM has no price for the route (e.g. a Bedrock application inference profile ARN).
COST_ESTIMATE_SOURCE_CATALOG_PRICE = "catalog_price"
# No completion response to run ``litellm.completion_cost`` on (e.g. transport error).
COST_ESTIMATE_SOURCE_UNAVAILABLE = "unavailable"

# Organization integration secret keys (encrypted at rest; generic pattern for future vendors).
INTEGRATION_KEY_AI_PROVIDER_OPENAI = "ai.provider.openai"
INTEGRATION_KEY_AI_PROVIDER_ANTHROPIC = "ai.provider.anthropic"
INTEGRATION_KEY_AI_PROVIDER_GEMINI = "ai.provider.gemini"
INTEGRATION_KEY_AI_PROVIDER_OPENROUTER = "ai.provider.openrouter"
INTEGRATION_KEY_AI_PROVIDER_AZURE = "ai.provider.azure"
# Embedding-only provider (Voyage AI makes embedding and rerank models).
INTEGRATION_KEY_AI_PROVIDER_VOYAGE = "ai.provider.voyage"

ORG_AI_PROVIDER_INTEGRATION_KEYS: frozenset[str] = frozenset(
    {
        INTEGRATION_KEY_AI_PROVIDER_OPENAI,
        INTEGRATION_KEY_AI_PROVIDER_ANTHROPIC,
        INTEGRATION_KEY_AI_PROVIDER_GEMINI,
        INTEGRATION_KEY_AI_PROVIDER_OPENROUTER,
        INTEGRATION_KEY_AI_PROVIDER_AZURE,
        INTEGRATION_KEY_AI_PROVIDER_VOYAGE,
    }
)

# Arbitrary vendor credentials saved like presets (`BackfieldOrganizationIntegrationSecret`).
INTEGRATION_KEY_AI_CREDENTIAL_PREFIX = "ai.credential."

AI_PROVIDER_SLUG_BY_INTEGRATION_KEY: dict[str, str] = {
    INTEGRATION_KEY_AI_PROVIDER_OPENAI: "openai",
    INTEGRATION_KEY_AI_PROVIDER_ANTHROPIC: "anthropic",
    INTEGRATION_KEY_AI_PROVIDER_GEMINI: "gemini",
    INTEGRATION_KEY_AI_PROVIDER_OPENROUTER: "openrouter",
    INTEGRATION_KEY_AI_PROVIDER_AZURE: "azure",
    INTEGRATION_KEY_AI_PROVIDER_VOYAGE: "voyage",
}


def is_built_in_ai_provider_integration_key(integration_key: str) -> bool:
    return integration_key in ORG_AI_PROVIDER_INTEGRATION_KEYS


def is_custom_ai_credential_integration_key(integration_key: str) -> bool:
    """Saved credential rows keyed ``ai.credential.<uuid>`` for custom catalog models."""
    return integration_key.startswith(INTEGRATION_KEY_AI_CREDENTIAL_PREFIX)


# Per-project keys for one catalog model (not listed in org credential picker UI).
INTEGRATION_KEY_AI_PROJECT_MODEL_PREFIX = "ai.project_model."


def project_model_override_integration_key(project_id: int, model_config_id: str) -> str:
    """Stable integration_key for one project's override credential on ``model_config_id``."""
    return f"{INTEGRATION_KEY_AI_PROJECT_MODEL_PREFIX}{int(project_id)}.{model_config_id.strip()}"


def is_project_model_override_integration_key(integration_key: str) -> bool:
    return integration_key.startswith(INTEGRATION_KEY_AI_PROJECT_MODEL_PREFIX)


# Organization preset slots for geocoding, search, and S3 (Core API + worker env).
INTEGRATION_KEY_PLATFORM_GEOCODE_EARTH = "platform.geocode.geocode_earth"
INTEGRATION_KEY_PLATFORM_GEOCODIO = "platform.geocode.geocodio"
INTEGRATION_KEY_PLATFORM_BRAVE_SEARCH = "platform.search.brave"
INTEGRATION_KEY_PLATFORM_EXA_SEARCH = "platform.search.exa"
INTEGRATION_KEY_PLATFORM_S3_ACCESS_KEY_ID = "platform.storage.s3_access_key_id"
INTEGRATION_KEY_PLATFORM_S3_SECRET_ACCESS_KEY = "platform.storage.s3_secret_access_key"
INTEGRATION_KEY_PLATFORM_S3_SESSION_TOKEN = "platform.storage.s3_session_token"
INTEGRATION_KEY_PLATFORM_S3_ROLE_ARN = "platform.storage.s3_role_arn"

ORG_PLATFORM_INTEGRATION_KEYS: frozenset[str] = frozenset(
    {
        INTEGRATION_KEY_PLATFORM_GEOCODE_EARTH,
        INTEGRATION_KEY_PLATFORM_GEOCODIO,
        INTEGRATION_KEY_PLATFORM_BRAVE_SEARCH,
        INTEGRATION_KEY_PLATFORM_EXA_SEARCH,
        INTEGRATION_KEY_PLATFORM_S3_ACCESS_KEY_ID,
        INTEGRATION_KEY_PLATFORM_S3_SECRET_ACCESS_KEY,
        INTEGRATION_KEY_PLATFORM_S3_SESSION_TOKEN,
        INTEGRATION_KEY_PLATFORM_S3_ROLE_ARN,
    }
)


def is_platform_integration_key(integration_key: str) -> bool:
    return integration_key in ORG_PLATFORM_INTEGRATION_KEYS


# Project-level default model roles (graph nodes resolve these at execution time).
AI_DEFAULT_ROLE_GEOCODE_ROUTER = "geocode.router"
AI_DEFAULT_ROLE_GEOCODE_EVALUATION = "geocode.evaluation"

AI_DEFAULT_ROLE_SEMANTIC_EMBEDDING = "semantic.embedding"
# Article passage search: articles are split into passages and embedded with this model
# (a Voyage context model chunks articles itself). Unset means article search keeps using
# whole-article embeddings from the Embed Text node.
AI_DEFAULT_ROLE_SEMANTIC_ARTICLE_EMBEDDING = "semantic.article_embedding"
# Legacy HyDE role; still read by resolver for existing DB rows.
AI_DEFAULT_ROLE_SEMANTIC_HYDE = "semantic.hyde"
AI_DEFAULT_ROLE_GENERATIVE_DEFAULT = "generative.default"

EMBEDDING_DEFAULT_ROLES: frozenset[str] = frozenset(
    {AI_DEFAULT_ROLE_SEMANTIC_EMBEDDING, AI_DEFAULT_ROLE_SEMANTIC_ARTICLE_EMBEDDING}
)

PROJECT_AI_DEFAULT_ROLES: frozenset[str] = frozenset(
    {
        AI_DEFAULT_ROLE_GEOCODE_ROUTER,
        AI_DEFAULT_ROLE_GEOCODE_EVALUATION,
        AI_DEFAULT_ROLE_SEMANTIC_EMBEDDING,
        AI_DEFAULT_ROLE_SEMANTIC_ARTICLE_EMBEDDING,
        AI_DEFAULT_ROLE_GENERATIVE_DEFAULT,
    }
)
