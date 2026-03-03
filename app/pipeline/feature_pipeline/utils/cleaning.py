import re

from unstructured.cleaners.core import (
    clean,
    replace_unicode_quotes,
)


def unbold_text(text):
    # 粗体数字到普通数字的映射
    bold_numbers = {
        "𝟬": "0",
        "𝟭": "1",
        "𝟮": "2",
        "𝟯": "3",
        "𝟰": "4",
        "𝟱": "5",
        "𝟲": "6",
        "𝟳": "7",
        "𝟴": "8",
        "𝟵": "9",
    }

    # 转换粗体字符的函数（字母和数字）
    def convert_bold_char(match):
        char = match.group(0)
        # 转换粗体数字
        if char in bold_numbers:
            return bold_numbers[char]
        # 转换粗体大写字母
        elif "\U0001d5d4" <= char <= "\U0001d5ed":
            return chr(ord(char) - 0x1D5D4 + ord("A"))
        # 转换粗体小写字母
        elif "\U0001d5ee" <= char <= "\U0001d607":
            return chr(ord(char) - 0x1D5EE + ord("a"))
        else:
            return char  # 如果不是粗体数字或字母，则保持原样

    # 匹配粗体字符的正则表达式（数字、大写和小写字母）
    bold_pattern = re.compile(r"[\U0001D5D4-\U0001D5ED\U0001D5EE-\U0001D607\U0001D7CE-\U0001D7FF]")
    text = bold_pattern.sub(convert_bold_char, text)

    return text


def unitalic_text(text):
    # 转换斜体字符的函数（字母）
    def convert_italic_char(match):
        char = match.group(0)
        # 斜体字符的Unicode范围
        if "\U0001d608" <= char <= "\U0001d621":  # 斜体大写字母A-Z
            return chr(ord(char) - 0x1D608 + ord("A"))
        elif "\U0001d622" <= char <= "\U0001d63b":  # 斜体小写字母a-z
            return chr(ord(char) - 0x1D622 + ord("a"))
        else:
            return char  # 如果不是斜体字母，则保持原样

    # 匹配斜体字符的正则表达式（大写和小写字母）
    italic_pattern = re.compile(r"[\U0001D608-\U0001D621\U0001D622-\U0001D63B]")
    text = italic_pattern.sub(convert_italic_char, text)

    return text


def remove_emojis_and_symbols(text):
    # 扩展模式以包含特定符号，如下箭头(↓, U+2193)或右箭头(↳, U+21B3)
    emoji_and_symbol_pattern = re.compile(
        "["
        "\U0001f600-\U0001f64f"  # 表情符号
        "\U0001f300-\U0001f5ff"  # 符号和象形文字
        "\U0001f680-\U0001f6ff"  # 交通和地图符号
        "\U0001f1e0-\U0001f1ff"  # 旗帜(iOS)
        "\U00002193"  # 下箭头
        "\U000021b3"  # 带右尖的下箭头
        "\U00002192"  # 右箭头
        "]+",
        flags=re.UNICODE,
    )

    return emoji_and_symbol_pattern.sub(r" ", text)


def replace_urls_with_placeholder(text, placeholder="[URL]"):
    # 匹配URL的正则表达式模式
    url_pattern = r"https?://\S+|www\.\S+"

    return re.sub(url_pattern, placeholder, text)


def remove_non_ascii(text: str) -> str:
    text = text.encode("ascii", "ignore").decode("ascii")
    return text


def clean_text(text_content: str | None, preserve_urls: bool = False) -> str:
    if text_content is None:
        return ""

    cleaned_text = unbold_text(text_content)
    cleaned_text = unitalic_text(cleaned_text)
    cleaned_text = remove_emojis_and_symbols(cleaned_text)
    cleaned_text = clean(cleaned_text)
    cleaned_text = replace_unicode_quotes(cleaned_text)
    # cleaned_text = clean_non_ascii_chars(cleaned_text)
    if not preserve_urls:
        cleaned_text = replace_urls_with_placeholder(cleaned_text)

    return cleaned_text
