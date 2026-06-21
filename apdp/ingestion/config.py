from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    # Flutterwave
    FLUTTERWAVE_SECRET_KEY: str = ""
    FLUTTERWAVE_WEBHOOK_HASH: str = ""

    # Paystack
    PAYSTACK_SECRET_KEY: str = ""
    PAYSTACK_WEBHOOK_SECRET: str = ""

    # MTN MoMo
    MTN_COLLECTIONS_SUBSCRIPTION_KEY: str = ""
    MTN_API_USER_ID: str = ""
    MTN_API_KEY: str = ""
    MTN_BASE_URL: str = "https://sandbox.momodeveloper.mtn.com"
    MTN_TARGET_ENVIRONMENT: str = "sandbox"

    # Monnify
    MONNIFY_API_KEY: str = ""
    MONNIFY_SECRET_KEY: str = ""
    MONNIFY_CONTRACT_CODE: str = ""
    MONNIFY_BASE_URL: str = "https://sandbox.monnify.com"

    # Mono (open banking — batch EOD)
    MONO_SECRET_KEY: str = ""

    # Postgres (used by mono-batch service and future dbt)
    DATABASE_URL: str = "postgresql://platform_user:platform_pass@postgres:5432/payment_platform"

    # App
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"


settings = Settings()