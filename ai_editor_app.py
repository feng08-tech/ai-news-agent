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

# 扩充的国际政治与军事信源（国内+国外+中立）
feeds = {
    # 1. 西方视角与深度军情
    "Defense News (美防务)": "https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml",
    "The War Zone (美战区)": "https://www.thedrive.com/the-war-zone/rss",
    "Reuters (路透社)": "https://www.reuters.com/arc/outboundfeeds/v3/all/?outputType=xml",
    "BBC World (英广播)": "https://feeds.bbci.co.uk/news/world/rss.xml",

    # 2. 中东与非西方视角
    "Al Jazeera (半岛中东)": "https://www.aljazeera.com/xml/rss/all.xml",
    "Sputnik (俄卫星社)": "https://sputniknews.cn/export/rss2/archive/index.xml",

    # 3. 中国官方视角（内网直连，极度稳定）
    "中国军网 (解放军报)": "http://www.81.cn/rss/jfjb.xml",
    "新华网国际": "http://www.xinhuanet.com/world/news_world.xml",

    # 4. 绝对中立国际视角
    "UN News (联合国)": "https://news.un.org/feed/subscribe/zh/news/all/rss.xml"
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
    
    prompt = f"""你是一个资深的国际政治与军事战略分析师，擅长情报整合与地缘博弈分析。
请根据以下抓取的多方信源新闻素材，为我写一份“今日全球地缘与军情简报”。
要求：
1. 挑出最重要、最具战略价值的 5 件事。
2. **重点关注：大国博弈（中美俄欧）、地区冲突（如俄乌、中东、亚太）、以及敏感的军事部署与外交制裁。**
3. 语气专业、客观、精炼（请综合对比不同立场媒体的报道，不要偏向单一视角）。
4. 用 Markdown 列表输出，每条提炼一个醒目标题，并且必须保留原始素材中的链接格式，以便我点击查看原文。

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
            
            with st.expander("🔍 展开查看：所有抓取到的原始新闻（最多可达70条，可点击原文）"):
                st.markdown(raw_news)
    else:
        st.error("❌ 所有新闻源均抓取失败，请检查网络。")
