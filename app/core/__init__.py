from . import logger_utils
from .logger_utils import get_logger

logger = get_logger(__file__)

# Lazy utilities only: importing app.core should not trigger heavy DB deps.
# Access `app.core.db` via explicit imports when needed.
__all__ = ["get_logger", "logger_utils"]
