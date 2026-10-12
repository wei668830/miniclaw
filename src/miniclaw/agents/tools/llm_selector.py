"""根据任务描述选择合适的大模型的选择器。"""


class LLMSelector:
    """通过分析任务描述来选择最合适的语言模型（LLM）"""
    def __init__(self, llm_selector):
        """初始化选择器。

        :param llm_selector: 接收任务描述并返回模型名的可调用对象
        """
        self.llm_selector = llm_selector

    def select_llm(self, task_description):
        """根据任务描述选择模型。

        :param task_description: 任务描述文本
        :return: 选出的模型标识
        """
        return self.llm_selector(task_description)