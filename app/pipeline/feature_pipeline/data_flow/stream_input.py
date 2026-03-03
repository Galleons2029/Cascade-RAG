import json
import logging
import time
from datetime import datetime
from typing import Generic, List, Optional, TypeVar

from bytewax.inputs import FixedPartitionedSource, StatefulSourcePartition
from app.configs import pipeline_config
from app.core import get_logger
from app.core.mq import RabbitMQConnection

logger = get_logger(__file__)

# 禁用 Pika 的调试日志
logging.getLogger("pika").setLevel(logging.WARNING)

DataT = TypeVar("DataT")
MessageT = TypeVar("MessageT")


class RabbitMQPartition(StatefulSourcePartition, Generic[DataT, MessageT]):
    """
    负责创建bytewax和rabbitmq之间的连接，促进数据从消息队列到bytewax流处理管道的传输。
    继承StatefulSourcePartition以实现快照功能，支持保存队列状态。
    """

    def __init__(self, queue_name: str, resume_state: MessageT | None = None) -> None:
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

        self._in_flight_msg_ids = resume_state or set()
        self.queue_name = queue_name
        self.connection = RabbitMQConnection()
        self.connection.connect()
        self.channel = self.connection.get_channel()
        logger.info("RabbitMQ 分区初始化", queue_name=queue_name, in_flight_messages=len(self._in_flight_msg_ids))

    def next_batch(self, sched: Optional[datetime] = None) -> List[DataT]:
        try:
            method_frame, header_frame, body = self.channel.basic_get(queue=self.queue_name, auto_ack=True)

        except Exception as e:
            logger.error(f"从队列获取消息时发生错误: {e}", queue_name=self.queue_name)
            time.sleep(10)

            self.connection.connect()
            self.channel = self.connection.get_channel()

            return []

        if method_frame:
            message_id = method_frame.delivery_tag
            self._in_flight_msg_ids.add(message_id)

            return [json.loads(body)]
        else:
            return []

    def snapshot(self) -> MessageT:
        logger.debug("创建运行中消息的快照", queue_name=self.queue_name, in_flight_count=len(self._in_flight_msg_ids))
        return self._in_flight_msg_ids

    def garbage_collect(self, state):
        closed_in_flight_msg_ids = state
        logger.debug("清理已确认的消息", queue_name=self.queue_name, messages_to_remove=len(closed_in_flight_msg_ids))
        for msg_id in closed_in_flight_msg_ids:
            self.channel.basic_ack(delivery_tag=msg_id)
            self._in_flight_msg_ids.remove(msg_id)
            logger.debug("消息已确认并从运行中移除", queue_name=self.queue_name, message_id=msg_id)

    def close(self):
        logger.info("关闭RabbitMQ通道", queue_name=self.queue_name, in_flight_messages=len(self._in_flight_msg_ids))
        self.channel.close()


class RabbitMQSource(FixedPartitionedSource):
    def list_parts(self) -> List[str]:
        return ["single partition"]

    def build_part(self, now: datetime, for_part: str, resume_state: MessageT | None = None) -> StatefulSourcePartition[DataT, MessageT]:
        logger.info("构建RabbitMQ分区", partition=for_part, has_resume_state=resume_state is not None)
        return RabbitMQPartition(queue_name=pipeline_config.RABBITMQ_QUEUE_NAME)
