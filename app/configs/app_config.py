# -*- coding: utf-8 -*-
# @Time    : 2025/07/08 6:55 AM
# @Author  : Galleons
# @File    : app_config.py

"""
这里是文件说明
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from enum import Enum
import os

ROOT_DIR = Path(__file__).resolve().parents[2] / ".env"


# Define environment types
class Environment(str, Enum):
    """Application environment types.

    Defines the possible environments the application can run in:
    development, staging, production, and test.
    """

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


# Determine environment
def get_environment() -> Environment:
    """Get the current environment.

    Returns:
        Environment: The current environment (development, staging, production, or test)
    """
    match os.getenv("APP_ENV", "development").lower():
        case "production" | "prod":
            return Environment.PRODUCTION
        case "staging" | "stage":
            return Environment.STAGING
        case "test":
            return Environment.TEST
        case _:
            return Environment.DEVELOPMENT


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR, env_file_encoding="utf-8", extra="ignore")

    # langfuse platform
    public_key: str | None = None
    secret_key: str | None = None
    localhost: str | None = "https://cloud.langfuse.com"
    cloud_host: str | None = "https://cloud.langfuse.com"

    ENVIRONMENT: str = get_environment()
