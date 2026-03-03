# -*- coding: utf-8 -*-
# @Time    : 2025/6/5 14:35
# @Author  : Galleons
# @File    : main.py

"""
管道调度脚本
"""

import bytewax.operators as op
from bytewax.dataflow import Dataflow
from app.core.db.qdrant import QdrantDatabaseConnector
from data_flow.stream_input import RabbitMQSource
from data_flow.stream_output import QdrantOutput
from data_logic.dispatchers import (
    ChunkingDispatcher,
    CleaningDispatcher,
    EmbeddingDispatcher,
    RawDispatcher,
)

connection = QdrantDatabaseConnector()

flow = Dataflow("流式摄取管道")
stream = op.input("输入", flow, RabbitMQSource())
stream = op.map("原始调度", stream, RawDispatcher.handle_mq_message)
stream = op.map("清理调度", stream, CleaningDispatcher.dispatch_cleaner)
op.output(
    "清理后的数据导入到qdrant",
    stream,
    QdrantOutput(connection=connection, sink_type="clean"),
)
stream = op.flat_map("分块调度", stream, ChunkingDispatcher.dispatch_chunker)
stream = op.map("嵌入块调度", stream, EmbeddingDispatcher.dispatch_embedder)
op.output(
    "嵌入数据导入到qdrant",
    stream,
    QdrantOutput(connection=connection, sink_type="vector"),
)
