from langchain_openai import ChatOpenAI
from app.configs import llm_config
from langchain.chat_models import init_chat_model

client = ChatOpenAI(
    model=llm_config.LLM_MODEL,
    temperature=llm_config.DEFAULT_LLM_TEMPERATURE,
    api_key=llm_config.API_KEY,
    max_tokens=llm_config.MAX_TOKENS,
    base_url=llm_config.SILICON_BASE_URL,
)

model = init_chat_model(
    model=llm_config.LLM_MODEL_PRO,
    base_url=llm_config.SILICON_BASE_URL,
    api_key=llm_config.SILICON_KEY,
    model_provider="openai",
    temperature=0,
)

if __name__ == "__main__":
    response = model.invoke("你好！")
    print(response)
