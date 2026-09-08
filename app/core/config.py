"""
应用配置模块
基于 pydantic-settings 从 .env 文件加载配置。
"""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MySQLSettings(BaseSettings):
    """MySQL 数据库配置"""
    host: str = Field(default="127.0.0.1", description="MySQL 主机地址")
    port: int = Field(default=3306, description="MySQL 端口")
    user: str = Field(default="root", description="MySQL 用户名")
    password: str = Field(default="", description="MySQL 密码")
    db: str = Field(default="gofilm", description="MySQL 数据库名")
    charset: str = Field(default="utf8mb4", description="MySQL 字符集")

    @property
    def async_url(self) -> str:
        # ⚠️ 已修复:必须是 aiomysql,绝不能出现 asyncmy
        return (
            f"mysql+aiomysql://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.db}?charset={self.charset}"
        )


class RedisSettings(BaseSettings):
    """Redis 配置"""
    host: str = Field(default="127.0.0.1", description="Redis 主机地址")
    port: int = Field(default=6379, description="Redis 端口")
    db: int = Field(default=0, description="Redis 数据库编号")
    password: str = Field(default="", description="Redis 密码(空字符串表示无密码)")

    @property
    def url(self) -> str:
        auth = f":{self.password}@" if self.password else ""
        return f"redis://{auth}{self.host}:{self.port}/{self.db}"


class SpiderSettings(BaseSettings):
    """爬虫配置"""
    concurrency: int = Field(default=8, description="最大并发数")
    delay_ms: int = Field(default=500, description="单个请求间隔(毫秒)")
    timeout: int = Field(default=15, description="单次请求超时(秒)")
    max_retries: int = Field(default=3, description="失败最大重试次数")


class Settings(BaseSettings):
    app_name: str = "GoFilm-Python"
    app_env: str = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    mysql: MySQLSettings = MySQLSettings()
    redis: RedisSettings = RedisSettings()
    spider: SpiderSettings = SpiderSettings()

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
