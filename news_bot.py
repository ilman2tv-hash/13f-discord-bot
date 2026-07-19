import os
import json
import hashlib
import requests
import feedparser

from datetime import datetime, timezone, timedelta
from deep_translator import GoogleTranslator


WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")

CACHE_FILE = "news_cache.json"


RSS_LIST = {

    "Reuters":
    "https://feeds.reuters.com/reuters/topNews",

    "Reuters Business":
    "https://feeds.reuters.com/reuters/businessNews",

    "CNBC":
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",

    "Yahoo Finance":
    "https://finance.yahoo.com/news/rssindex",

}


BREAKING_KEYWORDS = [

    # 경제 지표
    "cpi",
    "consumer price index",

    "ppi",
    "producer price index",

    "inflation",
    "jobs report",
    "employment",
    "unemployment",
    "payroll",

    # 연준
    "fed",
    "fomc",
    "powell",
    "interest rate",
    "rate cut",
    "rate hike",

    # 전쟁 / 지정학
    "war",
    "missile",
    "attack",
    "drone",
    "explosion",

    "iran",
    "israel",

    "russia",
    "ukraine",

    "china",
    "taiwan",

    # 관세 / 제재
    "tariff",
    "sanction",

    # 에너지
    "oil",
    "crude",

    # 우주
    "spacex",
    "starship",
    "rocket",
    "launch",
    "nasa",

    # 긴급 속보
    "breaking",
    "urgent",
    "emergency"
]


SECTOR = {

    "ai": "AI",

    "artificial intelligence": "AI",

    "chip": "반도체",

    "semiconductor": "반도체",

    "oil": "에너지",

    "fed": "금리",

    "interest rate": "금리",

    "spacex": "우주",

    "rocket": "우주"

}


TICKERS = {

    "nvidia": "NVDA",

    "apple": "AAPL",

    "microsoft": "MSFT",

    "tesla": "TSLA",

    "amazon": "AMZN",

    "google": "GOOGL",

    "meta": "META",

    "amd": "AMD",

    "intel": "INTC",

    "tsm": "TSM"

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

    if not text:

        return ""

    try:

        return GoogleTranslator(
            source="auto",
            target="ko"
        ).translate(text)

    except:

        return text


def analyze(text):

    text = text.lower()

    score = 6

    sectors = []

    tickers = []

    for key, value in SECTOR.items():

        if key in text:

            sectors.append(value)

    for key, value in TICKERS.items():

        if key in text:

            tickers.append(value)

    if any(
        word in text
        for word in [
            "war",
            "missile",
            "attack",
            "explosion"
        ]
    ):

        direction = "🔴 지정학적 위험"

        reason = (
            "전쟁·공격 뉴스는 "
            "시장 변동성을 키울 수 있습니다."
        )

        score = 9

    elif any(
        word in text
        for word in [
            "cpi",
            "ppi",
            "inflation",
            "fed",
            "fomc"
        ]
    ):

        direction = "🟡 경제 이벤트"

        reason = (
            "금리·물가 관련 뉴스는 "
            "미국 증시에 큰 영향을 줍니다."
        )

        score = 9

    elif any(
        word in text
        for word in [
            "spacex",
            "rocket",
            "launch"
        ]
    ):

        direction = "🚀 기술 이벤트"

        reason = (
            "우주·기술 산업 관련 "
            "대형 이벤트입니다."
        )

        score = 7

    else:

        direction = "🟢 시장 뉴스"

        reason = (
            "미국 시장과 관련된 "
            "중요 뉴스입니다."
        )

    return (

        direction,

        score,

        reason,

        list(set(sectors)),

        list(set(tickers))

    )


def send_discord(

    title,
    summary,
    link,
    source,
    direction,
    score,
    reason,
    sectors,
    tickers

):

    kst = datetime.now(
        timezone.utc
    ) + timedelta(hours=9)

    if not summary.strip():

        summary = (
            "기사 요약이 제공되지 않았습니다.\n"
            "원문 링크를 확인해 주세요."
        )

    message = f"""

📝 핵심 내용

{summary}


📊 투자자 해석

{reason}


📈 시장 영향

{direction}


🏢 영향 섹터

{', '.join(sectors) if sectors else '시장 전체'}


📌 관련 종목

{', '.join(tickers) if tickers else '확인 필요'}


🔥 중요도

{score}/10


🔗 원문 링크

{link}


📰 출처

{source}


⏰ 시간

{kst.strftime('%Y-%m-%d %H:%M KST')}

"""

    requests.post(

        WEBHOOK_URL,

        json={

            "embeds": [

                {

                    "title":
                    "🚨 미국시장 핵심 뉴스\n" + title,

                    "description":
                    message,

                    "color":
                    3447003

                }

            ]

        }

    )


def main():

    cache = load_cache()

    for source, url in RSS_LIST.items():

        feed = feedparser.parse(url)

        for item in feed.entries[:20]:

            title = item.get(
                "title",
                ""
            )

            summary = item.get(
                "summary",
                ""
            )

            link = item.get(
                "link",
                ""
            )

            uid = hashlib.md5(

                (
                    title + link
                ).encode()

            ).hexdigest()

            if uid in cache:

                continue

            full = (

                title
                + " "
                + summary

            )

            full_lower = full.lower()

            if not any(

                keyword in full_lower

                for keyword
                in BREAKING_KEYWORDS

            ):

                continue

            direction, score, reason, sectors, tickers = analyze(

                full

            )

            cache.add(uid)

            send_discord(

                translate(title),

                translate(summary[:400]),

                link,

                source,

                direction,

                score,

                reason,

                sectors,

                tickers

            )

    save_cache(cache)


if __name__ == "__main__":

    main()
