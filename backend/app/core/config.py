from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    应用配置类，使用 Pydantic 进行类型验证和管理。
    它会自动从环境变量或 .env 文件中读取配置。
    """
    # model_config 用于配置 Pydantic 的行为
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding='utf-8', extra='ignore')

    # 数据库连接 URL
    # 如果环境变量中没有定义，则使用默认的 SQLite 文件数据库
    DATABASE_URL: str = "sqlite:///./agenthub.db"

# 创建一个全局可用的配置实例
settings = Settings()