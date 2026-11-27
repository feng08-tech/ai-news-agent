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

# ================= 2. 信源矩阵 =================
feeds = {
    "GoogleNews 全球军政": "https://news.google.com/rss/search?q=intitle:military+OR+intitle:war+OR+intitle:defense&hl=en-US&gl=US&ceid=US:en",
    "GoogleNews 俄乌局势": "https://news.google.com/rss/search?q=Ukraine+war+OR+Russia+military&hl=en-US&gl=US&ceid=US:en",
    "GoogleNews 印太安全": "https://news.google.com/rss/search?q=Taiwan+strait+OR+South+China+Sea+military&hl=en-US&gl=US&ceid=US:en",
    "GoogleNews 中文军事": "https://news.google.com/rss/search?q=军事+OR+国防+OR+冲突&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
    "ISW (战争研究所)": "https://www.understandingwar.org/feeds/all.xml",
    "Defense News": "https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml",
    "The War Zone": "https://www.thedrive.com/the-war-zone/rss",
    "Breaking Defense": "https://breakingdefense.com/feed/",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "SCMP": "http://www.scmp.com/rss/318213/feed",
    "UN News": "https://news.un.org/feed/subscribe/zh/news/all/rss.xml",
    "BBC Politics": "https://feeds.bbci.co.uk/news/politics/rss.xml",
    "The Guardian World": "https://www.theguardian.com/world/rss",
}

# ================= 新增：Telegram 公开频道 =================
# 注意：这里填频道名，不需要带 @ 或网址。
tg_channels = [
    "Osinttechnical",   # 极度活跃的装备与战况开源情报
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
        
        for entry in feed.entries[:6]:
            pub_time = None
            if hasattr(entry, "published"):
                try:
                    pub_time = parser.parse(entry.published)
                    if pub_time.tzinfo is None:
                        pub_time = pub_time.replace(tzinfo=datetime.timezone.utc)
                except Exception:
                    pass

            if pub_time and (now_utc - pub_time) > datetime.timedelta(days=2):
                continue

            title = entry.get("title", "无标题")
            link = entry.get("link", "")
            summary = clean_html(entry.get("summary", ""))
            if len(summary) > 150:
                summary = summary[:150] + "..."

            result_text += f"【{name}】 [{title}]({link}) - {summary}\n"
            
    except Exception:
        pass

    return result_text

# ================= 新增：抓取 Telegram 频道函数 =================
def fetch_telegram(channel: str, limit: int = 5) -> str:
    result_text = ""
    url = f"https://t.me/s/{channel}"
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            return ""
        
        soup = BeautifulSoup(response.text, "html.parser")
        # 定位每条消息的正文区块
        messages = soup.find_all("div", class_="tgme_widget_message_text")
        
        # 取最近的 limit 条（网页版一般一页有 20 条）
        for msg in messages[-limit:]:
            text = msg.get_text(separator="\n", strip=True)
            # 过滤掉太短的无意义信息
            if text and len(text) > 30:
                result_text += f"【Telegram @{channel} 快讯】 {text}\n\n"
                
    except Exception:
        pass
        
    return result_text

def fetch_all_news() -> str:
    all_news_text = ""
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        # 构建并发任务：RSS + Telegram
        future_to_source = {}
        
        # 加入 RSS 任务
        for name, url in feeds.items():
            future_to_source[executor.submit(fetch_single_feed, name, url)] = name
            
        # 加入 Telegram 任务
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

# ================= 4. 升级版 AI 情报研判 =================
def generate_ai_summary(news_text: str) -> str:
    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL, timeout=180.0)
    prompt = f"""你是一位极具战略眼光的全球地缘政治与军事分析师。请根据以下提供的全球最新资讯素材，撰写一份极其详尽、充满深度细节的《全球军政情报内参》。

要求：
1. 素材中包含了【Telegram 快讯】，这些是未经传统媒体证实的开源情报（OSINT）。在分析时请标明“据开源情报显示”，并结合正规媒体的报道进行交叉比对研判。
2. 必须包含以下四个模块，给出具体的细节分析：
   ## 🌍 宏观战略定调 (总结当前全球最大的地缘风险)
   ## 🔥 热点战区动态 (俄乌、中东、印太。写明具体部队番号、武器型号、控制区域变化，结合 Telegram 快讯提供最新动态)
   ## 🤝 大国博弈与外交经济 (中美俄欧的高层交锋、最新制裁法案、外交斡旋细节)
   ## ⚙️ 军工装备与前沿技术 (新型武器交付、军演细节、AI 与无人化作战进展)
3. 剔除无关的娱乐、社会花边新闻，只保留硬核军政资讯。
4. 如果有不同阵营媒体对同一事件报道有分歧，请在段落末尾加上【叙事差异研判】。
5. 语言必须极其专业、克制，大量使用军事与地缘政治术语。
6. 每条重要情报末尾必须附带原文链接，格式为：`[参考来源](URL)`。

素材：
{news_text}
"""
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
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
    print("开始 AI 深度研判...")

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
        "topic": "全球军政情报内参",
        "summary": summary,
    }).execute()

    print("完成，已写入 history 表。")

if __name__ == "__main__":
    main()
