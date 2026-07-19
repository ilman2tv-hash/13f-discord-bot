import os
import json
import hashlib
import requests
import feedparser

from datetime import datetime, timezone, timedelta


WEBHOOK_URL = os.environ.get(
    "DISCORD_WEBHOOK"
)


CACHE_FILE = "news_cache.json"



RSS_LIST = {


    "Yahoo Finance":
    "https://finance.yahoo.com/news/rssindex",


    "CNBC":
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",


    "MarketWatch":
    "https://feeds.marketwatch.com/marketwatch/topstories/",


}



KEYWORDS = [

    # FED
    "fed",
    "federal reserve",
    "interest rate",
    "rate cut",
    "rate hike",

    # 경제
    "cpi",
    "inflation",
    "jobs",
    "unemployment",

    # 시장
    "nasdaq",
    "s&p",
    "dow",

    # AI 반도체
    "ai",
    "artificial intelligence",
    "nvidia",
    "semiconductor",
    "chip",

    # 빅테크
    "apple",
    "microsoft",
    "google",
    "amazon",
    "tesla",

    # 리스크
    "war",
    "oil",
    "sanction",

    # 기업 이벤트
    "earnings",
    "guidance",
    "merger",
    "acquisition"

]



def load_cache():

    if os.path.exists(CACHE_FILE):

        with open(
            CACHE_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return set(json.load(f))


    return set()



def save_cache(cache):

    with open(
        CACHE_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            list(cache),
            f,
            ensure_ascii=False,
            indent=2
        )



def make_id(text):

    return hashlib.md5(
        text.encode()
    ).hexdigest()



def score_news(text):

    score = 0

    text = text.lower()


    for k in KEYWORDS:

        if k in text:

            score += 1


    return score



def send_discord(
    title,
    summary,
    source,
    score
):


    kst = (
        datetime.now(timezone.utc)
        +
        timedelta(hours=9)
    )


    data = {


        "embeds":[

            {


            "title":
            f"🚨 MARKET NEWS {score}/10",


            "description":

f"""
**{title}**


{summary[:600]}


📰 출처:
{source}


⏰ 시간:
{kst.strftime('%Y-%m-%d %H:%M KST')}

"""


            }

        ]

    }



    requests.post(
        WEBHOOK_URL,
        json=data,
        timeout=10
    )



def main():


    if not WEBHOOK_URL:

        raise Exception(
            "DISCORD_WEBHOOK 없음"
        )



    cache = load_cache()



    for source,url in RSS_LIST.items():


        feed = feedparser.parse(url)



        for item in feed.entries[:15]:


            title = item.title


            summary = item.get(
                "summary",
                ""
            )


            text = title + summary



            score = score_news(text)



            # 중요 뉴스만

            if score < 2:

                continue



            uid = make_id(title)



            if uid in cache:

                continue



            cache.add(uid)



            send_discord(

                title,

                summary,

                source,

                min(score,10)

            )



    save_cache(cache)



if __name__ == "__main__":

    main()
