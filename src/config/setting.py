from pydantic_settings import BaseSettings,SettingsConfigDict

class Settings(BaseSettings):
    OPENAI_API_KEY: str
    PRICE_EXCEL_PATH: str
    CHROMA_DB_DIR: str
    ALIAS_PATH: str
    TAVILY_API_KEY:str
    EMBEDDING_MODEL: str = "text-embedding-3-large"
    
    
    model_config = SettingsConfigDict(env_file=".env",extra="ignore")

settings = Settings()

