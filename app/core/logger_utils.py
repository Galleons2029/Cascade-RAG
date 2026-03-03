# -*- coding: utf-8 -*-
# @Time   : 2025/8/14 09:46
# @Author : Galleons
# @File   : logger_utils.py

"""Logging configuration and setup for the application.

This module provides structured logging configuration using structlog,
with environment-specific formatters and handlers. It supports both
console-friendly development logging and JSON-formatted production logging.
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import (
    Any,
    List,
)

import structlog

from app.configs import (
    Environment,
    agent_config as settings,
)


def get_logger(cls: str):
    return structlog.get_logger().bind(cls=cls)


# Helpers are defined up-front so logging still works during interpreter shutdown.
def _safe_environment_value() -> str:
    """Return the environment label even if settings is partially torn down."""
    default = Environment.DEVELOPMENT.value
    try:
        env = getattr(settings, "ENVIRONMENT", None)
    except Exception:  # pragma: no cover - defensive during shutdown
        return default

    if isinstance(env, Environment):
        return env.value
    if env is None:
        return default
    return getattr(env, "value", str(env))


# Ensure log directory exists
settings.LOG_DIR.mkdir(parents=True, exist_ok=True)


def get_log_file_path() -> Path:
    """Get the current log file path based on date and environment.

    Returns:
        Path: The path to the log file
    """
    env_prefix = _safe_environment_value()
    return settings.LOG_DIR / f"{env_prefix}-{datetime.now().strftime('%Y-%m-%d')}.jsonl"


class JsonlFileHandler(logging.Handler):
    """Custom handler for writing JSONL logs to daily files."""

    def __init__(self, file_path: Path):
        """Initialize the JSONL file handler.

        Args:
            file_path: Path to the log file where entries will be written.
        """
        super().__init__()
        self.file_path = file_path
        self.environment = _safe_environment_value()

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a record to the JSONL file."""
        try:
            log_entry = {
                "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                "level": record.levelname,
                "message": record.getMessage(),
                "module": record.module,
                "function": record.funcName,
                "filename": record.pathname,
                "line": record.lineno,
                "environment": self.environment,
            }
            if hasattr(record, "extra"):
                log_entry.update(record.extra)

            with open(self.file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        """Close the handler."""
        super().close()


def get_structlog_processors(include_file_info: bool = True) -> List[Any]:
    """Get the structlog processors based on configuration.

    Args:
        include_file_info: Whether to include file information in the logs

    Returns:
        List[Any]: List of structlog processors
    """
    # Set up processors that are common to both outputs
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    # Add callsite parameters if file info is requested
    if include_file_info:
        processors.append(
            structlog.processors.CallsiteParameterAdder(
                {
                    structlog.processors.CallsiteParameter.FILENAME,
                    structlog.processors.CallsiteParameter.FUNC_NAME,
                    structlog.processors.CallsiteParameter.LINENO,
                    structlog.processors.CallsiteParameter.MODULE,
                    structlog.processors.CallsiteParameter.PATHNAME,
                }
            )
        )

    # Add environment info
    env_value = _safe_environment_value()
    processors.append(lambda _, __, event_dict, env=env_value: {**event_dict, "environment": env})

    return processors


def setup_logging() -> None:
    """Configure structlog with different formatters based on environment.

    In development: pretty console output
    In staging/production: structured JSON logs
    """
    # Create file handler for JSON logs
    file_handler = JsonlFileHandler(get_log_file_path())
    file_handler.setLevel(settings.LOG_LEVEL)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(settings.LOG_LEVEL)

    # Get shared processors
    shared_processors = get_structlog_processors(
        # Include detailed file info only in development and test
        include_file_info=settings.ENVIRONMENT in [Environment.DEVELOPMENT, Environment.TEST]
    )

    # Configure standard logging
    logging.basicConfig(
        format="%(message)s",
        level=settings.LOG_LEVEL,
        handlers=[file_handler, console_handler],
    )

    # Configure structlog based on environment
    if settings.LOG_FORMAT == "console":
        # Development-friendly console logging
        structlog.configure(
            processors=[
                *shared_processors,
                # Use ConsoleRenderer for pretty output to the console
                structlog.dev.ConsoleRenderer(),
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )
    else:
        # Production JSON logging
        structlog.configure(
            processors=[
                *shared_processors,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

    # Quiet noisy third-party loggers such as pika, regardless of global level
    pika_debug_enabled = getattr(settings, "ENABLE_PIKA_DEBUG", False)
    noisy_loggers = (
        "pika",
        "pika.connection",
        "pika.channel",
        "pika.adapters",
        "pika.adapters.utils",
        "pika.adapters.utils.io_services_utils",
        "pika.adapters.utils.connection_workflow",
        "pika.adapters.blocking_connection",
    )
    target_level = logging.DEBUG if pika_debug_enabled else logging.CRITICAL
    disable_noisy_pika = not pika_debug_enabled
    for logger_name in noisy_loggers:
        logger_obj = logging.getLogger(logger_name)
        # Reset handlers so earlier basicConfig calls can't reattach stdout emitters.
        logger_obj.handlers.clear()
        logger_obj.setLevel(target_level)
        # Only bubble up to global handlers when explicitly debugging pika internals.
        logger_obj.propagate = pika_debug_enabled
        # Hard-disable when not debugging to silence verbose socket traces.
        logger_obj.disabled = disable_noisy_pika


# Initialize logging at import-time and export a shared logger
setup_logging()
logger = structlog.get_logger()
logger.info(
    "logging_initialized",
    environment=settings.ENVIRONMENT.value,
    log_level=settings.LOG_LEVEL,
    log_format=settings.LOG_FORMAT,
)
