import streamlit as st
import feedparser
import re
import requests
import os
from openai import OpenAI
from dotenv import load_dotenv
from supabase import create_client, Client
import datetime
from dateutil import parser # 需要安装 python-dateutil
import concurrent.futures

# 加载本地环境变量
load_dotenv()

st.set_page_config(page_title="全球政军情报主编", page_icon="🌍", layout="wide")
st.title("🌍 全球政军情报指挥中心")
st.write("自动抓取全球防务、智库与官方情报，【24小时热点实时研判，云端永久保存】。")

# ================= 1. 核心：读取与校验密钥 =================
try:
    api_key = st.secrets.get("LLM_API_KEY") or st.secrets.get("ANTHROPIC_API_KEY")
    base_url = st.secrets.get("LLM_BASE_URL", "https://api.deepseek.com")
    supabase_url = st.secrets.get("SUPABASE_URL")
    supabase_key = st.secrets.get("SUPABASE_KEY")
except Exception:
    api_key = os.getenv("LLM_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

if not api_key or not supabase_url or not supabase_key:
    st.error("⚠️ 配置缺失：请检查 Streamlit Secrets 中的 LLM_API_KEY, SUPABASE_URL, SUPABASE_KEY。")
    st.stop()

try:
    supabase: Client = create_client(supabase_url, supabase_key)
except Exception as e:
    st.error(f"❌ 数据库连接失败：{e}")
    st.stop()

# ================= 2. 硬核信源矩阵 =================
feeds = {
    # --- 官方防务与军事机构 ---
    "US DoD (美国国防部)": "https://www.defense.gov/DesktopModules/ArticleCS/RSS.ashx?ContentType=1&Site=945&max=10",
    "NATO (北约)": "https://www.nato.int/cps/en/natohq/news_rss.htm",
    "Japan MoD (日本防卫省)": "https://www.mod.go.jp/j/rss/update.xml",
    "中国军网": "http://www.81.cn/rss/jfjb.xml",

    # --- 顶级智库与深度分析 ---
    "ISW (战争研究所)": "https://www.understandingwar.org/feeds/all.xml",
    "War on the Rocks (岩石上的战争)": "https://warontherocks.com/feed/",
    "SIPRI (斯德哥尔摩和平研究所)": "https://www.sipri.org/rss/combined.xml",
    "Crisis Group (国际危机组织)": "https://www.crisisgroup.org/latest-updates/feed",
    "Atlantic Council (大西洋理事会)": "https://www.atlanticcouncil.org/feed/",

    # --- 防务与开源情报 (OSINT) ---
    "Defense News (防务新闻)": "https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml",
    "The War Zone (战区)": "https://www.thedrive.com/the-war-zone/rss",
    "Breaking Defense (防务快报)": "https://breakingdefense.com/feed/",
    "Bellingcat (开源调查)": "https://www.bellingcat.com/feed/",

    # --- 多极视角主流媒体 ---
    "Reuters World (路透国际)": "https://www.reuters.com/arc/outboundfeeds/v3/all/?outputType=xml",
    "Al Jazeera (半岛中东)": "https://www.aljazeera.com/xml/rss/all.xml",
    "Sputnik (俄卫星社)": "https://sputniknews.cn/export/rss2/archive/index.xml",
    "RT News (今日俄罗斯)": "https://www.rt.com/rss/news/",
    "SCMP (南华早报)": "http://www.scmp.com/rss/318213/feed",
    "UN News (联合国)": "https://news.un.org/feed/subscribe/zh/news/all/rss.xml"
}

headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

def clean_html(raw_html):
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, '', raw_html).strip()

# ================= 3. 并发抓取与时间过滤 =================
def fetch_single_feed(name, url):
    result_text = ""
    try:
        response = requests.get(url, headers=headers, timeout=10)
        feed = feedparser.parse(response.text)
        
        # 获取当前 UTC 时间，用于过滤 24 小时内的新闻
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        
        for entry in feed.entries[:3]: # 每个源最多取3条
            # 尝试解析发布时间
            pub_time = None
            if hasattr(entry, 'published'):
                try:
                    pub_time = parser.parse(entry.published)
                    # 统一时区
                    if pub_time.tzinfo is None:
                        pub_time = pub_time.replace(tzinfo=datetime.timezone.utc)
                except:
                    pass
            
            # 如果解析出了时间，且超过 24 小时，则跳过
            if pub_time and (now_utc - pub_time) > datetime.timedelta(days=1):
                continue
                
            title = entry.title
            link = entry.link
            summary = clean_html(entry.get('summary', '暂无摘要'))
            if len(summary) > 80: summary = summary[:80] + "..."
            result_text += f"【{name}】 [{title}]({link}) - {summary}\n"
            
    except Exception as e:
        # 静默忽略失败的源，避免控制台报错刷屏
        pass
    return result_text

@st.cache_data(ttl=60) # 极短缓存，防止误触导致重复消耗API
def fetch_all_news():
    all_news_text = ""
    # 开启多线程并发抓取
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        future_to_feed = {executor.submit(fetch_single_feed, name, url): name for name, url in feeds.items()}
        for future in concurrent.futures.as_completed(future_to_feed):
            res = future.result()
            if res:
                all_news_text += res
    return all_news_text

# ================= 4. AI 情报研判 (重构 Prompt) =================
def generate_ai_summary(news_text):
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=120.0)
    prompt = f"""你是一位极其资深的全球地缘政治与军事战略分析师。
请根据以下抓取到的全球最新资讯，撰写一份专业的《全球军政情报内参》。

要求：
1. 必须按照以下三个结构输出：
   ## 🔥 热点战区动态（俄乌、中东、印太等实际交战或对峙区域）
   ## 🤝 大国博弈与外交（中美俄欧高层交锋、制裁与反制）
   ## ⚙️ 军工与装备发展（武器交付、军演、国防预算）
2. 剔除无关的娱乐、经济、社会新闻，只保留硬核政军资讯。
3. 如果不同阵营媒体对同一事件有报道，请在段落末尾加上【叙事差异研判】。
4. 语言必须克制、专业，使用军事术语（如：兵力集结、战略威慑、对等反制）。
5. 每条情报末尾**必须**附带原文链接，格式为：`[查看原文](URL)`
6. 如果素材中某类新闻没有，则跳过该类。

素材：
{news_text}
"""
    try:
        response = client.chat.completions.create(
            model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.5
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"❌ 总结失败：{e}"

# ================= 5. 前端界面：侧边栏 =================
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

# ================= 6. 前端界面：主工作区 =================
if st.button("🚀 一键抓取并生成今日内参", type="primary", use_container_width=True):
    
    with st.spinner("📡 多线程正在抓取全球防务情报（仅筛选24小时内新闻）..."):
        raw_news = fetch_all_news()
        
    if raw_news:
        with st.spinner("🧠 AI 正在生成结构化军政内参..."):
            summary = generate_ai_summary(raw_news)
            
            if "❌" not in summary:
                st.success("✅ 情报生成完毕！已自动存入云端历史库。")
                
                # --- 关键词高亮处理 ---
                highlight_words = ["核武器", "导弹", "航母", "制裁", "军事演习", "冲突", "战争", "兵力", "战机", "无人机"]
                display_summary = summary
                for word in highlight_words:
                    # 使用 HTML 标签加粗标红，注意不要覆盖原有的 Markdown 链接
                    display_summary = re.sub(rf'(?<!\[)({word})(?!\])', r'**<span style="color:#ff4b4b;">\1</span>**', display_summary)
                
                # 渲染总结 (开启 unsafe_allow_html 以支持标红)
                st.markdown(display_summary, unsafe_allow_html=True)
                
                # 存入 Supabase
                now_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                try:
                    supabase.table("history").insert({
                        "time": now_time,
                        "topic": "全球军政内参",
                        "summary": summary
                    }).execute()
                except Exception as e:
                    st.error(f"写入云端失败：{e}")
            else:
                st.error(summary)

            st.divider()
            with st.expander("🔍 查看抓取到的原始新闻素材"):
                lines = raw_news.strip().split('\n')
                for line in lines:
                    match = re.search(r'【(.*?)】\s*\[(.*?)\]\((.*?)\)\s*-\s*(.*)', line)
                    if match:
                        media, title, link, summary_text = match.groups()
                        st.markdown(f"**[{media}]** [{title}]({link}) \n\n> {summary_text}\n")
                    else:
                        st.text(line)
    else:
        st.error("❌ 未抓取到24小时内的有效新闻，请稍后再试或检查网络。")
