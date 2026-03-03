from transformers import AutoTokenizer


def compute_num_tokens(text: str) -> int:
    tokenizer = AutoTokenizer.from_pretrained("/data/cyx_model_weights/Qwen3-8B", cache_dir="./config_cache", local_files_only=True)

    return len(tokenizer.encode(text, add_special_tokens=False))


def truncate_text_to_max_tokens(text: str, max_tokens: int) -> tuple[str, int]:
    """将文本截断至不超过最大token数，同时尽量保持完整句子。

    参数：
        text: 需要截断的文本
        max_tokens: 允许的最大token数

    返回：
        截断后的文本（在最大token数范围内）和截断后文本的token数。
    """

    current_tokens = compute_num_tokens(text)

    if current_tokens <= max_tokens:
        return text, current_tokens

    tokenizer = AutoTokenizer.from_pretrained("/data/cyx_model_weights/Qwen3-8B", cache_dir="./config_cache", local_files_only=True)
    tokens = tokenizer.encode(text, add_special_tokens=False)

    # 取前max_tokens个token并解码
    truncated_tokens = tokens[:max_tokens]
    truncated_text = tokenizer.decode(truncated_tokens)

    # 尝试在最后一个完整句子处结束
    last_period = truncated_text.rfind(".")
    if last_period > 0:
        truncated_text = truncated_text[: last_period + 1]

    truncated_tokens = compute_num_tokens(truncated_text)

    return truncated_text, truncated_tokens
