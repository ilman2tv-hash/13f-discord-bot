import os
import json
import hashlib
import requests
import feedparser

from datetime import datetime, timezone, timedelta
from deep_translator import GoogleTranslator



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

    "fed",
    "federal reserve",
    "interest rate",
    "rate cut",
    "rate hike",

    "cpi",
    "inflation",
    "jobs",
    "unemployment",

    "nasdaq",
    "s&p",
    "dow",

    "nvidia",
    "apple",
    "microsoft",
    "google",
    "amazon",
    "tesla",

    "ai",
    "artificial intelligence",
    "semiconductor",
    "chip",

    "war",
    "oil",
    "sanction",

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



def translate(text):

    try:

        return GoogleTranslator(
            source="auto",
            target="ko"
        ).translate(text)


    except Exception:

        return text



def score_news(text):

    score = 0

    text = text.lower()


    for word in KEYWORDS:

        if word in text:

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
                f"🚨 미국시장 뉴스 중요도 {score}/10",


                "description":

f"""
**{title}**


{summary}


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



        for item in feed.entries[:20]:


            title = item.title


            summary = item.get(
                "summary",
                ""
            )


            full_text = (

                title

                +

                summary

            )


            score = score_news(
                full_text
            )



            # 중요도 낮은 뉴스 제거

            if score < 2:

                continue



            uid = make_id(title)



            if uid in cache:

                continue



            cache.add(uid)



            ko_title = translate(title)

            ko_summary = translate(
                summary[:700]
            )



            send_discord(

                ko_title,

                ko_summary,

                source,

                min(score,10)

            )



    save_cache(cache)



if __name__ == "__main__":

    main()
