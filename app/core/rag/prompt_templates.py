from abc import ABC, abstractmethod

from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel


class BasePromptTemplate(ABC, BaseModel):
    @abstractmethod
    def create_template(self, *args) -> PromptTemplate:
        pass


class QueryExpansionTemplate(BasePromptTemplate):
    prompt: str = """你是一个AI语言模型助手。你的任务是生成{to_expand_to_n}个
    不同版本的用户问题，以便从向量数据库中检索相关文档。通过生成用户问题的多个视角，
    你的目标是帮助用户克服基于距离的相似性搜索的一些限制。
    请用'{separator}'分隔这些替代问题。
    原始问题：{question}"""

    @property
    def separator(self) -> str:
        return "#next-question#"

    def create_template(self, to_expand_to_n: int) -> PromptTemplate:
        return PromptTemplate(
            template=self.prompt,
            input_variables=["question"],
            partial_variables={
                "separator": self.separator,
                "to_expand_to_n": to_expand_to_n,
            },
        )


class SelfQueryTemplate(BasePromptTemplate):
    prompt: str = """你是一个AI语言模型助手。你的任务是从用户问题中提取信息。
    需要提取的信息是用户名或用户ID。
    你的回答应该只包含提取出的用户名（例如：张三）或ID（例如：1345256），不要包含其他内容。
    如果用户问题中没有包含任何用户名或ID，你应该返回以下标记：none。
    
    例如：
    问题1：
    我的名字是张三，我想写一篇关于...
    回答1：
    张三
    
    问题2：
    我想写一篇关于...
    回答2：
    none
    
    问题3：
    我的用户ID是1345256，我想写一篇关于...
    回答3：
    1345256
    
    用户问题：{question}"""

    def create_template(self) -> PromptTemplate:
        return PromptTemplate(template=self.prompt, input_variables=["question"])


class RerankingTemplate(BasePromptTemplate):
    prompt: str = """你是一个AI语言模型助手。你的任务是根据相关性对与查询相关的段落进行重新排序。
    最相关的段落应该放在开头。
    你最多只能选择{keep_top_k}个段落。
    提供的和重新排序的文档用'{separator}'分隔。
    
    以下是与此查询相关的段落：{question}。
    
    段落：
    {passages}
    """

    def create_template(self, keep_top_k: int) -> PromptTemplate:
        return PromptTemplate(
            template=self.prompt,
            input_variables=["question", "passages"],
            partial_variables={"keep_top_k": keep_top_k, "separator": self.separator},
        )

    @property
    def separator(self) -> str:
        return "\n#next-document#\n"
