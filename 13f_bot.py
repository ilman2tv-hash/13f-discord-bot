import os
import requests
import xml.etree.ElementTree as ET

# =========================================================
# 📌 Discord Webhook
# GitHub Secrets:
# SEC_13F_WEBHOOK_URL
# =========================================================
DISCORD_URL = os.environ.get("SEC_13F_WEBHOOK_URL")

# =========================================================
# 📌 추적 대상 (시장 흐름 + 기관 자금 이동 중심)
# =========================================================
gurus = {
    "버크셔 해서웨이": "0001067983",
    "스탠리 드러켄밀러": "0001568832",
    "데이비드 테퍼": "0000905567",

    "Bridgewater": "0001350694",
    "Coatue Management": "0001461573",
    "Tiger Global": "0001456346"
}

# =========================================================
# 📌 SEC 요청 헤더
# =========================================================
HEADERS = {
    "User-Agent": "yourname yourmail@example.com",
    "Accept-Encoding": "gzip, deflate",
    "Host": "www.sec.gov"
}

# =========================================================
# 📌 티커 변환
# =========================================================
def get_ticker_from_cusip(cusip):
    if not cusip:
        return None

    try:
        url = f"https://query1.finance.yahoo.com/v1/finance/search?q={cusip}"

        res = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=5
        )

        if res.status_code == 200:
            data = res.json()

            quotes = data.get("quotes", [])

            if quotes:
                symbol = quotes[0].get("symbol")

                if symbol:
                    return symbol.upper()

    except Exception as e:
        print(f"CUSIP 변환 실패: {e}")

    return None

# =========================================================
# 📌 백업용 이름 변환
# =========================================================
def fallback_ticker(name):

    table = {
        "APPLE": "AAPL",
        "MICROSOFT": "MSFT",
        "NVIDIA": "NVDA",
        "AMAZON": "AMZN",
        "ALPHABET": "GOOGL",
        "META": "META",
        "TESLA": "TSLA",
        "BROADCOM": "AVGO",
        "NETFLIX": "NFLX",
        "REALTY INCOME": "O",
        "PFIZER": "PFE",
        "VERIZON": "VZ"
    }

    upper_name = name.upper()

    for k, v in table.items():
        if k in upper_name:
            return v

    return upper_name[:12]

# =========================================================
# 📌 13F XML 파싱
# =========================================================
def get_holdings_from_sec(cik, accession_number):

    holdings = {}

    try:

        acc = accession_number.replace("-", "")

        index_url = (
            f"https://www.sec.gov/Archives/edgar/data/"
            f"{int(cik)}/{acc}/index.json"
        )

        res = requests.get(index_url, headers=HEADERS, timeout=10)

        if res.status_code != 200:
            return holdings

        files = res.json()["directory"]["item"]

        xml_file = None

        # 우선순위 탐색
        for f in files:
            name = f["name"].lower()

            if (
                name.endswith(".xml")
                and (
                    "infotable" in name
                    or "informationtable" in name
                    or "form13f" in name
                )
            ):
                xml_file = f["name"]
                break

        # fallback
        if not xml_file:
            for f in files:
                if f["name"].endswith(".xml"):
                    xml_file = f["name"]
                    break

        if not xml_file:
            return holdings

        xml_url = (
            f"https://www.sec.gov/Archives/edgar/data/"
            f"{int(cik)}/{acc}/{xml_file}"
        )

        xml_res = requests.get(xml_url, headers=HEADERS, timeout=10)

        root = ET.fromstring(xml_res.content)

        ns = {}

        if "}" in root.tag:
            ns = {
                "ns": root.tag.split("}")[0].strip("{")
            }

        infos = (
            root.findall(".//ns:infoTable", ns)
            if ns
            else root.findall(".//infoTable")
        )

        for info in infos[:80]:

            try:
                issuer = (
                    info.find(".//ns:nameOfIssuer", ns).text
                    if ns
                    else info.find(".//nameOfIssuer").text
                )

                cusip = (
                    info.find(".//ns:cusip", ns).text
                    if ns
                    else info.find(".//cusip").text
                )

                shares_node = (
                    info.find(".//ns:sshPrnamt", ns)
                    if ns
                    else info.find(".//sshPrnamt")
                )

                if shares_node is None:
                    continue

                shares = int(float(shares_node.text))

                ticker = get_ticker_from_cusip(cusip)

                if not ticker:
                    ticker = fallback_ticker(issuer)

                holdings[ticker] = holdings.get(ticker, 0) + shares

            except:
                continue

    except Exception as e:
        print(f"13F 파싱 실패: {e}")

    return holdings

# =========================================================
# 📌 포지션 비교
# =========================================================
def compare_holdings(current, previous):

    trades = []

    # 신규 + 매수
    for ticker, cur_shares in current.items():

        if ticker not in previous:

            trades.append({
                "ticker": ticker,
                "action": "신규진입 🔥",
                "shares": f"{cur_shares:,} 주",
                "change": "NEW"
            })

        else:

            prev_shares = previous[ticker]

            diff = cur_shares - prev_shares

            if diff > 0:

                pct = (diff / prev_shares) * 100

                trades.append({
                    "ticker": ticker,
                    "action": "매수 🟢",
                    "shares": f"+{diff:,} 주",
                    "change": f"+{pct:.1f}%"
                })

    # 매도
    for ticker, prev_shares in previous.items():

        if ticker not in current:

            trades.append({
                "ticker": ticker,
                "action": "전량매도 🔴",
                "shares": f"-{prev_shares:,} 주",
                "change": "-100%"
            })

        else:

            cur_shares = current[ticker]

            diff = prev_shares - cur_shares

            if diff > 0:

                pct = (diff / prev_shares) * 100

                trades.append({
                    "ticker": ticker,
                    "action": "매도 🔴",
                    "shares": f"-{diff:,} 주",
                    "change": f"-{pct:.1f}%"
                })

    return trades

# =========================================================
# 📌 Discord 전송
# =========================================================
def send_to_discord(name, filing_date, trades):

    buy_text = ""
    sell_text = ""
    new_text = ""

    for t in trades[:12]:

        line = (
            f"` {t['ticker']:<10} ` "
            f"｜ **{t['shares']}** "
            f"`({t['change']})`\n"
        )

        if "신규" in t["action"]:
            new_text += f"✨ {line}"

        elif "매수" in t["action"]:
            buy_text += f"📈 {line}"

        else:
            sell_text += f"📉 {line}"

    if not buy_text:
        buy_text = "❌ 주요 매수 없음"

    if not sell_text:
        sell_text = "❌ 주요 매도 없음"

    if not new_text:
        new_text = "❌ 신규 진입 없음"

    payload = {
        "embeds": [
            {
                "title": f"🏛️ {name}",
                "description": (
                    f"📅 공시일: {filing_date}\n"
                    f"────────────────────────"
                ),
                "color": 3447003,
                "fields": [
                    {
                        "name": "🟢 매수 증가",
                        "value": buy_text,
                        "inline": False
                    },
                    {
                        "name": "🔴 매도 감소",
                        "value": sell_text,
                        "inline": False
                    },
                    {
                        "name": "🔥 신규 진입",
                        "value": new_text,
                        "inline": False
                    }
                ]
            }
        ]
    }

    requests.post(DISCORD_URL, json=payload)

# =========================================================
# 📌 메인 실행
# =========================================================
def run():

    for name, cik in gurus.items():

        try:

            url = (
                f"https://data.sec.gov/submissions/"
                f"CIK{cik.zfill(10)}.json"
            )

            res = requests.get(url, headers=HEADERS, timeout=10)

            data = res.json()

            recent = data["filings"]["recent"]

            idx = [
                i for i, form in enumerate(recent["form"])
                if form == "13F-HR"
            ]

            if len(idx) < 2:
                continue

            latest = idx[0]
            prev = idx[1]

            latest_acc = recent["accessionNumber"][latest]
            prev_acc = recent["accessionNumber"][prev]

            filing_date = recent["filingDate"][latest]

            current_holdings = get_holdings_from_sec(
                cik,
                latest_acc
            )

            previous_holdings = get_holdings_from_sec(
                cik,
                prev_acc
            )

            trades = compare_holdings(
                current_holdings,
                previous_holdings
            )

            # 변화량 큰 순 정렬
            trades = sorted(
                trades,
                key=lambda x: abs(
                    float(
                        x["change"]
                        .replace("%", "")
                        .replace("+", "")
                        .replace("NEW", "999")
                    )
                ),
                reverse=True
            )

            send_to_discord(
                name,
                filing_date,
                trades
            )

            print(f"{name} 완료")

        except Exception as e:
            print(f"{name} 실패: {e}")

# =========================================================
# 📌 실행
# =========================================================
if __name__ == "__main__":
    run()
