import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

def make_llm() -> ChatOpenAI:
    load_dotenv()
    return ChatOpenAI(
        model="deepseek-chat",
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com",
        temperature=0,
    )
