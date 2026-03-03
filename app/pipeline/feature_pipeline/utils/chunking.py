from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.configs import llm_config
from app.core.agent.call_llm import client
from app.core.prompts import CONTEXTUAL_RETRIEVAL_PROMPT


def chunk_text(text: str) -> list[str]:
    """Split raw text with the recursive splitter, then attach generated context."""
    if not text or not text.strip():
        return []

    separators = [
        "\n\n",
        "\n",
        " ",
        ".",
        ",",
        "\u200b",  # zero-width space
        "\uff0c",  # Chinese fullwidth comma
        "\u3001",  # ideographic comma
        "\uff0e",  # Chinese fullwidth period
        "\u3002",  # ideographic period
        "",
    ]

    # Recommended separators for languages without explicit word boundaries.
    recursive_splitter = RecursiveCharacterTextSplitter(
        separators=separators,
        chunk_size=500,
        chunk_overlap=0,
        length_function=len,
        is_separator_regex=False,
    )

    enriched_chunks: list[str] = []
    for chunk in recursive_splitter.split_text(text):
        if not chunk.strip():
            continue
        context = _generate_context(text, chunk, separators)
        enriched_chunks.append(f"{chunk}\n\n{context}".strip())

    return enriched_chunks


def situate_context(doc: str, chunk: str) -> str:
    """Use the centralized contextual retrieval prompt to enrich a chunk."""
    prompt = CONTEXTUAL_RETRIEVAL_PROMPT.format(
        full_article=doc,
        original_chunk=chunk,
    )
    response = client.invoke(prompt)
    return getattr(response, "content", str(response))


def _generate_context(doc: str, chunk: str, separators: list[str]) -> str:
    """Ensure doc fits prompt limits by slicing and merging context when needed."""
    max_tokens = llm_config.MAX_TOKENS
    if max_tokens and len(doc) > max_tokens:
        available = max_tokens - 2000  # 留出空间给提示和响应
        available = max(available, 10000)
        doc_splitter = RecursiveCharacterTextSplitter(
            separators=separators,
            chunk_size=available,
            chunk_overlap=500,
            length_function=len,
            is_separator_regex=False,
        )
        compressed_segments = []
        for section in doc_splitter.split_text(doc):
            if not section.strip():
                continue
            compressed_segments.append(situate_context(section, chunk))
        total_context = " ".join(compressed_segments).strip()
        return client.invoke(f"将下面几段话压缩成简短一段话：{total_context}").content

    return situate_context(doc, chunk)


def main():
    st = """
    为大型语言模型（LLMs）添加上下文能显著提升各类应用场景的性能表现。尽管检索增强生成（RAG）系统已得到广泛研究，但核心问题仍未解决：错误究竟源于LLM未能有效利用检索到的上下文，还是上下文本身不足以回答查询？
为探究这一问题，我们提出了充分上下文的新概念，并开发了相应的分类方法以判定实例是否包含足够信息来回答问题。基于这一标准，我们对多个模型和数据集展开分析。通过按上下文充分性对错误进行分层，研究发现：基线性能更高的大模型（如Gemini 1.5 Pro、GPT-4o、Claude 3.5）在上下文充分时表现优异，但当上下文不足时却倾向于输出错误答案而非主动弃答；而基线性能较弱的小模型（如Mistral 3、Gemma 2）即使面对充分上下文也经常产生幻觉或过度弃答。我们进一步识别出"部分有效上下文"场景——虽然上下文不能完全解答问题，但能提升模型准确率（若无上下文模型必定出错）。
基于这些发现，我们探索了减少RAG系统幻觉的方法，包括一种新型的选择性生成技术：利用充分上下文信息引导模型主动弃答。实验表明，该方法能将Gemini、GPT和Gemma系列模型在响应时的正确答案比例提升2%-10%。  
    """  # noqa: E501

    CHUNKS = chunk_text(st)
    print(CHUNKS)
    # print(CONTEXTUAL_RETRIEVAL_PROMPT)


if __name__ == "__main__":
    main()
