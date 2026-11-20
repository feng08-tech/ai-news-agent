import streamlit as st
import feedparser
import re
import requests
import os
from openai import OpenAI
from dotenv import load_dotenv
from supabase import create_client, Client
import datetime

# 加载本地环境变量（主要用于本地测试，云端依靠 st.secrets）
load_dotenv()

st.set_page_config(page_title="AI 全球情报主编", page_icon="🌍", layout="wide")
st.title("🌍 AI 全球情报主编")
st.write("全球政军情报自动翻译提炼，【历史记录已接入云端永久保存】。")

# ================= 1. 核心：读取与校验密钥 =================
try:
    # 优先从 Streamlit Secrets 读取
    api_key = st.secrets.get("LLM_API_KEY") or st.secrets.get("ANTHROPIC_API_KEY")
    base_url = st.secrets.get("LLM_BASE_URL", "https://api.deepseek.com")
    supabase_url = st.secrets.get("SUPABASE_URL")
    supabase_key = st.secrets.get("SUPABASE_KEY")
except Exception:
    # 本地测试从环境变量读取
    api_key = os.getenv("LLM_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

# 核心拦截：缺 Key 直接停机，避免满屏报错
if not api_key or not supabase_url or not supabase_key:
    st.error("⚠️ 配置缺失：请检查 Streamlit Secrets 中的 LLM_API_KEY, SUPABASE_URL, SUPABASE_KEY 是否配置正确。")
    st.info("注意：SUPABASE_URL 必须只保留纯域名（https://xxx.supabase.co），不要带 /rest/v1 等后缀！")
    st.stop()

# 初始化云数据库
try:
    supabase: Client = create_client(supabase_url, supabase_key)
except Exception as e:
    st.error(f"❌ 数据库连接失败，请检查 URL 和 KEY 格式：{e}")
    st.stop()

# ================= 2. 信源矩阵（多极视角 · 25个精选源） =================
feeds = {
    # --- 西方主流媒体（基准线） ---
    "Reuters (路透社)": "https://www.reuters.com/arc/outboundfeeds/v3/all/?outputType=xml",
    "NYT (纽约时报)": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "BBC (英国广播公司)": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "AP News (美联社)": "https://apnews.com/hub/ap-top-news/feed",
    "Washington Post (华盛顿邮报)": "https://feeds.washingtonpost.com/rss/world",

    # --- 中东与俄罗斯视角 ---
    "Al Jazeera (半岛中东)": "https://www.aljazeera.com/xml/rss/all.xml",
    "Tasnim News (伊朗塔斯尼姆)": "https://www.tasnimnews.com/en/rss/feed/0/8/0/all-news",
    "Sputnik (俄卫星社)": "https://sputniknews.cn/export/rss2/archive/index.xml",
    "RT News (今日俄罗斯)": "https://www.rt.com/rss/news/",
    "TASS (俄塔社)": "https://tass.com/rss/v2.xml",

    # --- 亚太地区 ---
    "SCMP (南华早报)": "http://www.scmp.com/rss/318213/feed",
    "Japan MoD (日本防卫省)": "https://www.mod.go.jp/j/rss/update.xml",
    "Asia Times (亚洲时报)": "https://asiatimes.com/feed/",
    "中国军网": "http://www.81.cn/rss/jfjb.xml",

    # --- 国际组织与智库（深度分析） ---
    "UN News (联合国)": "https://news.un.org/feed/subscribe/zh/news/all/rss.xml",
    "SIPRI (斯德哥尔摩国际和平研究所)": "https://www.sipri.org/rss/combined.xml",
    "Foreign Affairs (外交事务)": "http://www.foreignaffairs.com/rss.xml",
    "Crisis Group (国际危机组织)": "https://www.crisisgroup.org/latest-updates/feed",
    "Atlantic Council (大西洋理事会)": "https://www.atlanticcouncil.org/feed/",

    # --- 防务与开源情报 (OSINT) ---
    "ISW (战争研究所)": "https://www.understandingwar.org/feeds/all.xml",
    "Bellingcat (开源调查)": "https://www.bellingcat.com/feed/",
    "Defense News (防务新闻)": "https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml",
    "Breaking Defense (防务快报)": "https://breakingdefense.com/feed/",
    "The War Zone (战区)": "https://www.thedrive.com/the-war-zone/rss",
    "Defense One (防务一号)": "https://www.defenseone.com/rss/all",
}

headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

def clean_html(raw_html):
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, '', raw_html).strip()

# 缓存10分钟，如果你需要每次点击都抓取最新，把 ttl=600 改成 ttl=0
@st.cache_data(ttl=600)
def fetch_all_news():
    all_news_text = ""
    for name, url in feeds.items():
        try:
            # 增加 timeout 到 12 秒，适应更多源
            response = requests.get(url, headers=headers, timeout=12)
            feed = feedparser.parse(response.text)
            if feed.entries:
                for entry in feed.entries[:3]: # 每个源取最新的3条
                    title = entry.title
                    link = entry.link
                    summary = clean_html(entry.get('summary', '暂无摘要'))
                    if len(summary) > 80: summary = summary[:80] + "..."
                    all_news_text += f"【{name}】 [{title}]({link}) - {summary}\n"
        except Exception as e:
            # 如果某个源挂了（比如被墙），静默跳过并打印日志
            print(f"抓取 {name} 失败: {e}")
    return all_news_text

def generate_ai_summary(news_text):
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=120.0)
    prompt = f"""你是一个顶级的国际政治与军事战略分析师。
请根据以下素材，写一份“今日全球局势内参”。挑出最重要 5 件事，翻译为中文，重点关注大国博弈、军事动向和地缘冲突。
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

# ================= 3. 侧边栏：云端历史记录 =================
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

# ================= 4. 网页主界面 =================
if st.button("🚀 一键抓取并生成今日简报", type="primary", use_container_width=True):
    
    with st.spinner("📡 正在多线程抓取全球情报（由于信源较多，请耐心等待约10-20秒）..."):
        raw_news = fetch_all_news()
        
    if raw_news:
        with st.spinner("🧠 AI 正在深度提炼与研判..."):
            summary = generate_ai_summary(raw_news)
            
            if "❌" not in summary:
                st.success("✅ 生成完毕！并已自动保存至云端数据库。")
                st.markdown(summary)
                
                # 存入 Supabase
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
                lines = raw_news.strip().split('\n')
                for line in lines:
                    match = re.search(r'【(.*?)】\s*\[(.*?)\]\((.*?)\)\s*-\s*(.*)', line)
                    if match:
                        media, title, link, summary_text = match.groups()
                        st.markdown(f"**[{media}]** [{title}]({link}) \n\n> {summary_text}\n")
                    else:
                        st.text(line)
    else:
        st.error("❌ 所有新闻源均抓取失败，请检查网络或稍后再试。")
