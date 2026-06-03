from functools import lru_cache
from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    APP_NAME: str = 'ai-agent-template'
    APP_ENV: str = 'local'
    LOG_LEVEL: str = 'INFO'
    API_HOST: str = '0.0.0.0'
    API_PORT: int = 8000
    CORS_ORIGINS: str = 'http://localhost:5173'

    LLM_PROVIDER: Literal['mock','oci_openai','oci_sdk','openai_compatible'] = 'mock'
    LLM_TEMPERATURE: float = 0.2
    LLM_MAX_TOKENS: int = 2048
    LLM_TIMEOUT_SECONDS: int = 120

    OCI_GENAI_BASE_URL: str = 'https://inference.generativeai.sa-saopaulo-1.oci.oraclecloud.com/openai/v1'
    OCI_GENAI_MODEL: str = 'openai.gpt-4.1'
    OCI_GENAI_API_KEY: str | None = None
    OCI_GENAI_PROJECT_OCID: str | None = None
    OCI_CONFIG_FILE: str = '~/.oci/config'
    OCI_PROFILE: str = 'DEFAULT'
    OCI_COMPARTMENT_ID: str | None = None
    OCI_REGION: str = 'sa-saopaulo-1'

    SESSION_REPOSITORY_PROVIDER: Literal['memory','sqlite','autonomous','oracle','mongodb'] = 'memory'
    MEMORY_REPOSITORY_PROVIDER: Literal['memory','sqlite','autonomous','oracle','mongodb'] = 'memory'
    CHECKPOINT_REPOSITORY_PROVIDER: Literal['memory','sqlite','autonomous','oracle','mongodb'] = 'memory'

    # LangGraph enterprise checkpointing
    ENABLE_RESILIENT_CHECKPOINTER: bool = True
    ENABLE_CHECKPOINT_INTEGRITY: bool = True
    ENABLE_CHECKPOINT_COMPACTION: bool = True
    CHECKPOINT_COMPACT_EVERY: int = 50
    CHECKPOINT_KEEP_LAST: int = 20
    CHECKPOINT_RECOVERY_SCAN_LIMIT: int = 25
    CHECKPOINT_RETRY_MAX_ATTEMPTS: int = 3
    CHECKPOINT_RETRY_BASE_DELAY_SECONDS: float = 0.05
    CHECKPOINT_RETRY_MAX_DELAY_SECONDS: float = 1.0
    CHECKPOINT_RETRY_JITTER_SECONDS: float = 0.05
    USAGE_REPOSITORY_PROVIDER: Literal['sqlite','autonomous','oracle'] = 'sqlite'

    ADB_USER: str | None = None
    ADB_PASSWORD: str | None = None
    ADB_DSN: str | None = None
    ADB_WALLET_LOCATION: str | None = None
    ADB_WALLET_PASSWORD: str | None = None
    ADB_TABLE_PREFIX: str = 'AGENTFW'

    MONGODB_URI: str = 'mongodb://localhost:27017'
    MONGODB_DATABASE: str = 'agent_platform'
    REDIS_URL: str = 'redis://localhost:6379/0'
    ENABLE_REDIS_CACHE: bool = False
    CACHE_KEY_PREFIX: str = 'agentfw'

    VECTOR_STORE_PROVIDER: Literal['memory','sqlite','autonomous','oracle','mongodb'] = 'memory'
    GRAPH_STORE_PROVIDER: Literal['memory','autonomous','oracle'] = 'memory'
    ORACLE_GRAPH_NAME: str = 'AGENTFW_GRAPH'
    ORACLE_GRAPH_AUTO_CREATE: bool = False
    RAG_TOP_K: int = 5
    EMBEDDING_PROVIDER: Literal['mock','oci'] = 'mock'
    OCI_EMBEDDING_MODEL: str = 'cohere.embed-multilingual-v3.0'

    ENABLE_LANGFUSE: bool = False
    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_SECRET_KEY: str | None = None
    LANGFUSE_HOST: str = 'https://cloud.langfuse.com'
    MODEL_PRICES_JSON: str | None = None
    USD_BRL_RATE: str = '5.0'
    ENABLE_OTEL: bool = False
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = None
    OTEL_SERVICE_NAME: str = 'ai-agent-template'

    ENABLE_ANALYTICS: bool = False
    ANALYTICS_PROVIDERS: str = 'oci_streaming'
    GCP_PUBSUB_TOPIC_PATH: str | None = None
    AGENT_PUBSUB_TOPIC: str | None = None
    GCP_PROJECT_ID: str | None = None
    GCP_PUBSUB_TOPIC: str | None = None
    GCP_PUBSUB_TIMEOUT_SECONDS: float = 30.0
    ANALYTICS_FAIL_SILENT: bool = True

    ENABLE_OCI_STREAMING: bool = False
    OCI_STREAM_ENDPOINT: str | None = None
    OCI_STREAM_OCID: str | None = None
    OCI_STREAM_PARTITION_KEY: str = 'agent-events'

    ENABLE_INPUT_GUARDRAILS: bool = True
    ENABLE_OUTPUT_GUARDRAILS: bool = True
    ENABLE_PARALLEL_GUARDRAILS: bool = True
    GUARDRAILS_FAIL_FAST: bool = True
    ENABLE_JUDGES: bool = True
    ENABLE_SUPERVISOR: bool = True
    ENABLE_OUTPUT_SUPERVISOR: bool = True
    OUTPUT_SUPERVISOR_MAX_RETRIES: int = 3
    GUARDRAILS_CONFIG_PATH: str = './config/guardrails.yaml'
    JUDGES_CONFIG_PATH: str = './config/judges.yaml'
    PROMPT_POLICY_PATH: str = './config/prompt_policy.yaml'
    AGENTS_CONFIG_PATH: str = './config/agents.yaml'
    ROUTING_CONFIG_PATH: str = './config/routing.yaml'
    ENABLE_LLM_ROUTER: bool = False
    ROUTING_MODE: Literal['router','supervisor'] = 'router'

    # MCP / Tooling
    ENABLE_MCP_TOOLS: bool = True
    MCP_SERVERS_CONFIG_PATH: str = './config/mcp_servers.yaml'
    TOOLS_CONFIG_PATH: str = './config/tools.yaml'
    IDENTITY_CONFIG_PATH: str = './config/identity.yaml'
    MCP_PARAMETER_MAPPING_PATH: str = './config/mcp_parameter_mapping.yaml'
    MCP_TOOL_TIMEOUT_SECONDS: int = 30

    DEFAULT_CHANNEL: str = 'web'
    ENABLE_VOICE_ADAPTER: bool = True
    ENABLE_WHATSAPP_ADAPTER: bool = True
    ENABLE_TEXT_ADAPTER: bool = True


    # FIRST-ready runtime options
    SQLITE_DB_PATH: str = './data/agent_framework.db'
    ENABLE_SSE: bool = True
    SSE_KEEPALIVE_SECONDS: float = 15.0
    SSE_EVENT_REPLAY_LIMIT: int = 100
    ENABLE_MESSAGE_IDEMPOTENCY: bool = True
    ENABLE_LOCAL_CACHE: bool = True
    CACHE_TTL_SECONDS: int = 300
    CACHE_BACKEND_PROVIDER: Literal['memory','sqlite','autonomous','oracle'] = 'memory'
    SSE_STORE_PROVIDER: Literal['sqlite','autonomous','oracle'] | None = None

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
