from langchain_openai import ChatOpenAI

from app.configs import llm_config

import app.core.logger_utils as logger_utils
from app.core import lib
from app.core.db.documents import UserDocument
from app.core.rag.prompt_templates import SelfQueryTemplate

logger = logger_utils.get_logger(__name__)


class SelfQuery:
    # opik_tracer = OpikTracer(tags=["SelfQuery"])

    @staticmethod
    # @opik.track(name="SelQuery.generate_response")
    def generate_response(query: str) -> str | None:
        prompt = SelfQueryTemplate().create_template()
        model = ChatOpenAI(
            model=llm_config.LLM_MODEL or llm_config.FREE_LLM_MODEL,
            api_key=llm_config.SILICON_KEY,
            base_url=llm_config.SILICON_BASE_URL,
        )
        chain = prompt | model
        # chain = chain.with_config({"callbacks": [SelfQuery.opik_tracer]})

        response = chain.invoke({"question": query})
        response = response.content
        user_full_name = response.strip("\n ")

        if user_full_name == "none":
            return None

        logger.info(
            "Successfully extracted the user full name from the query.",
            user_full_name=user_full_name,
        )
        first_name, last_name = lib.split_user_full_name(user_full_name)
        logger.info(
            "Successfully extracted the user first and last name from the query.",
            first_name=first_name,
            last_name=last_name,
        )
        user_id = UserDocument.get_or_create(first_name=first_name, last_name=last_name)

        return user_id
