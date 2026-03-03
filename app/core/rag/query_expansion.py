from app.configs import llm_config
from langchain_openai import ChatOpenAI

from app.core.rag.prompt_templates import QueryExpansionTemplate
from app.core import logger_utils

logger = logger_utils.get_logger(__name__)


class QueryExpansion:
    # opik_tracer = OpikTracer(tags=["QueryExpansion"])

    @staticmethod
    # @opik.track(name="QueryExpansion.generate_response")
    def generate_response(query: str, to_expand_to_n: int, stream: bool | None = False) -> list[str]:
        logger.debug("生成查询中。。。。")

        query_expansion_template = QueryExpansionTemplate()
        prompt = query_expansion_template.create_template(to_expand_to_n)
        model = ChatOpenAI(
            model=llm_config.FREE_LLM_MODEL,
            api_key=llm_config.SILICON_KEY,
            base_url=llm_config.SILICON_BASE_URL,
        )
        chain = prompt | model

        # if stream:
        #     for chunk in chain.stream({"question": query}):
        #         # print(chunk, end="|", flush=True)
        #         yield chunk.content
        #     logger.debug(f"stream: {stream}")
        # else:
        # chain = chain.with_config({"callbacks": [QueryExpansion.opik_tracer]})

        response = chain.invoke({"question": query})
        response = response.content

        queries = response.strip().split(query_expansion_template.separator)
        stripped_queries = [stripped_item for item in queries if (stripped_item := item.strip(" \\n"))]

        return stripped_queries
