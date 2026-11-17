import streamlit as st
import feedparser
import re
import requests
import os
from openai import OpenAI
from dotenv import load_dotenv

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
st.title("🌍 AI 全球情报主编 (精准搜索版)")
st.write("输入关键词，系统将定向抓取全球各大媒体的相关报道并进行深度提炼。")

# 🌟 新增：搜索输入框
search_keyword = st.text_input("🔍 输入定向侦察关键词（留空则抓取全网头条）：", placeholder="例如：伊朗、俄乌、半导体、中东局势")

feeds = {
    # 顶级通讯社
    "Reuters (路透社)": "https://www.reuters.com/arc/outboundfeeds/v3/all/?outputType=xml",
    "AP News (美联社)": "https://rsshub.app/apnews/topics/apf-topnews",
    # 西方大报
    "NYT (纽约时报)": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "BBC World (英广播)": "https://feeds.bbci.co.uk/news/world/rss.xml",
    # 中东与多极视角
    "Al Jazeera (半岛中东)": "https://www.aljazeera.com/xml/rss/all.xml",
    "Tasnim News (伊朗塔斯尼姆)": "https://www.tasnimnews.com/en/rss/feed/0/8/0/all-news",
    "Sputnik (俄卫星社)": "https://sputniknews.cn/export/rss2/archive/index.xml",
    # 亚太与日本防务
    "Japan MoD (日本防卫省)": "https://www.mod.go.jp/j/rss/update.xml",
    "Asagumo News (朝云新闻)": "https://www.asagumo-news.com/feed/",
    # 中国视角
    "中国军网": "http://www.81.cn/rss/jfjb.xml",
    "新华网国际": "http://www.xinhuanet.com/world/news_world.xml"
}

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def clean_html(raw_html):
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', raw_html)
    return cleantext.strip()

# 🌟 核心修改：把搜索词加进缓存参数里，保证不同的搜索词有不同的缓存结果
@st.cache_data(ttl=600)
def fetch_all_news(keyword):
    all_news_text = ""
    keyword_lower = keyword.strip().lower() if keyword else ""
    
    for name, url in feeds.items():
        try:
            response = requests.get(url, headers=headers, timeout=8)
            feed = feedparser.parse(response.text)
            if feed.entries:
                for entry in feed.entries:
                    title = entry.title
                    summary = clean_html(entry.get('summary', '暂无摘要'))
                    
                    # 🌟 关键词过滤逻辑：如果输入了关键词，但标题和摘要里都没有，直接跳过
                    if keyword_lower:
                        if keyword_lower not in title.lower() and keyword_lower not in summary.lower():
                            continue # 跳过不相关的新闻
                            
                    link = entry.link
                    if len(summary) > 100:
                        summary = summary[:100] + "..."
                    all_news_text += f"【{name}】 [{title}]({link}) - {summary}\n"
                    
                    # 如果某个源已经找到了 2 条相关的，就不往下找了，节省时间
                    if keyword_lower and all_news_text.count(f"【{name}】") >= 2:
                        break
        except Exception:
            pass 
    return all_news_text

def generate_ai_summary(news_text, keyword):
    if not api_key:
        return "❌ 错误：未能获取到 API Key，请检查云端 Secrets 配置。"

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=90.0)
    
    # 🌟 根据有无关键词，动态调整提示词
    if keyword:
        focus_prompt = f"用户正在定向搜索关于【{keyword}】的情报。请必须围绕该关键词提取核心事件，如果素材中没有相关信息，请直接回答“暂无相关情报”。"
    else:
        focus_prompt = "请提取今日全球最重要的 5 件地缘与军情大事。"

    prompt = f"""你是一个顶级的国际政治与军事战略分析师。
{focus_prompt}
要求：
1. 将所有外文新闻准确翻译为地道、专业的中文。
2. 重点关注大国博弈、地区冲突、军事部署，经济动向，地缘政治。
3. 用 Markdown 列表输出，每条提炼醒目标题。
4. **【强制要求】每条总结最后，必须附上 `[点击阅读原文](完整URL)` 的 Markdown 链接。**

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
    
    with st.spinner("📡 正在全网定向扫描相关资讯..."):
        # 把搜索词传进去
        raw_news = fetch_all_news(search_keyword)
        
    if raw_news:
        with st.spinner("🧠 AI 主编正在进行深度分析..."):
            summary = generate_ai_summary(raw_news, search_keyword)
            
            st.success("✅ 今日情报生成完毕！")
            st.divider()
            st.markdown(summary) 
            st.divider()
            
            with st.expander("🔍 展开查看：抓取到的相关原始新闻素材（可点击标题看原文）"):
                for line in raw_news.strip().split('\n'):
                    match = re.search(r'【(.*?)】 \[(.*?)\] \((.*?)\) - (.*)', line)
                    if match:
                        media, title, link, summary_text = match.groups()
                        st.markdown(f"**[{media}]** [{title}]({link}) \n\n> {summary_text}\n")
    else:
        st.warning(f"⚠️ 在所有监控的信源中，暂未找到与【{search_keyword}】相关的新闻。请尝试换个关键词（如：美国、俄罗斯、芯片）。")
