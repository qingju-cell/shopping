from dotenv import load_dotenv
import os
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser

load_dotenv()
llm = ChatOpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL"),
    model="deepseek-v4-flash",
    temperature=0.7
)

# 支持历史对话占位的模板
prompt = ChatPromptTemplate.from_messages([
    ("system", "你是智能对话助手，结合上下文连贯回答用户问题"),
    MessagesPlaceholder(variable_name="history"), # 历史对话占位
    ("human", "{input}") # 当前用户提问
])

chain = prompt | llm | StrOutputParser()

# 模拟多轮对话调用
history = []
# 第一轮
res1 = chain.invoke({"history": history, "input": "Python怎么入门？"})
history.append(("human", "Python怎么入门？"))
history.append(("ai", res1))
print("AI1：", res1)

# 第二轮（带上下文）
res2 = chain.invoke({"history": history, "input": "推荐入门学习路线"})
print("AI2：", res2)