import streamlit as st
import feedparser
import re
import requests
import os
from openai import OpenAI
from dotenv import load_dotenv

# 加载本地环境变量
load_dotenv()

# ================= 核心：自动读取云端/本地密钥 =================
try:
    api_key = st.secrets["ANTHROPIC_API_KEY"]
    base_url = st.secrets.get("ANTHROPIC_BASE_URL", "https://api.deepseek.com")
except Exception:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.deepseek.com")
# ================================================================

st.set_page_config(page_title="AI 全球情报主编", page_icon="🌍", layout="centered")
st.title("🌍 AI 全球情报主编")
st.write("一键抓取中外多方信源，由 DeepSeek 自动翻译并提炼最核心的政治与军事地缘博弈事件。")

# 精选信源：涵盖中美俄欧、中东及国际组织
feeds = {
    "Defense News (美防务)": "https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml",
    "The War Zone (美战区)": "https://www.thedrive.com/the-war-zone/rss",
    "Reuters (路透社)": "https://www.reuters.com/arc/outboundfeeds/v3/all/?outputType=xml",
    "BBC World (英广播)": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "Al Jazeera (半岛中东)": "https://www.aljazeera.com/xml/rss/all.xml",
    "Sputnik (俄卫星社)": "https://sputniknews.cn/export/rss2/archive/index.xml",
    "中国军网 (解放军报)": "http://www.81.cn/rss/jfjb.xml",
    "新华网国际": "http://www.xinhuanet.com/world/news_world.xml",
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
                # 每个源抓取 8 条，保留足够的原素材
                for entry in feed.entries[:8]: 
                    title = entry.title
                    link = entry.link
                    summary = clean_html(entry.get('summary', '暂无摘要'))
                    if len(summary) > 100:
                        summary = summary[:100] + "..."
                    
                    # 拼装素材，格式： 【媒体】 标题 | 链接 | 摘要
                    all_news_text += f"【{name}】 【{title}】 (原文链接: {link}) - {summary}\n"
        except Exception:
            pass 
    return all_news_text

def generate_ai_summary(news_text):
    if not api_key:
        return "❌ 错误：未能获取到 API Key，请检查云端 Secrets 配置。"

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=60.0
    )
    
    # 极其严厉的 Prompt，逼迫 AI 输出完整链接
    prompt = f"""你是一个资深的国际政治与军事战略分析师，擅长情报整合与地缘博弈分析。
请根据以下抓取的多方信源新闻素材，为我写一份“今日全球地缘与军情简报”。
要求：
1. 挑出最重要、最具战略价值的 5 件事。
2. 无论素材是何种语言，请务必先将其准确翻译为地道、专业的中文，然后再进行总结。
3. 重点关注：大国博弈（中美俄欧）、地区冲突（如俄乌、中东、亚太）、以及敏感的军事部署与外交制裁。
4. 语气专业、客观、精炼（请综合对比不同立场媒体的报道，不要偏向单一视角）。
5. 用 Markdown 列表输出，每条提炼一个醒目标题。
6. **【强制要求】在每一条总结的最后，必须使用 `[点击阅读原文](完整的URL链接)` 的 Markdown 格式附上原文链接。绝对不要省略网址，也不要只写媒体名称，必须给出完整的、可点击的链接！如果合并了多个素材，请附上最重要的那一个链接。**

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

# ================= 网页界面 =================
if st.button("🚀 一键抓取并生成今日简报", type="primary", use_container_width=True):
    
    with st.spinner("📡 正在全网抓取中外最新资讯..."):
        raw_news = fetch_all_news()
        
    if raw_news:
        with st.spinner("🧠 AI 主编正在翻译、阅读并提炼核心..."):
            summary = generate_ai_summary(raw_news)
            
            st.success("✅ 今日情报生成完毕！")
            st.divider()
            # 渲染最终简报
            st.markdown(summary) 
            st.divider()
            
            # 底部折叠框：展示原汁原味的原始新闻，全部带可点击链接
            with st.expander("🔍 展开查看：抓取到的原始外文/中文新闻素材（可点击标题看原文）"):
                # 将素材解析成 Markdown 列表，让每个标题变成真正的超链接
                for line in raw_news.strip().split('\n'):
                    match = re.search(r'【(.*?)】 【(.*?)】 \(原文链接: (.*?)\) - (.*)', line)
                    if match:
                        media, title, link, summary = match.groups()
                        st.markdown(f"**[{media}]** [{title}]({link}) \n\n> {summary}\n")
    else:
        st.error("❌ 所有新闻源均抓取失败，请检查网络。")
