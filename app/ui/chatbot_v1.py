# -*- coding: utf-8 -*-
# @Time    : 2025/06/17 12:31 AM
# @Author  : Galleons
# @File    : chatbot_v1.py

"""
第一版推理思维链可视化 demo 界面
"""

import gradio as gr
from gradio import ChatMessage
import time
from app.pipeline.inference_pipeline.prompt_templates import InferenceTemplate
from app.core.rag.retriever import VectorRetriever
from app.core.rag.prompt_templates import QueryExpansionTemplate
from langchain_openai import ChatOpenAI
from app.configs import llm_config
from langchain_core.prompts import PromptTemplate

from app.core import logger_utils

logger = logger_utils.get_logger(__name__)

sleep_time = 0.3
model = ChatOpenAI(
    model=llm_config.LLM_MODEL or llm_config.FREE_LLM_MODEL,
    api_key=llm_config.SILICON_KEY,
    base_url=llm_config.SILICON_BASE_URL,
    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
)
query_expansion_template = QueryExpansionTemplate()
prompt = query_expansion_template.create_template(3)
chain = prompt | model


def format_prompt(
    system_prompt,
    prompt_template: PromptTemplate,
    prompt_template_variables: dict,
) -> tuple[list[dict[str, str]], int]:
    prompt = prompt_template.format(**prompt_template_variables)

    # num_system_prompt_tokens = compute_num_tokens(system_prompt)
    # prompt, prompt_num_tokens = truncate_text_to_max_tokens(
    #     prompt, max_tokens=settings.MAX_INPUT_TOKENS - num_system_prompt_tokens
    # )
    # total_input_tokens = num_system_prompt_tokens + prompt_num_tokens

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]

    # return messages, total_input_tokens
    return messages


def user_message(msg, chat_history):
    """
    将用户消息添加到聊天历史，并清空输入框
    """
    if not isinstance(chat_history, list):
        chat_history = []
    chat_history = chat_history.copy()
    # chat_history.append(ChatMessage(role="user", content=msg))
    return "", chat_history


def simulate_thinking_chat(prompt: str, history: list):
    history.append(ChatMessage(role="user", content=prompt))
    yield history

    start_time = time.time()
    history.append(ChatMessage(content="", metadata={"title": "_生成多重查询_", "id": 0, "status": "pending"}))
    yield history
    prompt_template_builder = InferenceTemplate()
    system_prompt, prompt_template = prompt_template_builder.create_template(enable_rag=True)
    prompt_template_variables = {"question": prompt}

    retriever = VectorRetriever(query=prompt)

    full_output = ""
    for chunk in chain.stream({"question": prompt}):
        # print(chunk, end="|", flush=True)
        full_output += chunk.content
        history[-1].content = full_output.strip()
        yield history

    history[-1].metadata["status"] = "done"
    history[-1].metadata["duration"] = time.time() - start_time

    queries = full_output.strip().split(query_expansion_template.separator)
    stripped_queries = [stripped_item for item in queries if (stripped_item := item.strip(" \\n"))]
    logger.debug(stripped_queries)
    hits = retriever.retrieve_top_k(k=3, collections=["zsk_test1"], generated_queries=stripped_queries)

    history.append(ChatMessage(content="", metadata={"title": "查询到相关文档", "id": 1, "status": "pending"}))
    start_time = time.time()
    accumulated_thoughts = ""
    for hit in hits:
        time.sleep(sleep_time)
        accumulated_thoughts += f"- {hit}\n\n"
        history[-1].content = accumulated_thoughts.strip()
        yield history

    history[-1].metadata["status"] = "done"
    history[-1].metadata["duration"] = time.time() - start_time

    history.append(ChatMessage(content="", metadata={"title": "对文档进行重排", "id": 2, "status": "pending"}))
    start_time = time.time()
    context = retriever.rerank(hits=hits, keep_top_k=3)
    prompt_template_variables["context"] = context
    messages = format_prompt(system_prompt, prompt_template, prompt_template_variables)
    yield history

    history[-1].metadata["status"] = "done"
    history[-1].metadata["duration"] = time.time() - start_time
    yield history

    from openai import OpenAI

    client = OpenAI(api_key=settings.SILICON_KEY, base_url="https://api.siliconflow.cn/v1")
    answer = client.chat.completions.create(
        # model='Pro/deepseek-ai/DeepSeek-R1',
        model="deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
        messages=messages,
        stream=True,
        max_tokens=1000,
    )

    thought_buffer = ""
    response_buffer = ""
    thinking_complete = False

    history.append(ChatMessage(role="assistant", content="", metadata={"title": "⏳Thinking: *正在思考"}))
    start_time = time.time()

    for chunk in answer:
        content = chunk.choices[0].delta.content
        reasoning_content = chunk.choices[0].delta.reasoning_content

        if content and not thinking_complete:
            # Complete thought and start response
            content += content or ""
            history[-1] = ChatMessage(role="assistant", content=thought_buffer, metadata={"title": "⏳Thinking: *正在思考"})

            # Add response message
            history.append(ChatMessage(role="assistant", content=content))
            thinking_complete = True

        elif thinking_complete:
            # Continue streaming response
            response_buffer += content or ""
            history[-1] = ChatMessage(
                role="assistant",
                content=response_buffer,
                # metadata = {"title": "最终回答！"}
            )

        else:
            # Continue streaming thoughts
            thought_buffer += reasoning_content or ""
            history[-1] = ChatMessage(role="assistant", content=thought_buffer, metadata={"title": "⏳Thinking: *推理思维链"})

        yield history

    history[-1].metadata["status"] = "done"
    history[-1].metadata["duration"] = time.time() - start_time


with gr.Blocks() as demo:
    gr.Markdown("# 流式推理智能体 💭")

    chatbot = gr.Chatbot(
        type="messages",
        label="Gemini2.0 'Thinking' Chatbot",
        render_markdown=True,
    )

    input_box = gr.Textbox(lines=1, label="Chat Message", placeholder="Type your message here and press Enter...")

    # Set up event handlers
    msg_store = gr.State("")  # Store for preserving user message

    input_box.submit(
        lambda msg: (msg, msg, ""),  # Store message and clear input
        inputs=[input_box],
        outputs=[msg_store, input_box, input_box],
        queue=False,
    ).then(
        user_message,  # Add user message to chat
        inputs=[msg_store, chatbot],
        outputs=[input_box, chatbot],
        queue=False,
    ).then(
        simulate_thinking_chat,  # Generate and stream response
        inputs=[msg_store, chatbot],
        outputs=chatbot,
    )

demo.launch()
