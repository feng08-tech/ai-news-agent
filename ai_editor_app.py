import streamlit as st
import feedparser
import re
import requests
import os
from openai import OpenAI
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

# ================= 核心：读取密钥 =================
try:
    api_key = st.secrets["ANTHROPIC_API_KEY"]
    base_url = st.secrets.get("ANTHROPIC_BASE_URL", "https://api.deepseek.com")
    supabase_url = st.secrets["SUPABASE_URL"]
    supabase_key = st.secrets["SUPABASE_KEY"]
except Exception:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.deepseek.com")
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

# 初始化云数据库
supabase: Client = create_client(supabase_url, supabase_key)

st.set_page_config(page_title="AI 全球情报主编", page_icon="🌍", layout="wide")
st.title("🌍 AI 全球情报主编")
st.write("全球政军情报自动翻译提炼，【历史记录已接入云端永久保存】。")

# ================= 信源矩阵（保持你的多极视角） =================
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

headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

def clean_html(raw_html):
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, '', raw_html).strip()

@st.cache_data(ttl=600)
def fetch_all_news():
    all_news_text = ""
    for name, url in feeds.items():
        try:
            response = requests.get(url, headers=headers, timeout=8)
            feed = feedparser.parse(response.text)
            if feed.entries:
                for entry in feed.entries[:3]: 
                    title = entry.title
                    link = entry.link
                    summary = clean_html(entry.get('summary', '暂无摘要'))
                    if len(summary) > 80: summary = summary[:80] + "..."
                    all_news_text += f"【{name}】 [{title}]({link}) - {summary}\n"
        except Exception:
            pass 
    return all_news_text

def generate_ai_summary(news_text):
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=90.0)
    prompt = f"""你是一个顶级的国际政治与军事战略分析师。
请根据以下素材，写一份“今日全球局势内参”。挑出最重要 5 件事，翻译为中文，重点关注大国博弈，地缘政治，军事冲突，经济制裁。
每条总结最后，必须附上 `[点击阅读原文](完整URL)`。
素材：
{news_text}
"""
    try:
        response = client.chat.completions.create(
            model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"❌ 总结失败：{e}"

# ================= 侧边栏：云端历史记录 =================
with st.sidebar:
    st.header("☁️ 云端历史情报库")
    
    # 从 Supabase 读取数据
    try:
        response = supabase.table("history").select("*").order("time", desc=True).execute()
        history_data = response.data
    except Exception as e:
        st.error(f"读取云端失败：{e}")
        history_data = []

    if not history_data:
        st.info("云端暂无记录，快去生成第一条吧！")
    else:
        for item in history_data:
            with st.expander(f"🕒 {item.get('time', '未知时间')}"):
                st.markdown(item.get('summary', ''))
                # 增加删除功能
                if st.button("🗑️ 删除此条", key=f"del_{item.get('id')}"):
                    supabase.table("history").delete().eq("id", item.get('id')).execute()
                    st.rerun()

# ================= 网页主界面 =================
if st.button("🚀 一键抓取并生成今日简报", type="primary", use_container_width=True):
    
    with st.spinner("📡 正在抓取全球情报..."):
        raw_news = fetch_all_news()
        
    if raw_news:
        with st.spinner("🧠 AI 正在深度提炼..."):
            summary = generate_ai_summary(raw_news)
            
            st.success("✅ 生成完毕！并已自动保存至云端数据库。")
            st.markdown(summary)
            
            # 存入 Supabase 云端数据库
            import datetime
            now_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            try:
                supabase.table("history").insert({
                    "time": now_time,
                    "topic": "全球局势",
                    "summary": summary
                }).execute()
            except Exception as e:
                st.error(f"写入云端失败：{e}")

            st.divider()
            with st.expander("🔍 原始新闻素材（可点击看原文）"):
                for line in raw_news.strip().split('\n'):
                    match = re.search(r'【(.*?)】 \[(.*?)\] \((.*?)\) - (.*)', line)
                    if match:
                        media, title, link, summary_text = match.groups()
                        st.markdown(f"**[{media}]** [{title}]({link}) \n\n> {summary_text}\n")
    else:
        st.error("❌ 所有新闻源均抓取失败，请检查网络。")
