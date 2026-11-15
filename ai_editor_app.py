import streamlit as st
import feedparser
import re
import requests
import os
from openai import OpenAI
from dotenv import load_dotenv

# 加载本地环境变量
load_dotenv()

# ================= 核心修复：全局读取云端/本地密钥 =================
try:
    api_key = st.secrets["ANTHROPIC_API_KEY"]
    base_url = st.secrets.get("ANTHROPIC_BASE_URL", "https://api.deepseek.com")
except Exception:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.deepseek.com")
# ==================================================================

st.set_page_config(page_title="AI 智能新闻主编", page_icon="📰", layout="centered")
st.title("📰 AI 智能新闻主编")
st.write("一键抓取全球媒体最新资讯，由 DeepSeek 为你提炼核心政治与军事事件（附原文链接）！")

# ================= 扩充的国际政治与军事信源 =================
feeds = {
    "Defense News (防务新闻)": "https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml",
    "Breaking Defense (防务快报)": "https://breakingdefense.com/feed/",
    "Defense One (防务一号)": "https://www.defenseone.com/rss/all/",
    "The War Zone (战区)": "https://www.thedrive.com/the-war-zone/rss",
    "Reuters (路透社)": "https://www.reuters.com/arc/outboundfeeds/v3/all/?outputType=xml",
    "Al Jazeera (半岛电视台)": "https://www.aljazeera.com/xml/rss/all.xml",
    "BBC World (BBC国际)": "https://feeds.bbci.co.uk/news/world/rss.xml"
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
                # 🌟 核心改动：把 [:3] 改成 [:10]，每个源抓 10 条
                for entry in feed.entries[:10]: 
                    title = entry.title
                    link = entry.link
                    summary = clean_html(entry.get('summary', '暂无摘要'))
                    if len(summary) > 100:
                        summary = summary[:100] + "..."
                    all_news_text += f"【{name}】 [{title}]({link}) - {summary}\n"
        except Exception:
            pass 
    return all_news_text

def generate_ai_summary(news_text):
    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=60.0
    )
    
    # 注意：抓取的新闻太多，为了避免 AI 脑容量爆炸（Token超限），这里限制它只挑最核心的 5 条
    prompt = f"""你是一个资深的国际政治与军事战略分析师。
请根据以下抓取的新闻素材，为我写一份“今日全球局势简报”。
要求：
1. 挑出最重要、最具战略价值的 5 件事，必须兼顾国际政治动向（如外交博弈、大选、制裁）与军事冲突（如地区战争、军备部署）。
2. 语气专业、客观、精炼。
3. 用 Markdown 列表输出，每条提炼一个醒目标题，并且必须保留原始素材中的链接格式，以便我点击查看原文。

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
    
    with st.spinner("📡 正在全网抓取海量资讯..."):
        raw_news = fetch_all_news()
        
    if raw_news:
        with st.spinner("🧠 AI 主编正在疯狂阅读并提炼核心..."):
            summary = generate_ai_summary(raw_news)
            
            st.success("✅ 今日简报生成完毕！")
            st.divider()
            st.markdown(summary) 
            st.divider()
            
            # 🌟 这里就是让你看更多新闻的入口！
            with st.expander("🔍 展开查看：所有抓取到的原始新闻（最多可达70条，可点击原文）"):
                st.markdown(raw_news)
    else:
        st.error("❌ 所有新闻源均抓取失败，请检查网络。")
