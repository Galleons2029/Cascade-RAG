import os

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

from app.configs import mongo_config
from app.core.logger_utils import get_logger

logger = get_logger(__file__)


class _DisabledMongoCollection:
    def __init__(self, name: str):
        self._name = name

    # Methods used in codebase: insert_one, insert_many, find_one
    def _raise(self, method: str):
        raise RuntimeError(f"MongoDB is disabled (DISABLE_MONGO=true); attempted {method} on collection '{self._name}'.")

    def insert_one(self, *args, **kwargs):
        self._raise("insert_one")

    def insert_many(self, *args, **kwargs):
        self._raise("insert_many")

    def find_one(self, *args, **kwargs):
        self._raise("find_one")


class _DisabledMongoDatabase:
    def __init__(self, name: str):
        self._name = name

    def __getitem__(self, collection_name: str):
        return _DisabledMongoCollection(collection_name)


class _DisabledMongoClient:
    def __init__(self):
        pass

    def get_database(self, name: str | None = None):
        db_name = name or mongo_config.MONGO_DATABASE_NAME
        return _DisabledMongoDatabase(db_name)

    def close(self):
        logger.info("MongoDB disabled; close() no-op.")


class MongoDatabaseConnector:
    """用于连接MongoDB数据库的单例类。"""

    _instance: MongoClient | _DisabledMongoClient | None = None

    def __new__(cls, *args, **kwargs):
        # If disabled, always return a disabled client without attempting network calls
        env_disabled = os.getenv("DISABLE_MONGO", "").strip().lower() in {"1", "true", "yes", "on"}
        if mongo_config.DISABLE_MONGO or env_disabled:
            if cls._instance is None or not isinstance(cls._instance, _DisabledMongoClient):
                logger.warning("MongoDB usage is disabled via settings.DISABLE_MONGO=true. Using no-op client.")
                cls._instance = _DisabledMongoClient()
            return cls._instance

        if cls._instance is None or isinstance(cls._instance, _DisabledMongoClient):
            try:
                cls._instance = MongoClient(mongo_config.MONGO_DATABASE_HOST)
                # logger.info(
                #     f"成功连接到数据库，URI: {mongo_config.MONGO_DATABASE_HOST}"
                # )
            except ConnectionFailure:
                logger.error("无法连接到数据库。")
                raise

        return cls._instance


# Instantiate a module-level connection (real or disabled) for consumers doing `from ... import connection`
connection = MongoDatabaseConnector()
