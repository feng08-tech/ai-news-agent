import os
import requests
from bs4 import BeautifulSoup
from supabase import create_client
from datetime import datetime, timezone, timedelta

# ==========================================
# 1. 读取环境变量与初始化
# ==========================================
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
LLM_API_KEY = os.environ.get("LLM_API_KEY")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1") # 默认给个DeepSeek的，你可以改

if not all([SUPABASE_URL, SUPABASE_KEY, LLM_API_KEY]):
    raise ValueError("❌ 缺少必要的环境变量，请检查 GitHub Secrets！")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# 2. 抓取逻辑 (替换为你真实的网址)
# ==========================================
def fetch_all_news():
    print("开始抓取网页...")
    # 这里我随便找了个新闻网站做演示，你需要换成你真正要抓的网址
    url = "https://feng-aieditor.streamlit.app" 
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        response.encoding = 'utf-8'
        
        # 提取网页纯文本
        soup = BeautifulSoup(response.text, 'html.parser')
        # 这里只是简单提取段落，如果你有特定的 CSS 选择器，请在这里修改
        paragraphs = soup.find_all('p')
        text_content = "\n".join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
        
        return text_content[:5000] # 截取前5000字，防止超出 AI 模型的 token 限制
        
    except Exception as e:
        print(f"抓取失败: {e}")
        return None

# ==========================================
# 3. AI 总结逻辑 (兼容 OpenAI 格式)
# ==========================================
def generate_ai_summary(raw_text):
    print("开始 AI 总结...")
    if not raw_text:
        return None
        
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # 注意：把下面的 "deepseek-chat" 换成你实际使用的模型名称，比如 "gpt-4o-mini" 或 "deepseek-chat"
    payload = {
        "model": "deepseek-chat", 
        "messages": [
            {"role": "system", "content": "你是一个专业的全球军政情报主编。请对用户提供的新闻内容进行提炼总结，输出格式使用 Markdown。"},
            {"role": "user", "content": f"请帮我总结以下新闻：\n\n{raw_text}"}
        ],
        "temperature": 0.5
    }
    
    try:
        # 请求 AI 接口
        response = requests.post(f"{LLM_BASE_URL}/chat/completions", headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        
        result = response.json()
        summary = result['choices'][0]['message']['content']
        return summary
        
    except Exception as e:
        print(f"AI 总结失败: {e}")
        return None

# ==========================================
# 4. 主程序执行与写入
# ==========================================
if __name__ == "__main__":
    # 1. 抓取
    raw_data = fetch_all_news()
    
    if not raw_data or len(raw_data) < 50:
        print("⚠️ 抓取到的内容为空或太短，终止任务。")
        exit(0)
        
    # 2. 总结
    ai_summary = generate_ai_summary(raw_data)
    
    if ai_summary:
        print("正在写入 Supabase...")
        
        # 获取北京时间
        bj_time = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
        
        # 组装数据 (包含了所有你需要的字段)
        data_to_insert = {
            "topic": "全球军政内参",
            "time": bj_time,
            "summary": ai_summary,
            "content": ai_summary  # 把总结内容同时填给 content
        }
        
        try:
            # 写入数据库
            supabase.table("history").insert(data_to_insert).execute()
            print("✅ 数据写入成功！")
        except Exception as e:
            print(f"❌ 写入数据库失败: {e}")
            exit(1)
    else:
        print("⚠️ AI 总结为空，不写入数据。")
        exit(1)
