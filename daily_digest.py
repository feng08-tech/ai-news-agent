import os
import requests
from bs4 import BeautifulSoup
from supabase import create_client
# 你原有的 AI 客户端导入也放在这里（比如 openai 或 requests）

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
LLM_API_KEY = os.environ["LLM_API_KEY"]
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ↓↓↓ 从 ai_editor_app.py 复制过来，但删掉里面所有 st. 开头的行 ↓↓↓
def fetch_all_news():
    ...   # 你原来的并发抓取逻辑

def generate_ai_summary(raw_text):
    ...   # 你原来的 AI 总结逻辑
# ↑↑↑ 复制到这里为止 ↑↑↑


if __name__ == "__main__":
    print("开始抓取...")
    raw = fetch_all_news()

    print("开始 AI 总结...")
    summary = generate_ai_summary(raw)

    print("写入 Supabase...")
    supabase.table("history").insert({
        "content": summary,
        # 如果有其他字段（比如 created_at、title），按你的表结构加
    }).execute()

    print("完成")
