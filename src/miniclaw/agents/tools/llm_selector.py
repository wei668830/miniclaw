class LLMSelector:
    """通过分析任务描述来选择最合适的语言模型（LLM）"""
    def __init__(self, llm_selector):
        self.llm_selector = llm_selector

    def select_llm(self, task_description):
        return self.llm_selector(task_description)