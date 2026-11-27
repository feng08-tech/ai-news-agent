import os
import re
import sys
import datetime
import concurrent.futures

import requests
import feedparser
from dateutil import parser
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
    "US DoD (美国国防部)": "https://www.defense.gov/DesktopModules/ArticleCS/RSS.ashx?ContentType=1&Site=945&max=10",
    "NATO (北约)": "https://www.nato.int/cps/en/natohq/news_rss.htm",
    "Japan MoD (日本防卫省)": "https://www.mod.go.jp/j/rss/update.xml",
    "中国军网": "http://www.81.cn/rss/jfjb.xml",
    "ISW (战争研究所)": "https://www.understandingwar.org/feeds/all.xml",
    "War on the Rocks": "https://warontherocks.com/feed/",
    "SIPRI (斯德哥尔摩和平研究所)": "https://www.sipri.org/rss/combined.xml",
    "Crisis Group": "https://www.crisisgroup.org/latest-updates/feed",
    "Atlantic Council": "https://www.atlanticcouncil.org/feed/",
    "Defense News": "https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml",
    "The War Zone": "https://www.thedrive.com/the-war-zone/rss",
    "Breaking Defense": "https://breakingdefense.com/feed/",
    "Bellingcat": "https://www.bellingcat.com/feed/",
    "Reuters World": "https://feeds.reuters.com/Reuters/worldNews",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "Sputnik": "https://sputniknews.cn/export/rss2/archive/index.xml",
    "RT News": "https://www.rt.com/rss/news/",
    "SCMP": "http://www.scmp.com/rss/318213/feed",
    "UN News": "https://news.un.org/feed/subscribe/zh/news/all/rss.xml",
    "Reuters Politics": "https://feeds.reuters.com/reuters/politicsNews",
    "AP World News": "https://openrss.org/feed/apnews.com/world-news",
    "AP Politics": "https://apnews.com/hub/politics?output=rss",
    "BBC Politics": "https://feeds.bbci.co.uk/news/politics/rss.xml",
    "The Guardian World": "https://www.theguardian.com/world/rss",
    "The Diplomat": "https://thediplomat.com/feed/",
    "The Diplomat Asia Defense": "https://thediplomat.com/category/asia-defense/feed/",
    "Middle East Eye": "https://www.middleeasteye.net/rss",
    "Janes": "https://www.janes.com/feeds/news",
    "Foreign Affairs": "https://www.foreignaffairs.com/rss.xml",
    "Foreign Policy": "https://foreignpolicy.com/feed/",
    "RAND International Affairs": "https://www.rand.org/rss.xml?feed=international-affairs",
    "ECFR": "https://ecfr.eu/feed/",
    "EU Commission Press": "https://ec.europa.eu/commission/presscorner/api/rss?language=en",
}

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

# ================= 3. 抓取与清洗 (带调试信息) =================
def clean_html(raw_html: str) -> str:
    cleanr = re.compile("<.*?>")
    return re.sub(cleanr, "", raw_html or "").strip()

def fetch_single_feed(name: str, url: str) -> str:
    result_text = ""
    try:
        response = requests.get(url, headers=headers, timeout=10)
        feed = feedparser.parse(response.text)

        if not feed.entries:
            print(f"❌ [{name}] 抓取失败，可能被屏蔽或无更新。")
            return ""

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        valid_count = 0

        for entry in feed.entries[:3]:
            pub_time = None
            if hasattr(entry, "published"):
                try:
                    pub_time = parser.parse(entry.published)
                    if pub_time.tzinfo is None:
                        pub_time = pub_time.replace(tzinfo=datetime.timezone.utc)
                except Exception:
                    pass

            # 如果超过24小时，跳过
            if pub_time and (now_utc - pub_time) > datetime.timedelta(days=1):
                continue

            title = entry.get("title", "无标题")
            link = entry.get("link", "")
            summary = clean_html(entry.get("summary", "暂无摘要"))
            if len(summary) > 80:
                summary = summary[:80] + "..."

            result_text += f"【{name}】 [{title}]({link}) - {summary}\n"
            valid_count += 1
            
        if valid_count == 0:
             print(f"⚠️ [{name}] 抓取到了数据，但全部在24小时之外被过滤了。")

    except Exception as e:
        print(f"❌ [{name}] 请求异常: {str(e)[:50]}")

    return result_text

def fetch_all_news() -> str:
    all_news_text = ""
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        future_to_feed = {
            executor.submit(fetch_single_feed, name, url): name
            for name, url in feeds.items()
        }
        for future in concurrent.futures.as_completed(future_to_feed):
            try:
                res = future.result()
                if res:
                    all_news_text += res
            except Exception:
                pass
    return all_news_text

# ================= 4. AI 情报研判 =================
def generate_ai_summary(news_text: str) -> str:
    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL, timeout=120.0)
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
5. 每条情报末尾必须附带原文链接，格式为：`[查看原文](URL)`
6. 如果素材中某类新闻没有，则跳过该类。

素材：
{news_text}
"""
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"❌ 总结失败：{e}"

# ================= 5. 主入口 =================
def main():
    print("开始抓取全球新闻...")
    raw_news = fetch_all_news()

    if not raw_news.strip():
        print(f"⚠️ 所有 {len(feeds)} 个源都没有抓到 24 小时内的内容，终止任务。")
        sys.exit(1)  # 强制报错，让 GitHub 变红
        
    print(f"抓取完成，素材长度：{len(raw_news)} 字符")
    print("开始 AI 研判...")

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
        "topic": "全球军政内参",
        "summary": summary,
    }).execute()

    print("完成，已写入 history 表。")

if __name__ == "__main__":
    main()
