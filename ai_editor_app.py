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

st.set_page_config(page_title="AI 全球情报主编", page_icon="🌍", layout="wide")
st.title("🌍 AI 全球情报主编 (究极版)")
st.write("聚合全球顶级通讯社与主流媒体，自动翻译并提炼最核心的全球政军情报。")

# ================= 终极全球情报信源矩阵 =================
feeds = {
    # 1. 顶级国际通讯社（中立视角）
    "Reuters (路透社)": "https://www.reuters.com/arc/outboundfeeds/v3/all/?outputType=xml",
    "AP News (美联社)": "https://rsshub.app/apnews/topics/apf-topnews", # 通过 RSSHub 抓取
    "AFP (法新社)": "https://www.france24.com/en/afp/rss", # 法新社通常依附于合作媒体发布

    # 2. 西方顶级大报与媒体
    "NYT (纽约时报)": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "WSJ (华尔街日报)": "https://feeds.a.dj.com/rss/RSSWorldNews.xml",
    "BBC World (英广播)": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "The Guardian (卫报)": "https://www.theguardian.com/world/rss",

    # 3. 欧洲与亚太视角
    "DW (德国之声)": "https://rss.dw.com/rdf/rss-en-world",
    "France 24 (法国24)": "https://www.france24.com/en/rss",
    "SCMP (南华早报)": "https://www.scmp.com/rss/91/feed", # 亚洲视角的重要英文媒体
    "Straits Times (海峡时报)": "https://www.straitstimes.com/news/world/rss.xml",

    # 4. 中东、伊朗与俄罗斯（多极博弈视角）
    "Al Jazeera (半岛中东)": "https://www.aljazeera.com/xml/rss/all.xml",
    "Tasnim News (伊朗塔斯尼姆)": "https://www.tasnimnews.com/en/rss/feed/0/8/0/all-news",
    "IRNA (伊朗官方)": "https://en.irna.ir/rss",
    "Sputnik (俄卫星社)": "https://sputniknews.cn/export/rss2/archive/index.xml",

    # 5. 日本防务与军事
    "Japan MoD (日本防卫省)": "https://www.mod.go.jp/j/rss/update.xml",
    "Asagumo News (朝云新闻)": "https://www.asagumo-news.com/feed/",

    # 6. 中国视角
    "中国军网": "http://www.81.cn/rss/jfjb.xml",
    "新华网国际": "http://www.xinhuanet.com/world/news_world.xml",

    # 7. 国际组织
    "UN News (联合国)": "https://news.un.org/feed/subscribe/zh/news/all/rss.xml"
}

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def clean_html(raw_html):
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', raw_html)
    return cleantext.strip()

# 🌟 安全阀：缓存抓取结果 10 分钟，避免频繁请求拖垮程序
@st.cache_data(ttl=600)
def fetch_all_news():
    all_news_text = ""
    for name, url in feeds.items():
        try:
            response = requests.get(url, headers=headers, timeout=8) # 缩短单源超时时间
            feed = feedparser.parse(response.text)
            if feed.entries:
                # 每个源只抓取前 3 条（信源实在太多了，必须限流）
                for entry in feed.entries[:3]: 
                    title = entry.title
                    link = entry.link
                    summary = clean_html(entry.get('summary', '暂无摘要'))
                    if len(summary) > 80:
                        summary = summary[:80] + "..."
                    all_news_text += f"【{name}】 [{title}]({link}) - {summary}\n"
        except Exception:
            pass 
    return all_news_text

def generate_ai_summary(news_text):
    if not api_key:
        return "❌ 错误：未能获取到 API Key，请检查云端 Secrets 配置。"

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=90.0)
    
    prompt = f"""你是一个顶级的国际政治与军事战略分析师，擅长情报整合与地缘博弈分析。
请根据以下抓取的全球多方信源新闻素材，为我写一份“今日全球局势内参”。
要求：
1. 挑出最重要、最具战略价值的 5 件事。
2. 将所有外文新闻准确翻译为地道、专业的中文。
3. 重点关注：大国博弈、地区冲突、军事部署、外交制裁,经济博弈，地缘政治。
4. **【核心要求】进行多极视角的交叉验证。例如：对比西方媒体（路透/纽约时报）与中东媒体（半岛/塔斯尼姆）对同一事件的不同叙事；对比中日两国的防务动态。**
5. 用 Markdown 列表输出，每条提炼醒目标题。
6. **【强制要求】每条总结最后，必须附上 `[点击阅读原文](完整URL)` 的 Markdown 链接。绝对不要省略！**

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
    
    with st.spinner("📡 正在全网抓取全球顶级媒体资讯（首次抓取约需 10 秒）..."):
        raw_news = fetch_all_news()
        
    if raw_news:
        with st.spinner("🧠 AI 主编正在翻译、交叉比对并提炼核心..."):
            summary = generate_ai_summary(raw_news)
            
            st.success("✅ 今日情报生成完毕！")
            st.divider()
            st.markdown(summary) 
            st.divider()
            
            with st.expander("🔍 展开查看：抓取到的全球原始新闻素材（可点击标题看原文）"):
                for line in raw_news.strip().split('\n'):
                    match = re.search(r'【(.*?)】 \[(.*?)\] \((.*?)\) - (.*)', line)
                    if match:
                        media, title, link, summary_text = match.groups()
                        st.markdown(f"**[{media}]** [{title}]({link}) \n\n> {summary_text}\n")
    else:
        st.error("❌ 所有新闻源均抓取失败，请检查网络。")
