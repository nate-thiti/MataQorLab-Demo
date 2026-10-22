from pydantic import Field, AliasChoices, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    # App Configurations
    PROJECT_NAME: str = "SaaS AI Data Analysis API"
    API_V1_STR: str = "/api/v1"

    # Runtime environment: production fails closed on missing workflow RPC.
    APP_ENV: str = Field(
        default="development",
        validation_alias=AliasChoices("APP_ENV", "ENVIRONMENT"),
    )
    # None = auto (allow fallback outside production). Explicit True/False overrides.
    WORKFLOW_ALLOW_BEGIN_STEP_FALLBACK: Optional[bool] = None

    # Phase 5: conversational data-setup orchestration (wizard remains available).
    ENABLE_CONVERSATIONAL_DATA_SETUP: bool = True
    # Optional dedicated model; empty → reuse LIGHT / FREE / PREMIUM tier resolution.
    LLM_MODEL_ORCHESTRATOR: str = ""
    MAX_ORCHESTRATOR_ACTIONS: int = 3
    MAX_CONTROLLER_ACTIONS_PER_USER_TURN: int = 3
    # Phase 7.2.2 performance diagnostics (ops only).
    CONTROLLER_SLOW_TURN_MS: int = 30000
    LLM_SLOW_CALL_MS: int = 15000
    WORKFLOW_STEP_SLOW_MS: int = 10000
    DB_SLOW_AGGREGATE_MS: int = 5000
    # Phase 7.2: at most one setup clarification question per controller turn.
    MAX_SETUP_QUESTIONS_PER_TURN: int = 1

    # Phase 7: stuck-workflow diagnostics (do not auto-mutate state).
    WORKFLOW_RUNNING_STUCK_MINUTES: float = 120.0
    WORKFLOW_AWAITING_USER_STALE_HOURS: float = 24.0
    
    # LLM provider (OpenAI-compatible API — OpenRouter, Groq, Together, etc.)
    LLM_API_KEY: str = Field(validation_alias=AliasChoices("LLM_API_KEY", "OPENROUTER_API_KEY"))

    LLM_MODEL_FREE: str = Field(
        default="openai/gpt-oss-120b:free",
        validation_alias=AliasChoices("LLM_MODEL_FREE", "OPENROUTER_MODEL_FREE"),
    )
    LLM_MODEL_FREE_FALLBACK: str = Field(
        default="google/gemma-4-26b-a4b-it:free",
        validation_alias=AliasChoices("LLM_MODEL_FREE_FALLBACK", "OPENROUTER_MODEL_FREE_FALLBACK"),
    )

    LLM_MODEL_PREMIUM: str = Field(
        default="google/gemma-4-31b-it:free",
        validation_alias=AliasChoices("LLM_MODEL_PREMIUM", "OPENROUTER_MODEL_PREMIUM"),
    )
    LLM_MODEL_PREMIUM_FALLBACK: str = Field(
        default="nousresearch/hermes-3-llama-3.1-405b:free",
        validation_alias=AliasChoices("LLM_MODEL_PREMIUM_FALLBACK", "OPENROUTER_MODEL_PREMIUM_FALLBACK"),
    )

    # Optional intent-aware model routing. Empty values keep the tier defaults.
    LLM_MODEL_LIGHT: str = ""
    LLM_MODEL_REASONING: str = ""

    LLM_BASE_URL: str = Field(
        default="https://openrouter.ai/api/v1",
        validation_alias=AliasChoices("LLM_BASE_URL", "OPENROUTER_BASE_URL"),
    )

    # OpenRouter hosting provider routing (ignored for non-OpenRouter LLM_BASE_URL)
    # Comma-separated slugs from model page, e.g. deepinfra/bf16
    LLM_PROVIDER_ORDER: str = ""
    LLM_PROVIDER_ONLY: str = ""
    LLM_PROVIDER_ALLOW_FALLBACKS: bool = False

    # HTTP Referer & Title (some providers e.g. OpenRouter require these headers)
    APP_REFERER: str = "https://github.com/your-org/your-repo"
    APP_TITLE: str = "MataqorLab AI"

    # Chat request timeout (seconds) — file prep + LLM can exceed 60s on free models
    CHAT_REQUEST_TIMEOUT_SECONDS: float = 300.0

    # Supabase client timeouts (seconds). Storage default in supabase-py is only 20s.
    SUPABASE_POSTGREST_TIMEOUT_SECONDS: float = 120.0
    STORAGE_DOWNLOAD_TIMEOUT_SECONDS: float = 120.0

    # Autonomous agent loop
    AGENT_SESSION_DIR: str = "data/agent_sessions"
    AGENT_MAX_STEPS: int = 5
    AGENT_DF_CACHE_MAX_MB: int = 50
    AGENT_MAX_LLM_CALLS_PER_QUESTION: int = 10
    AGENT_MAX_TOOL_CALLS_PER_QUESTION: int = 6
    AGENT_MAX_TOOL_COST_UNITS: int = 12

    # Pro/Deep Python analysis runs only in a separately deployed OCI/gVisor
    # sandbox. Empty/disabled configuration fails closed; there is no local
    # subprocess fallback in the API or worker process.
    PYTHON_SANDBOX_ENABLED: bool = False
    PYTHON_SANDBOX_RUNNER_URL: str = ""
    PYTHON_SANDBOX_RUNNER_TOKEN: str = ""
    PYTHON_SANDBOX_STAGE_DIR: str = "data/python_sandbox_stage"
    PYTHON_SANDBOX_POLL_SECONDS: int = 2
    PYTHON_SANDBOX_MAX_CPU: int = 2
    PYTHON_SANDBOX_MAX_MEMORY_MB: int = 2048
    PYTHON_SANDBOX_MAX_RUNTIME_SECONDS: int = 60
    PYTHON_SANDBOX_MAX_INPUT_BYTES: int = 524_288_000
    PYTHON_SANDBOX_MAX_OUTPUT_BYTES: int = 10_485_760

    # Large dataset analytics (DuckDB)
    DUCKDB_ROW_THRESHOLD: int = 50000
    # Skip expensive extended analytics (DISTINCT/corr/outliers) above this row count
    EXTENDED_ANALYTICS_ROW_THRESHOLD: int = 1_000_000

    # Upload / ingest limits
    MAX_UPLOAD_FILE_BYTES: int = 524_288_000  # 500 MB
    MAX_EXCEL_FILE_BYTES: int = 25_000_000  # 25 MB — use Parquet/CSV above this

    # LLM context: cap pre-computed metrics block
    MAX_LLM_METRICS_CHARS: int = 12_000

    # On-disk cache for ingested datasets (avoids re-download every chat)
    DATASET_INGEST_CACHE_DIR: str = "data/dataset_cache"

    # Disk-backed analytics cache (L2; survives process restarts)
    ANALYTICS_DISK_CACHE_DIR: str = "data/analytics_cache"

    # REST API fetch / pagination
    API_FETCH_TIMEOUT_SECONDS: int = 120
    API_PAGINATION_MAX_PAGES: int = 10_000

    # Excel streaming ingest threshold (bytes); above this use openpyxl read_only
    EXCEL_STREAMING_BYTES_THRESHOLD: int = 2_000_000

    # SQL query execution timeout (seconds) for live database connections
    SQL_QUERY_TIMEOUT_SECONDS: int = 300

    # Max rows for DB sync dumps and live SELECT (unified policy)
    SQL_SYNC_ROW_LIMIT: int = 10_000_000
    MAX_SQL_RESULT_ROWS: int = 10_000_000

    # Chunk size when streaming SQL results to disk (avoids full DataFrame in RAM)
    SQL_STREAM_CHUNK_SIZE: int = 25000

    # In-memory analytics cache TTL (seconds); file uploads only
    ANALYTICS_CACHE_TTL_SECONDS: int = 1800

    # Agent session persistence: "file" (local disk) or "supabase" (multi-instance)
    AGENT_SESSION_BACKEND: str = "file"
    AGENT_SESSION_STORAGE_BUCKET: str = "business-data"

    # Scheduled ETL worker. Database leases make multiple backend replicas safe.
    ETL_SCHEDULER_ENABLED: bool = True
    ETL_SCHEDULER_POLL_SECONDS: int = 30
    ETL_SCHEDULER_BATCH_SIZE: int = 3
    ETL_SCHEDULER_LEASE_SECONDS: int = 900
    ETL_MAX_SCHEDULES_PER_USER: int = 10
    WORKER_HEARTBEAT_SECONDS: int = 30

    # Smart Alert evaluator. Disabled until smart_alert_evaluator.sql is applied.
    SMART_ALERT_SCHEDULER_ENABLED: bool = False
    SMART_ALERT_POLL_SECONDS: int = 30
    SMART_ALERT_BATCH_SIZE: int = 5
    SMART_ALERT_LEASE_SECONDS: int = 300
    SMART_ALERT_DELIVERY_ATTEMPTS: int = 2
    SMART_ALERT_DELIVERY_TIMEOUT_SECONDS: int = 15
    SMART_ALERT_SLACK_WEBHOOK_URL: str = ""
    SMART_ALERT_TEAMS_WEBHOOK_URL: str = ""
    SMART_ALERT_WEBHOOK_URL: str = ""

    # Scheduled report delivery. Secrets stay server-side.
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_FROM_NAME: str = "MataQorLab"
    SMTP_USE_TLS: bool = True
    SMTP_USE_SSL: bool = False
    DELIVERY_PUBLIC_BASE_URL: str = ""
    DELIVERY_LLM_ENABLED: bool = True
    DELIVERY_LLM_MAX_TOKENS: int = 500
    DELIVERY_TIMEOUT_SECONDS: int = 30

    # Supabase Configurations
    # AliasChoices keeps VITE_SUPABASE_URL working for older .env files.
    SUPABASE_URL: str = Field(validation_alias=AliasChoices("SUPABASE_URL", "VITE_SUPABASE_URL"))
    SUPABASE_SERVICE_ROLE_KEY: str

    # 32 random bytes encoded as URL-safe base64. Server-side only.
    CONNECTION_SECRET_KEY: str = ""
    ALLOW_PRIVATE_CONNECTORS: bool = False
    ALLOW_INSECURE_HTTP_CONNECTORS: bool = False

    # Stripe Configurations (Sandbox Mode)
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    FRONTEND_URL: str = "http://localhost:3000"

    # Comma-separated browser origins allowed to call the API (production + local dev).
    CORS_ORIGINS: str = ""

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _normalize_cors_origins(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()

    def cors_origins_list(self) -> list[str]:
        if self.CORS_ORIGINS:
            return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]
        defaults = {
            self.FRONTEND_URL,
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
        }
        return sorted(defaults)

    # จัดการการโหลดไฟล์ .env
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8", 
        extra="ignore"
    )

settings = Settings()
