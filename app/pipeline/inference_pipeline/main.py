"""
# TODO: 引入 LMCache 加速推理 https://github.com/LMCache/LMCache
"""


# 为了模拟使用多个Python模块，如'core'和'feature_pipeline'，
# 我们将'./src'目录添加到PYTHONPATH中。这不适用于生产环境，
# 仅用于开发和教学目的。
# ROOT_DIR = str(Path(__file__).parent)

# sys.path.append(ROOT_DIR)

from app.core import logger_utils
from reasoning import ReasoningPipeline

# settings.patch_localhost()

logger = logger_utils.get_logger(__name__)
# logger.info(
#     f"已将以下目录添加到PYTHONPATH以模拟多个模块：{ROOT_DIR}"
# )
# logger.warning(
#     "已修改设置以使用'localhost' URL。\
#     在部署或在Docker中运行时，请删除上面的'settings.patch_localhost()'调用。"
# )


if __name__ == "__main__":
    inference_endpoint = ReasoningPipeline(mock=False)

    query = """
            你好，我是张三。
            你能帮我写一段关于RAG的文章段落吗？
            我特别感兴趣的是如何设计一个RAG系统。
        """

    response = inference_endpoint.generate(query=query, enable_rag=True, sample_for_evaluation=False, doc_names=["zsk_test1"])

    logger.info("=" * 50)
    logger.info(f"问题：{query}")
    logger.info("=" * 50)
    logger.info(f"回答：{response['answer']}")
    logger.info("=" * 50)
