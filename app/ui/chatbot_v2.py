# -*- coding: utf-8 -*-
# @Time    : 2025/06/18 3:31 AM
# @Author  : Galleons
# @File    : chatbot_v2.py

"""
第二版推理可视化 demo 展示界面，整合文件上传功能
"""

import gradio as gr
from gradio import ChatMessage

import time
import os
import uuid

from app.core.mq import publish_to_rabbitmq
from app.configs import agent_config as app_settings
from app.configs import llm_config, qdrant_config
from app.core import logger_utils
from app.pipeline.feature_pipeline.models.raw import DocumentRawModel
from app.pipeline.inference_pipeline.reasoning import ReasoningPipeline
from qdrant_client import QdrantClient, models
from app.pipeline.inference_pipeline.prompt_templates import InferenceTemplate
from app.core.rag.retriever import VectorRetriever
from app.core.rag.prompt_templates import QueryExpansionTemplate
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from app.pipeline.inference_pipeline.utils import compute_num_tokens, truncate_text_to_max_tokens
from pathlib import Path
from markitdown import MarkItDown


ROOT_DIR = str(Path(__file__).parent.parent.parent.parent)
UPLOAD_FOLDER = os.path.join(ROOT_DIR, "uploads")


sleep_time = 0.5
model = ChatOpenAI(
    model=llm_config.LLM_MODEL or llm_config.FREE_LLM_MODEL,
    api_key=llm_config.API_KEY or llm_config.SILICON_KEY,
    base_url=llm_config.SILICON_BASE_URL,
    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
)
query_expansion_template = QueryExpansionTemplate()
prompt = query_expansion_template.create_template(3)
chain = prompt | model
# 使用配置中的 Qdrant 连接信息，兼容 Docker 和本地部署
client = QdrantClient(host=qdrant_config.QDRANT_DATABASE_HOST, port=qdrant_config.QDRANT_DATABASE_PORT)
doc_bases = [collection.name for collection in client.get_collections().collections]

logger = logger_utils.get_logger(__name__)


def process_uploaded_file(files: list, dir_files: list, collection_choice: str = "default"):
    """
    处理上传的文件，支持单个文件上传和目录上传两种方式。

    参数:
        files (list): 单个文件上传列表
        dir_files (list): 目录上传文件列表
        collection_choice (str): 上传的知识库名

    返回:
        tuple: (状态消息, 文件名, 文件名)
    """
    try:
        # 过滤掉None值和空列表
        files = [f for f in files if f] if files else []
        dir_files = [f for f in dir_files if f] if dir_files else []

        # 合并所有文件
        files_list = files + dir_files

        if not files_list:
            return "未选择任何文件", "", ""

        doc_count = len(files_list)
        logger.info(f"共收到{doc_count}个文件，文件名：{files_list}")

        md = MarkItDown(enable_plugins=False)

        processed_count = 0
        for file in files_list:
            try:
                result = md.convert(file)
                data = DocumentRawModel(
                    knowledge_id=collection_choice,
                    doc_id="222",
                    path=file,
                    filename=file,
                    content=result.text_content,
                    type="documents",
                    entry_id=str(uuid.uuid4()),
                ).model_dump_json()
                publish_to_rabbitmq(queue_name="test_files", data=data)
                logger.info(f"成功处理并发送文件：{file}")
                processed_count += 1
            except Exception as e:
                logger.error(f"处理文件 {file} 时出错: {str(e)}")
                continue

        if processed_count == 0:
            return "文件处理失败，请检查文件格式是否正确", "", ""

        return f"成功处理 {processed_count}/{doc_count} 个文件", file_name, file_name

    except Exception as e:
        logger.error(f"处理上传文件时发生错误: {str(e)}")
        return f"处理文件时发生错误: {str(e)}", "", ""


def process_query(query: str, show_reasoning: bool = False, use_background: bool = True, selected_collections: list = None):
    inference_endpoint = ReasoningPipeline(mock=False)

    response = inference_endpoint.generate(
        query=query, enable_rag=True, sample_for_evaluation=True, doc_names=selected_collections if selected_collections else None
    )

    return response["answer"]


def add_new_collection(new_collection: str):
    """
    添加新的知识库集合

    参数:
        new_collection (str): 新知识库名称
        current_collections (list): 当前知识库列表

    返回:
        tuple: (更新后的知识库列表, 新知识库名称)
    """
    global doc_bases
    if not new_collection or new_collection.strip() == "":
        return doc_bases

    if new_collection in doc_bases:
        return doc_bases

    client.create_collection(
        collection_name=new_collection,
        vectors_config=models.VectorParams(size=llm_config.EMBEDDING_SIZE, distance=models.Distance.COSINE),
        quantization_config=models.ScalarQuantization(
            scalar=models.ScalarQuantizationConfig(
                type=models.ScalarType.INT8,
                quantile=0.99,
                always_ram=True,
            ),
        ),
    )

    logger.debug(f"{doc_bases}<UNK>{new_collection}<UNK>]")
    doc_bases.append(new_collection)

    return doc_bases


def format_prompt(
    system_prompt,
    prompt_template: PromptTemplate,
    prompt_template_variables: dict,
) -> tuple[list[dict[str, str]], int]:
    prompt = prompt_template.format(**prompt_template_variables)

    num_system_prompt_tokens = compute_num_tokens(system_prompt)
    prompt, prompt_num_tokens = truncate_text_to_max_tokens(prompt, max_tokens=app_settings.MAX_TOKENS - num_system_prompt_tokens)
    total_input_tokens = num_system_prompt_tokens + prompt_num_tokens

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]

    return messages, total_input_tokens


def kunlunrag_thinking_chat(prompt: str, history: list):
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

    queries = full_output.strip().split(query_expansion_template.separator)
    stripped_queries = [stripped_item for item in queries if (stripped_item := item.strip(" \\n"))]
    logger.debug(stripped_queries)
    hits = retriever.retrieve_top_k(k=3, collections=["zsk_demo"], generated_queries=stripped_queries)

    history.append(ChatMessage(content="", metadata={"title": "查询到相关文档", "id": 1, "status": "pending"}))
    history[-1].metadata["duration"] = time.time() - start_time
    accumulated_thoughts = ""
    for hit in hits:
        time.sleep(sleep_time)
        accumulated_thoughts += f"- {hit}\n\n"
        history[-1].content = accumulated_thoughts.strip()
        yield history

    history.append(ChatMessage(content="", metadata={"title": "对文档进行重排", "id": 2, "status": "pending"}))
    context = retriever.rerank(hits=hits, keep_top_k=3)
    prompt_template_variables["context"] = context
    messages, input_num_tokens = format_prompt(system_prompt, prompt_template, prompt_template_variables)
    yield history

    history[-1].metadata["status"] = "done"
    history[-1].metadata["duration"] = time.time() - start_time
    yield history

    from openai import OpenAI

    client = OpenAI(api_key="sk-jkcrphotzrjcdttdpbdzczufqryzmeogzbvwbtpabuitgnzx", base_url="https://api.siliconflow.cn/v1")
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

    for chunk in answer:
        content = chunk.choices[0].delta.content
        reasoning_content = chunk.choices[0].delta.reasoning_content

        if content and not thinking_complete:
            # Complete thought and start response
            content += content or ""
            history[-1] = ChatMessage(role="assistant", content=thought_buffer, metadata={"title": "⏳Thinking: *正在思考"})

            # Add response message
            history.append(ChatMessage(role="assistant", content=content))
            response_buffer += content
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


with gr.Blocks(title="推理问答知识库") as demo:
    gr.Markdown("""
    # 推理问答系统
        支持多文件上传，大文档上传
        支持多文件夹上传，大文件夹上传
    """)

    with gr.Row():
        with gr.Column():
            files_input = gr.File(label="上传文档", file_types=[".txt", ".docx", ".pdf", ".csv", ".json"], type="filepath", file_count="multiple")
            dir_input = gr.File(label="上传文件夹", file_types=[".txt", ".docx", ".pdf", ".csv", ".json"], type="filepath", file_count="directory")

            with gr.Row():
                collection_choice = gr.Dropdown(
                    label="选择加载到的知识库", choices=doc_bases, multiselect=False, value=doc_bases[0] if doc_bases else None, interactive=True
                )
                new_collection_input = gr.Textbox(label="新建知识库", placeholder="输入新知识库名称", interactive=True)
                add_collection_btn = gr.Button("添加")

            file_name = gr.Textbox(label="文件名", visible=False)

            upload_button = gr.Button("加载文档到知识库")

            upload_output = gr.Textbox(label="上传状态", interactive=False)

            collections_dropdown = gr.Dropdown(label="选择知识库集合", choices=doc_bases, multiselect=True, value=None, interactive=True)

        with gr.Column():
            chat = gr.ChatInterface(
                kunlunrag_thinking_chat,
                title="Thinking LLM Chat Interface 🤔",
                type="messages",
            )

    # 处理文件上传
    def on_file_select(file):
        """处理文件选择"""
        if file is None:
            return "未选择文件", ""

        print(f"已选择文件: {type(file)}")
        if isinstance(file, str):  # filepath模式返回字符串路径
            logger.info(f"文件名: {os.path.basename(file)}, 路径:{os.path.splitext(file)[1]}")

            return os.path.basename(file), os.path.splitext(file)[1]
        elif hasattr(file, "name"):
            logger.info(f"文件名: {file.name}, 路径:{os.path.splitext(file.name)[1]}")

            return file.name, os.path.splitext(file.name)[1]
        else:
            return "已选择文件（未知格式）", ".txt"

    files_input.change(fn=on_file_select, inputs=[files_input], outputs=[file_name, upload_output])

    # 处理上传文件按钮点击
    upload_button.click(fn=process_uploaded_file, inputs=[files_input, dir_input, collection_choice], outputs=[upload_output, gr.State(), gr.State()])

    add_collection_btn.click(fn=add_new_collection, inputs=new_collection_input, outputs=[collection_choice, collections_dropdown])


# 启动应用
if __name__ == "__main__":
    # 启动应用
    demo.launch(server_name="0.0.0.0", share=True)
    # demo.launch(server_name="175.6.21.222", share=True)
