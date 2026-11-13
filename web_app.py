import streamlit as st
import os
import requests
import json
import time
import hmac
import hashlib
import base64
import urllib.parse
from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime
from bs4 import BeautifulSoup

load_dotenv()

# ================= 配置区域 =================
# ⚠️ 请把下面引号里的内容换成你自己的真实数据！
DINGTALK_WEBHOOK = "https://oapi.dingtalk.com/robot/send?access_token=69b36940ef9ba884b92503cd7d948f8d702976e6824a393cfba46d56daaae596"
DINGTALK_SECRET = "SEC49f300fbb22571d34706711d9f777f53347e58141f008667a989e2f8b3c4f7a1"
# ============================================

st.set_page_config(page_title="AI 新闻秘书", page_icon="🧠", layout="wide", initial_sidebar_state="collapsed")
st.title("🧠 我的 AI 新闻秘书 5.0")
st.write("点击下方按钮，AI 会生成简报、自动配图并推送到钉钉！")

HISTORY_FILE = "history.json"
def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_history(topic, summary):
    history = load_history()
    record = {"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "topic": topic, "summary": summary}
    history.insert(0, record) 
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=4)

with st.sidebar:
    st.header("📚 历史简报库")
    history_data = load_history()
    if not history_data:
        st.info("暂无历史记录，快去生成第一条吧！")
    else:
        for item in history_data:
            with st.expander(f"🕒 {item['time']} | {item['topic']}"):
                st.write(item['summary'])
        if st.button("🗑️ 清空历史记录"):
            if os.path.exists(HISTORY_FILE):
                os.remove(HISTORY_FILE)
                st.rerun()

user_topic = st.text_input("你想让 AI 关注什么主题？", value="今日最新的 AI 行业新闻")

persona = st.selectbox("选择 AI 的人设：", ["资深科技主编", "幽默段子手", "小红书爆款文案", "暴躁老哥"])
import feedparser

def fetch_news(query):
    # 使用 BBC 中文网的 RSS 源，极其稳定，不会被反爬拦截
    rss_url = "https://feeds.bbci.co.uk/zhongwen/simp/rss.xml"
    try:
        feed = feedparser.parse(rss_url)
        news_list = []
        # 提取前 5 条真实新闻
        for entry in feed.entries[:5]:
            news_list.append({"title": entry.title})
        if news_list:
            return news_list
        else:
            return [{"title": f"未抓取到新闻，请基于知识库生成关于【{query}】的总结。"}]
    except Exception as e:
        return [{"title": f"网络异常({e})，请基于知识库生成关于【{query}】的总结。"}]
def summarize_with_ai(news_list, query):
    news_text = "\n".join([f"- {item['title']}" for item in news_list])
    client = OpenAI(api_key=os.getenv("ANTHROPIC_API_KEY"), base_url="https://api.deepseek.com", timeout=60.0)
    prompt = f"你现在的身份是【{persona}】。请围绕【{query}】，根据以下信息写一段 150 字左右的简报。\n参考：\n{news_text}"
    try:
        response = client.chat.completions.create(
            model="deepseek-chat", messages=[{"role": "user", "content": prompt}], temperature=0.7, stream=True
        )
        def generate_chunks():
            for chunk in response:
                if chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content
        return generate_chunks()
    except Exception as e:
        error_msg = str(e)
        def error_chunk(): yield f"ERROR: {error_msg}"
        return error_chunk()

def generate_image(prompt):
    encoded_prompt = urllib.parse.quote(prompt)
    return f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=800&height=400&nologo=true"
def send_to_dingtalk(title, text):
    timestamp = str(round(time.time() * 1000))
    secret_enc = DINGTALK_SECRET.encode('utf-8')
    string_to_sign = '{}\n{}'.format(timestamp, DINGTALK_SECRET)
    string_to_sign_enc = string_to_sign.encode('utf-8')
    hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    url = f"{DINGTALK_WEBHOOK}&timestamp={timestamp}&sign={sign}"
    headers = {'Content-Type': 'application/json;charset=utf-8'}
    data = {"msgtype": "markdown", "markdown": {"title": title, "text": f"### {title}\n\n{text}"}}
    try:
        response = requests.post(url, data=json.dumps(data), headers=headers)
        return response.json().get("errcode") == 0
    except Exception:
        return False

if st.button("🚀 立即生成并推送简报", type="primary"):
    if not user_topic:
        st.warning("请先输入主题！")
    else:
        with st.spinner(f"正在生成关于【{user_topic}】的简报..."):
            news = fetch_news(user_topic)
            summary_generator = summarize_with_ai(news, user_topic)
            
            st.success("AI 简报生成成功！")
            full_summary = st.write_stream(summary_generator)
            
            if full_summary.startswith("ERROR:"):
                st.error(f"生成失败：\n{full_summary}")
            else:
                with st.spinner("🎨 正在加载封面图..."):
                    image_url = generate_image(f"{user_topic}, technology")
                    st.image(image_url, caption="科技感新闻简报", use_container_width=True)
                
                save_history(user_topic, full_summary)
                st.toast("✅ 已自动保存到历史记录库", icon="💾")
                
                # 👇 下载按钮（注意它和上面的 save_history 对齐）
                st.download_button(
                    label="📥 下载这份简报 (.md格式)",
                    data=full_summary,
                    file_name=f"AI简报_{user_topic}_{persona}.md",
                    mime="text/markdown"
                )
                
                with st.spinner("正在推送到钉钉..."):
                    # 👇 下面这行就是报错的那行，保证它的缩进是在 with 内部
                    if send_to_dingtalk(f"【{user_topic}】简报", full_summary):
                        st.balloons() 
                        st.success("🎉 钉钉推送成功，请查看手机！")
                    else:
                        st.error("❌ 钉钉推送失败。")
                     
                   
