import os
import re
import sys
import datetime
import concurrent.futures

import requests
import feedparser
from dateutil import parser
from bs4 import BeautifulSoup
from openai import OpenAI
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

# ================= 1. 读取环境变量 =================
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

missing = []
if not LLM_API_KEY: missing.append("LLM_API_KEY")
if not SUPABASE_URL: missing.append("SUPABASE_URL")
if not SUPABASE_KEY: missing.append("SUPABASE_KEY")

if missing:
    raise SystemExit(f"缺少环境变量：{', '.join(missing)}")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ================= 2. 全球无死角信源矩阵（包含中国深度视角） =================
feeds = {
    # --- 中国核心视角与中文资讯 ---
    "GoogleNews 中国军事": "https://news.google.com/rss/search?q=解放军+OR+中国军方+OR+中国国防部&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
    "GoogleNews 台海动态": "https://news.google.com/rss/search?q=台海+OR+台湾+演习+OR+军售&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
    "GoogleNews 中国外交": "https://news.google.com/rss/search?q=中国外交部+OR+中美关系+OR+中俄合作&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
    "SCMP (南华早报)": "http://www.scmp.com/rss/318213/feed",

    # --- 亚洲与大洋洲 ---
    "Nikkei Asia (日经亚洲)": "https://asia.nikkei.com/rss/feed/nar",
    "Times of India (印度时报)": "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
    "GoogleNews 印太安全": "https://news.google.com/rss/search?q=Taiwan+strait+OR+South+China+Sea+military&hl=en-US&gl=US&ceid=US:en",

    # --- 欧洲与俄罗斯 ---
    "ISW (战争研究所)": "https://www.understandingwar.org/feeds/all.xml",
    "Politico Europe (欧洲政治)": "https://www.politico.eu/feed/",
    "The Guardian World": "https://www.theguardian.com/world/rss",
    "GoogleNews 俄乌局势": "https://news.google.com/rss/search?q=Ukraine+war+OR+Russia+military&hl=en-US&gl=US&ceid=US:en",

    # --- 北美洲与全球军政/经济 ---
    "Defense News": "https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml",
    "The War Zone": "https://www.thedrive.com/the-war-zone/rss",
    "FT (金融时报)": "https://www.ft.com/rss/home",
    "Bloomberg (彭博-政治)": "https://feeds.bloomberg.com/politics/news.rss",
    "GoogleNews 制裁与关税": "https://news.google.com/rss/search?q=sanctions+OR+tariffs+OR+geopolitics+economy&hl=en-US&gl=US&ceid=US:en",

    # --- 中东 ---
    "Al Jazeera (半岛)": "https://www.aljazeera.com/xml/rss/all.xml",
    "Times of Israel (以色列)": "https://www.timesofisrael.com/feed/",

    # --- 非洲 ---
    "AllAfrica (全非新闻)": "https://allafrica.com/tools/headlines/rdf/latest/headlines.rdf",
    "GoogleNews 非洲安全": "https://news.google.com/rss/search?q=Africa+military+OR+Africa+conflict+OR+Sahel+security&hl=en-US&gl=US&ceid=US:en",

    # --- 南美洲 ---
    "Mercopress (南美地缘)": "https://en.mercopress.com/rss/",
    "GoogleNews 拉美动态": "https://news.google.com/rss/search?q=South+America+military+OR+Latin+America+security&hl=en-US&gl=US&ceid=US:en",

    # --- 南北两极 ---
    "GoogleNews 极地地缘": "https://news.google.com/rss/search?q=Arctic+military+OR+Antarctica+geopolitics&hl=en-US&gl=US&ceid=US:en",
}

# ================= 新增：Telegram 公开频道 =================
tg_channels = [
    "Osinttechnical",   # 装备与战况开源情报
    "sentdefender",     # 全球防务与突发快讯
    "wartranslated",    # 俄乌前线战报翻译
]

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

# ================= 3. 抓取与清洗 =================
def clean_html(raw_html: str) -> str:
    cleanr = re.compile("<.*?>")
    return re.sub(cleanr, "", raw_html or "").strip()

def fetch_single_feed(name: str, url: str) -> str:
    result_text = ""
    try:
        response = requests.get(url, headers=headers, timeout=15)
        feed = feedparser.parse(response.text)

        if not feed.entries:
            return ""

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        
        for entry in feed.entries[:8]:
            pub_time = None
            if hasattr(entry, "published"):
                try:
                    pub_time = parser.parse(entry.published)
                    if pub_time.tzinfo is None:
                        pub_time = pub_time.replace(tzinfo=datetime.timezone.utc)
                except Exception:
                    pass

            if pub_time and (now_utc - pub_time) > datetime.timedelta(days=3):
                continue

            title = entry.get("title", "无标题")
            link = entry.get("link", "")
            summary = clean_html(entry.get("summary", ""))
            if len(summary) > 200:
                summary = summary[:200] + "..."

            result_text += f"【{name}】 [{title}]({link}) - {summary}\n"
            
    except Exception:
        pass

    return result_text

def fetch_telegram(channel: str, limit: int = 8) -> str:
    result_text = ""
    url = f"https://t.me/s/{channel}"
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            return ""
        
        soup = BeautifulSoup(response.text, "html.parser")
        messages = soup.find_all("div", class_="tgme_widget_message_text")
        
        for msg in messages[-limit:]:
            text = msg.get_text(separator="\n", strip=True)
            if text and len(text) > 30:
                result_text += f"【Telegram @{channel} 快讯】 {text}\n\n"
                
    except Exception:
        pass
        
    return result_text

def fetch_all_news() -> str:
    all_news_text = ""
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        future_to_source = {}
        for name, url in feeds.items():
            future_to_source[executor.submit(fetch_single_feed, name, url)] = name
        for channel in tg_channels:
            future_to_source[executor.submit(fetch_telegram, channel)] = f"TG_{channel}"

        for future in concurrent.futures.as_completed(future_to_source):
            try:
                res = future.result()
                if res:
                    all_news_text += res
            except Exception:
                pass
    return all_news_text

# ================= 4. 终极全球视野 Prompt =================
def generate_ai_summary(news_text: str) -> str:
    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL, timeout=180.0)
    prompt = f"""你是一位顶级地缘政治智库的首席分析师。请根据以下全球最新素材，撰写一份极其详尽、具有战略纵深的《全球军政与经济深度内参》。

【写作要求】：
1. 绝对不要写流水账！必须深挖事件背后的动机，并预测下一步走向。
2. 必须包含以下六大板块，篇幅要长，内容要硬核。如果某板块当天确实没有新闻素材，请注明“本日该区域态势平稳”，严禁遗漏板块：
   ## 🌍 一、宏观战略定调 (当前全球最大风险与底层逻辑)
   ## 🔥 二、核心战区动态推演 (俄乌、中东、印太。重点分析台海与南海动态，提取武器型号并结合 Telegram 快讯推演)
   ## 💰 三、地缘经济与制裁博弈 (中美经贸、科技战、军费、制裁、能源、供应链武器化)
   ## 🌐 四、边缘地带扫描 (重点扫描：拉美、非洲、南北极。分析区域冲突、资源争夺与大国渗透)
   ## 🤝 五、大国交锋与外交暗战 (中美俄欧最新法案背后的真实筹码，中国外交的最新动向)
   ## ⚙️ 六、军工前沿与战争形态 (AI、无人机、新型弹药在实战中的演进，以及中国军工的突破)
3. 强化【情报交叉验证】：当正规媒体与 Telegram 快讯有出入时，必须单列段落进行研判。如果西方媒体与中文媒体（如南华早报、GoogleNews中文源）对同一事件有不同叙事，请明确指出【叙事差异研判】。
4. 语言极其克制、专业，充满“地缘博弈”、“经济威慑”、“消耗战”等术语。
5. 每条重要情报必须附带原文链接：`[参考来源](URL)`。

【素材】：
{news_text}
"""
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            max_tokens=4000
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"❌ 总结失败：{e}"

# ================= 5. 主入口 =================
def main():
    print("开始抓取全球新闻与 Telegram 快讯...")
    raw_news = fetch_all_news()

    if not raw_news.strip():
        print("⚠️ 没有抓到内容，终止任务。")
        sys.exit(1)
        
    print(f"抓取完成，素材长度：{len(raw_news)} 字符")
    print("开始 AI 深度战略推演...")

    summary = generate_ai_summary(raw_news)

    if summary.startswith("❌"):
        print(summary)
        sys.exit(1)

    now_time = datetime.datetime.now(
        datetime.timezone(datetime.timedelta(hours=8))
    ).strftime("%Y-%m-%d %H:%M")

    print("写入 Supabase...")
    supabase.table("history").insert({
        "time": now_time,
        "topic": "全球军政经济内参",
        "summary": summary,
    }).execute()

    print("完成，已写入 history 表。")

if __name__ == "__main__":
    main()
