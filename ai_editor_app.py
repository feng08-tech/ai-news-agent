import streamlit as st
import feedparser
import re
import requests
import os
from openai import OpenAI
from dotenv import load_dotenv
from supabase import create_client, Client
import datetime

load_dotenv()

st.set_page_config(page_title="AI 全球情报主编", page_icon="🌍", layout="wide")
st.title("🌍 AI 全球情报主编")
st.write("全球政军情报自动翻译提炼，【历史记录已接入云端永久保存】。")

# ================= 核心：读取与校验密钥 =================
try:
    # 建议在 Secrets 里统一用 LLM_API_KEY
    api_key = st.secrets.get("LLM_API_KEY") or st.secrets.get("ANTHROPIC_API_KEY")
    base_url = st.secrets.get("LLM_BASE_URL", "https://api.deepseek.com")
    supabase_url = st.secrets.get("SUPABASE_URL")
    supabase_key = st.secrets.get("SUPABASE_KEY")
except Exception:
    api_key = os.getenv("LLM_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

# 核心拦截：缺 Key 直接停机，避免满屏报错
if not api_key or not supabase_url or not supabase_key:
    st.error("⚠️ 配置缺失：请检查 Streamlit Secrets 中的 LLM_API_KEY, SUPABASE_URL, SUPABASE_KEY 是否配置正确。")
    st.info("注意：SUPABASE_URL 必须以 https:// 开头！")
    st.stop()

# 初始化数据库
try:
    supabase: Client = create_client(supabase_url, supabase_key)
except Exception as e:
    st.error(f"❌ 数据库连接失败，请检查 URL 和 KEY 格式：{e}")
    st.stop()

# ================= 信源矩阵 =================
feeds = {
    "Reuters (路透社)": "https://www.reuters.com/arc/outboundfeeds/v3/all/?outputType=xml",
    "NYT (纽约时报)": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "Al Jazeera (半岛中东)": "https://www.aljazeera.com/xml/rss/all.xml",
    "Tasnim News (伊朗塔斯尼姆)": "https://www.tasnimnews.com/en/rss/feed/0/8/0/all-news",
    "Sputnik (俄卫星社)": "https://sputniknews.cn/export/rss2/archive/index.xml",
    "Japan MoD (日本防卫省)": "https://www.mod.go.jp/j/rss/update.xml",
    "中国军网": "http://www.81.cn/rss/jfjb.xml",
    "UN News (联合国)": "https://news.un.org/feed/subscribe/zh/news/all/rss.xml"
}

headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

def clean_html(raw_html):
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, '', raw_html).strip()

# 注意：如果是测试，建议把 ttl 去掉，或者改成 60，否则 10 分钟内点按钮抓到的都是缓存
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
        except Exception as e:
            # 打印错误方便调试
            print(f"抓取 {name} 失败: {e}")
    return all_news_text

def generate_ai_summary(news_text):
    # 确保传入完整的 url
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=90.0)
    prompt = f"""你是一个顶级的国际政治与军事战略分析师。
请根据以下素材，写一份“今日全球局势内参”。挑出最重要 5 件事，翻译为中文，重点关注大国博弈。
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

# ================= 侧边栏 =================
with st.sidebar:
    st.header("☁️ 云端历史情报库")
    
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
            
            if "❌" not in summary:
                st.success("✅ 生成完毕！并已自动保存至云端数据库。")
                st.markdown(summary)
                
                now_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                try:
                    supabase.table("history").insert({
                        "time": now_time,
                        "topic": "全球局势",
                        "summary": summary
                    }).execute()
                except Exception as e:
                    st.error(f"写入云端失败：{e}")
            else:
                st.error(summary)

            st.divider()
            with st.expander("🔍 原始新闻素材（可点击看原文）"):
                # 这里建议按行解析
                lines = raw_news.strip().split('\n')
                for line in lines:
                    # 正则匹配稍作调整，防止有些摘要包含特殊字符导致匹配失败
                    match = re.search(r'【(.*?)】\s*\[(.*?)\]\((.*?)\)\s*-\s*(.*)', line)
                    if match:
                        media, title, link, summary_text = match.groups()
                        st.markdown(f"**[{media}]** [{title}]({link}) \n\n> {summary_text}\n")
                    else:
                        st.text(line) # 兜底显示
    else:
        st.error("❌ 所有新闻源均抓取失败，请检查网络。")
