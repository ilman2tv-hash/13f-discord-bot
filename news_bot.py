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



POSITIVE = [

    "beat",
    "beats",
    "upgrade",
    "raises",
    "growth",
    "record",
    "approval",
    "partnership",
    "investment",
    "ai",
    "artificial intelligence",
    "rate cut",
    "lower rates",
    "strong earnings"

]


NEGATIVE = [

    "miss",
    "downgrade",
    "warning",
    "lawsuit",
    "investigation",
    "recession",
    "inflation",
    "rate hike",
    "sanction",
    "war"

]



SECTOR = {

    "ai":
    "AI",

    "artificial intelligence":
    "AI",

    "chip":
    "반도체",

    "semiconductor":
    "반도체",

    "oil":
    "에너지",

    "fed":
    "금리",

    "interest rate":
    "금리",

}



TICKERS = {

    "nvidia":"NVDA",

    "apple":"AAPL",

    "microsoft":"MSFT",

    "tesla":"TSLA",

    "amazon":"AMZN",

    "google":"GOOGL",

    "meta":"META",

    "amd":"AMD",

    "intel":"INTC",

    "tsm":"TSM"

}



def load_cache():

    if os.path.exists(CACHE_FILE):

        with open(
            CACHE_FILE,
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
            ensure_ascii=False
        )



def translate(text):

    try:

        return GoogleTranslator(
            source="auto",
            target="ko"
        ).translate(text)

    except:

        return text



def analyze(text):

    text=text.lower()


    pos=sum(
        1 for x in POSITIVE
        if x in text
    )


    neg=sum(
        1 for x in NEGATIVE
        if x in text
    )


    score=5


    if pos>neg:

        direction="🟢 긍정"

        score+=pos


        reason=(
            "기업 성장 기대 또는 "
            "시장 심리 개선 요인"
        )


    elif neg>pos:

        direction="🔴 부정"

        score+=neg


        reason=(
            "실적 우려 또는 "
            "투자심리 악화 가능성"
        )


    else:

        direction="🟡 중립"

        reason=(
            "추가 정보 확인 필요"
        )


    sectors=[]


    for k,v in SECTOR.items():

        if k in text:

            sectors.append(v)



    tickers=[]


    for k,v in TICKERS.items():

        if k in text:

            tickers.append(v)



    return (

        direction,

        min(score,10),

        reason,

        list(set(sectors)),

        list(set(tickers))

    )



def send_discord(
    title,
    summary,
    source,
    direction,
    score,
    reason,
    sectors,
    tickers
):


    kst=datetime.now(
        timezone.utc
    )+timedelta(hours=9)



    message=f"""

📝 핵심 내용

{summary}


📊 투자자 해석

{reason}


📈 시장 영향

{direction}


영향 섹터:
{', '.join(sectors) if sectors else '시장 전체'}


관련 종목:
{', '.join(tickers) if tickers else '확인 필요'}


🔥 중요도:
{score}/10


📰 출처:
{source}


⏰ 시간:
{kst.strftime('%Y-%m-%d %H:%M KST')}

"""


    requests.post(

        WEBHOOK_URL,

        json={

            "embeds":[

                {

                "title":
                "🚨 미국시장 핵심 뉴스\n"+title,

                "description":
                message

                }

            ]

        }

    )



def main():

    cache=load_cache()



    for source,url in RSS_LIST.items():

        feed=feedparser.parse(url)



        for item in feed.entries[:15]:

            title=item.title

            summary=item.get(
                "summary",
                ""
            )


            uid=hashlib.md5(
                title.encode()
            ).hexdigest()



            if uid in cache:

                continue



            full=title+" "+summary



            direction,score,reason,sectors,tickers=analyze(full)



            if score < 6:

                continue



            cache.add(uid)



            send_discord(

                translate(title),

                translate(summary[:800]),

                source,

                direction,

                score,

                reason,

                sectors,

                tickers

            )



    save_cache(cache)



if __name__=="__main__":

    main()
