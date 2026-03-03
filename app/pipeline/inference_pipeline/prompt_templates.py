from app.core.rag.prompt_templates import BasePromptTemplate
from langchain_core.prompts import PromptTemplate


class InferenceTemplate(BasePromptTemplate):
    simple_system_prompt: str = """
            你是一个AI语言模型助手。你的任务是根据用户的指令生成一个连贯且简洁的回复，使用相似的写作风格和语气。
        """
    simple_prompt_template: str = """
            ### Instruction:
            {question}
            """

    rag_system_prompt: str = """ 你是一个深度思考助手。你的任务是根据用户的指令和特定上下文思考并回答，你有多次思考的机会，直到你认为你已经回答了用户的问题。

            以下是解决这个任务需要遵循的步骤：
            
            步骤1：你需要分析用户的指令。
            步骤2：你需要分析提供的上下文，以及其中的信息如何与用户指令相关。
            步骤3：生成内容时要注意，基于查询尽可能保持连贯和简洁。你将使用从用户指令和上下文中推断出的用户写作风格和语气。
            首先尝试基于上下文回答。如果上下文不相关，则用“我无法回答你的问题，因为我没有足够的上下文。”拒绝回答，并给出可能的解决方案。"
            """  # noqa: E501

    rag_prompt_template: str = """
        ### Instruction:
        {question}
        
        ### Context:
        {context}
        """

    def create_template(self, enable_rag: bool = True) -> tuple[str, PromptTemplate]:
        if enable_rag is True:
            return self.rag_system_prompt, PromptTemplate(
                template=self.rag_prompt_template,
                input_variables=["question", "context"],
            )

        return self.simple_system_prompt, PromptTemplate(template=self.simple_prompt_template, input_variables=["question"])
