import os
import feedparser
import requests
import hashlib
from datetime import datetime, timezone, timedelta


WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")


# 뉴스 소스
RSS_FEEDS = {
    "Yahoo Finance":
        "https://finance.yahoo.com/news/rssindex",

    "CNBC":
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",

    "MarketWatch":
        "https://feeds.marketwatch.com/marketwatch/topstories/"
}


# 중요 키워드
HIGH_KEYWORDS = [

    # FED / 금리
    "fed",
    "federal reserve",
    "interest rate",
    "rate cut",
    "rate hike",

    # 경제지표
    "cpi",
    "ppi",
    "inflation",
    "jobs report",
    "unemployment",

    # 시장
    "stock market",
    "nasdaq",
    "s&p",
    "dow",

    # 빅테크
    "apple",
    "microsoft",
    "nvidia",
    "google",
    "amazon",
    "tesla",

    # 산업
    "semiconductor",
    "chip",
    "ai",
    "artificial intelligence",

    # 리스크
    "war",
    "sanction",
    "oil",
    "crude",

    # 기업 이벤트
    "earnings",
    "guidance",
    "merger",
    "acquisition",
    "sec",
]


sent_cache = set()



def get_score(text):

    score = 0

    text = text.lower()

    for k in HIGH_KEYWORDS:
        if k in text:
            score += 1

    return score



def make_hash(title):

    return hashlib.md5(
        title.encode()
    ).hexdigest()



def send_discord(title, summary, source, score):

    korea_time = (
        datetime.now(timezone.utc)
        +
        timedelta(hours=9)
    )

    color = 16711680 if score >= 5 else 16753920


    data = {

        "embeds":[
            {
                "title":
                f"🚨 MARKET NEWS ({score}/10)",

                "description":
                f"""
**{title}**

{summary}

📌 분류:
시장 영향 뉴스

📰 출처:
{source}

⏰ 시간:
{korea_time.strftime('%Y-%m-%d %H:%M KST')}
                """,

                "color": color
            }
        ]

    }


    requests.post(
        WEBHOOK_URL,
        json=data,
        timeout=10
    )



def translate(text):

    # 무료 번역 자리
    # 추후 GPT API 연결 가능

    return text



def collect_news():


    for source, url in RSS_FEEDS.items():

        feed = feedparser.parse(url)


        for item in feed.entries[:10]:

            title = item.title

            description = (
                item.get(
                    "summary",
                    ""
                )
            )


            total_text = (
                title
                +
                description
            )


            score = get_score(
                total_text
            )


            # 중요도 낮은 뉴스 제거
            if score < 2:
                continue


            uid = make_hash(title)


            if uid in sent_cache:
                continue


            sent_cache.add(uid)



            send_discord(

                translate(title),

                translate(description[:500]),

                source,

                min(score,10)

            )



if __name__ == "__main__":

    if not WEBHOOK_URL:
        raise Exception(
            "DISCORD_WEBHOOK missing"
        )


    collect_news()
