import streamlit as st
import feedparser
import re
import requests
import os
from openai import OpenAI
from dotenv import load_dotenv

# 加载本地环境变量（用于本地运行）
load_dotenv()

# ================= 核心修复：云端密钥读取逻辑 =================
# 优先从 Streamlit Cloud 的 Secrets 中读取，并注入到环境变量
try:
    if "ANTHROPIC_API_KEY" in st.secrets:
        os.environ["ANTHROPIC_API_KEY"] = st.secrets["ANTHROPIC_API_KEY"]
    if "ANTHROPIC_BASE_URL" in st.secrets:
        os.environ["ANTHROPIC_BASE_URL"] = st.secrets["ANTHROPIC_BASE_URL"]
except Exception:
    pass
# ============================================================

st.set_page_config(page_title="AI 智能新闻主编", page_icon="📰", layout="centered")
st.title("📰 AI 智能新闻主编")
st.write("一键抓取三大科技媒体最新资讯，由 DeepSeek 为你提炼今日最核心的 3 条大事件！")

feeds = {
    "IT之家 (科技)": "https://www.ithome.com/rss/",
    "Solidot (奇客)": "https://www.solidot.org/index.rss",
    "少数派 (数字生活)": "https://sspai.com/feed"
}

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def clean_html(raw_html):
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', raw_html)
    return cleantext.strip()

def fetch_all_news():
    all_news_text = ""
    for name, url in feeds.items():
        try:
            response = requests.get(url, headers=headers, timeout=10)
            feed = feedparser.parse(response.text)
            if feed.entries:
                for entry in feed.entries[:3]: 
                    title = entry.title
                    summary = clean_html(entry.get('summary', '暂无摘要'))
                    if len(summary) > 100:
                        summary = summary[:100] + "..."
                    all_news_text += f"【{name}】 {title} - {summary}\n"
        except Exception:
            pass 
    return all_news_text

def generate_ai_summary(news_text):
    client = OpenAI(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        base_url="https://api.deepseek.com",
        timeout=60.0
    )
    
    prompt = f"""你是一个资深的科技与财经主编。
请根据以下抓取的最新新闻素材，为我写一份“今日核心简报”。
要求：
1. 挑出最重要、最有价值的 3 件事。
2. 语气专业、精炼，不要废话。
3. 用 Markdown 格式输出，每条提炼一个醒目的标题。

新闻素材：
{news_text}
"""
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"❌ AI 总结失败：{e}"

if st.button("🚀 一键抓取并生成今日简报", type="primary", use_container_width=True):
    
    with st.spinner("📡 正在全网抓取最新资讯..."):
        raw_news = fetch_all_news()
        
    if raw_news:
        with st.spinner("🧠 AI 主编正在疯狂阅读并提炼核心..."):
            summary = generate_ai_summary(raw_news)
            
            st.success("✅ 今日简报生成完毕！")
            st.divider()
            st.markdown(summary)
            st.divider()
            
            with st.expander("🔍 查看抓取到的原始新闻素材"):
                st.text(raw_news)
    else:
        st.error("❌ 所有新闻源均抓取失败，请检查网络。")
