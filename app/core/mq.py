from typing import Self, List
import logging
import time

import pika
from pika.adapters.blocking_connection import BlockingChannel

from app.configs import agent_config as settings
from app.core.logger_utils import get_logger

logger = get_logger(__file__)

# 禁用 Pika 的调试日志
logging.getLogger("pika").setLevel(logging.WARNING)


class RabbitMQConnection:
    """用于管理RabbitMQ连接的单例类。"""

    _instance = None

    def __new__(cls, *args, **kwargs) -> Self:
        if not cls._instance:
            cls._instance = super().__new__(cls, *args, **kwargs)

        return cls._instance

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        virtual_host: str = "/",
        fail_silently: bool = False,
        queue_names: List[str] = ["test_files"],
        **kwargs,
    ) -> None:
        self.host = host or settings.RABBITMQ_HOST
        self.port = port or settings.RABBITMQ_PORT
        self.username = username or settings.RABBITMQ_DEFAULT_USERNAME
        self.password = password or settings.RABBITMQ_DEFAULT_PASSWORD
        self.virtual_host = virtual_host
        self.fail_silently = fail_silently
        self.queue_names = queue_names  # 保存队列名称列表
        self._connection = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def connect(self, max_retries: int = 6, retry_delay: int = 5):
        attempt = 0
        while True:
            try:
                # 禁用 Pika 的所有子模块日志
                for logger_name in [
                    "pika",
                    "pika.connection",
                    "pika.channel",
                    "pika.adapters",
                    "pika.adapters.utils",
                    "pika.adapters.utils.io_services_utils",
                    "pika.adapters.blocking_connection",
                ]:
                    logging.getLogger(logger_name).setLevel(logging.ERROR)
                    logging.getLogger(logger_name).propagate = False

                credentials = pika.PlainCredentials(self.username, self.password)
                self._connection = pika.BlockingConnection(
                    pika.ConnectionParameters(
                        host=self.host,
                        port=self.port,
                        virtual_host=self.virtual_host,
                        credentials=credentials,
                    )
                )
                # 在连接成功后，检查并初始化队列
                with self._connection.channel() as channel:
                    for queue_name in self.queue_names:
                        self._initialize_queue(channel, queue_name)
                return

            except pika.exceptions.AMQPConnectionError as e:
                attempt += 1
                if attempt >= max_retries:
                    logger.exception("连接RabbitMQ失败：")
                    if not self.fail_silently:
                        raise e
                    return
                logger.warning(
                    "连接RabbitMQ失败，准备重试",
                    extra={"attempt": attempt, "max_retries": max_retries, "host": self.host, "port": self.port},
                )
                time.sleep(retry_delay)

    def is_connected(self) -> bool:
        return self._connection is not None and self._connection.is_open

    def get_channel(self):
        if self.is_connected():
            return self._connection.channel()

    def close(self):
        if self.is_connected():
            self._connection.close()
            self._connection = None
            print("已关闭RabbitMQ连接")

    def _initialize_queue(self, channel: BlockingChannel, queue_name: str):
        """检查并初始化队列。"""
        try:
            # 声明队列（如果队列不存在则创建）
            channel.queue_declare(queue=queue_name, durable=True)
            logger.info(f"队列 {queue_name} 已初始化。")
        except Exception as e:
            logger.exception(f"初始化队列 {queue_name} 时发生错误：{e}")


def publish_to_rabbitmq(queue_name: str, data: str):
    """向RabbitMQ队列发布数据。"""
    try:
        # 创建RabbitMQConnection实例
        rabbitmq_conn = RabbitMQConnection()

        # 建立连接
        with rabbitmq_conn:
            channel = rabbitmq_conn.get_channel()

            # 确保队列存在
            channel.queue_declare(queue=queue_name, durable=True)

            # 投递确认
            channel.confirm_delivery()

            # 向队列发送数据
            channel.basic_publish(
                exchange="",
                routing_key=queue_name,
                body=data,
                properties=pika.BasicProperties(
                    delivery_mode=2,  # 使消息持久化
                ),
            )
            logger.info(f"成功发送数据至队列：{data}")

    except pika.exceptions.UnroutableError:
        logger.warning("消息无法路由")
    except Exception:
        logger.exception("发布到RabbitMQ时发生错误。")


if __name__ == "__main__":
    publish_to_rabbitmq("test_queue", "Hello, World!")
