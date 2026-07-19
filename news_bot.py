import os
import json
import hashlib
import requests
import feedparser

from datetime import timezone, timedelta
from deep_translator import GoogleTranslator
from email.utils import parsedate_to_datetime


WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
CACHE_FILE = "news_cache.json"


# =========================
# 뉴스 출처
# =========================

RSS_LIST = {

    "Reuters Top":
    "https://feeds.reuters.com/reuters/topNews",

    "Reuters Business":
    "https://feeds.reuters.com/reuters/businessNews",

    "CNBC":
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",

    "AP News":
    "https://apnews.com/hub/ap-top-news/rss.xml"

}


# =========================
# 중요도 점수
# =========================

SCORE_RULES = {

    # 경제 지표

    "cpi": 10,
    "consumer price index": 10,

    "ppi": 10,
    "producer price index": 10,

    "inflation": 9,
    "employment": 9,
    "unemployment": 9,
    "jobs report": 9,
    "payroll": 9,

    "gdp": 9,
    "recession": 9,

    # 연준

    "fed": 10,
    "fomc": 10,
    "powell": 10,
    "interest rate": 10,
    "rate cut": 10,
    "rate hike": 10,

    # 대통령 / 정부

    "trump": 8,
    "president": 8,
    "white house": 8,

    "executive order": 9,
    "treasury": 8,
    "congress": 7,

    # 전쟁 / 안보

    "war": 10,
    "attack": 10,
    "missile": 10,
    "airstrike": 10,
    "explosion": 9,
    "military": 9,

    "iran": 9,
    "israel": 9,

    "russia": 9,
    "ukraine": 9,

    "china": 8,
    "taiwan": 8,

    "nuclear": 10,
    "terror": 10,

    # 경제 정책

    "tariff": 10,
    "sanction": 9,
    "tax": 8,

    # 에너지

    "oil": 8,
    "crude": 8,
    "opec": 9,

    # 기업

    "bankruptcy": 10,
    "earnings": 7,
    "guidance": 7,
    "forecast": 7,

    # 시장

    "nasdaq": 7,
    "s&p": 7,
    "dow": 7,

    # 우주

    "spacex": 7,
    "starship": 7,
    "rocket": 6,
    "launch": 6,
    "nasa": 6

}


# =========================
# 캐시
# =========================

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


# =========================
# 번역
# =========================

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


# =========================
# 중요도 계산
# =========================

def get_score(text):

    text = text.lower()

    score = 0

    for key, value in SCORE_RULES.items():

        if key in text:

            score += value

    return min(score, 10)


# =========================
# 한국 시간 변환
# =========================

def to_kst(published):

    if not published:

        return "시간 정보 없음"

    try:

        dt = parsedate_to_datetime(
            published
        )

        kst = dt.astimezone(

            timezone(
                timedelta(hours=9)
            )

        )

        return kst.strftime(
            "%Y-%m-%d %H:%M KST"
        )

    except:

        return published


# =========================
# 디스코드 전송
# =========================

def send_discord(

    title,
    summary,
    link,
    source,
    score,
    published

):

    if not summary:

        summary = (
            "기사 요약이 없습니다.\n"
            "원문 링크를 확인해 주세요."
        )

    message = f"""

📝 핵심 내용

{summary}


🔥 중요도

{score}/10


🔗 원문 링크

{link}


📰 출처

{source}


🕒 뉴스 시간

{published}

"""

    requests.post(

        WEBHOOK_URL,

        json={

            "embeds": [

                {

                    "title":
                    "🚨 미국 시장 속보\n" + title,

                    "description":
                    message,

                    "color":
                    16711680

                }

            ]

        }

    )


# =========================
# 메인
# =========================

def main():

    cache = load_cache()

    for source, url in RSS_LIST.items():

        feed = feedparser.parse(url)

        for item in feed.entries[:30]:

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

            published = item.get(
                "published",
                ""
            )

            uid = hashlib.md5(

                (
                    title +
                    link
                ).encode()

            ).hexdigest()

            if uid in cache:

                continue

            full_text = (

                title +
                " " +
                summary

            )

            score = get_score(
                full_text
            )

            # 중요 뉴스만 전송

            if score < 7:

                continue

            cache.add(uid)

            send_discord(

                translate(title),

                translate(
                    summary[:400]
                ),

                link,

                source,

                score,

                to_kst(
                    published
                )

            )

    save_cache(cache)


if __name__ == "__main__":

    main()
