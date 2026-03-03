# -*- coding: utf-8 -*-
# @Time   : 8/1/25 3:35 PM
# @Author : Galleons
# @File   : rag_config.py

"""
这里是文件说明
"""

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict


class RAGConfig(BaseSettings):
    model_config = SettingsConfigDict(
        # read from dotenv format config file
        env_file=".env",
        env_file_encoding="utf-8",
        # ignore extra attributes
        extra="ignore",
    )

    # Before adding any config,
    # please consider to arrange it in the proper config group of existed or added
    # for better readability and maintainability.
    # Thanks for your concentration and consideration.

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
        )
