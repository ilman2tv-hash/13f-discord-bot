import os
import requests
import xml.etree.ElementTree as ET

# =========================
# 설정
# =========================

DISCORD_URL = os.environ.get("SEC_13F_WEBHOOK_URL")

HEADERS = {
    "User-Agent": "your_email@example.com"
}

EXCHANGE_RATE = 1350
TOP_N = 7

# =========================
# 유틸
# =========================

def format_krw(usd_value_k):
    """
    SEC 13F value (천 달러 단위)를 KRW로 변환
    """

    try:
        usd_value_k = int(usd_value_k or 0)
    except:
        return "0원"

    krw = usd_value_k * 1000 * EXCHANGE_RATE

    if krw >= 1_000_000_000_000:
        cho = krw // 1_000_000_000_000
        eok = (krw % 1_000_000_000_000) // 100_000_000

        if eok > 0:
            return f"{cho}조 {eok}억"

        return f"{cho}조"

    eok = krw // 100_000_000
    return f"{eok}억"


def safe_int(value, default=0):
    try:
        return int(float(value))
    except:
        return default


def safe_text(elem):
    try:
        return elem.text.strip()
    except:
        return ""


# =========================
# 티커 조회
# =========================

def get_ticker_from_cusip(cusip):

    if not cusip:
        return None

    try:
        url = f"https://query1.finance.yahoo.com/v1/finance/search?q={cusip}"

        res = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10
        )

        if res.status_code != 200:
            return None

        data = res.json()

        quotes = data.get("quotes", [])

        if not quotes:
            return None

        return quotes[0].get("symbol")

    except Exception as e:
        print(f"CUSIP 조회 실패: {cusip} / {e}")
        return None


# =========================
# SEC XML 파싱
# =========================

def get_holdings_from_sec(cik, accession_num):

    holdings = {}

    try:

        acc_clean = accession_num.replace("-", "")

        folder_url = (
            f"https://www.sec.gov/Archives/edgar/data/"
            f"{int(cik)}/{acc_clean}/index.json"
        )

        folder_res = requests.get(
            folder_url,
            headers=HEADERS,
            timeout=15
        )

        folder_res.raise_for_status()

        files = (
            folder_res.json()
            .get("directory", {})
            .get("item", [])
        )

        xml_file = next(
            (
                f.get("name", "")
                for f in files
                if (
                    f.get("name", "").endswith(".xml")
                    and "table" in f.get("name", "").lower()
                )
            ),
            None
        )

        if not xml_file:
            print(f"XML 파일 없음: {cik}")
            return holdings

        xml_url = (
            f"https://www.sec.gov/Archives/edgar/data/"
            f"{int(cik)}/{acc_clean}/{xml_file}"
        )

        xml_res = requests.get(
            xml_url,
            headers=HEADERS,
            timeout=15
        )

        xml_res.raise_for_status()

        root = ET.fromstring(xml_res.content)

        ns = (
            {"ns": root.tag.split("}")[0].strip("{")}
            if "}" in root.tag
            else None
        )

        info_tables = (
            root.findall(".//ns:infoTable", ns)
            if ns
            else root.findall(".//infoTable")
        )

        for info in info_tables:

            try:

                if ns:
                    issuer = safe_text(
                        info.find(".//ns:nameOfIssuer", ns)
                    )

                    cusip = safe_text(
                        info.find(".//ns:cusip", ns)
                    )

                    value = safe_text(
                        info.find(".//ns:value", ns)
                    )

                    shares = safe_text(
                        info.find(".//ns:sshPrnamt", ns)
                    )

                else:
                    issuer = safe_text(
                        info.find(".//nameOfIssuer")
                    )

                    cusip = safe_text(
                        info.find(".//cusip")
                    )

                    value = safe_text(
                        info.find(".//value")
                    )

                    shares = safe_text(
                        info.find(".//sshPrnamt")
                    )

                if not issuer:
                    continue

                value = safe_int(value)
                shares = safe_int(shares)

                ticker = (
                    get_ticker_from_cusip(cusip)
                    or issuer[:12]
                )

                holdings[ticker] = {
                    "issuer": issuer,
                    "shares": shares,
                    "value": value
                }

            except Exception as e:
                print(f"종목 파싱 실패: {e}")
                continue

    except Exception as e:
        print(f"SEC 보유종목 수집 실패: {cik} / {e}")

    return holdings


# =========================
# 디스코드 전송
# =========================

def send_to_discord(guru_name, filing_date, trades):

    if not DISCORD_URL:
        print("디스코드 웹훅 없음")
        return

    if not trades:
        print(f"{guru_name} 변동 없음")
        return

    sections = {
        "신규진입 🔥": [],
        "비중확대 🟢": [],
        "비중축소 🔴": [],
        "전량매도 ❌": []
    }

    for t in trades:

        line = (
            f"`{t['ticker']}` ｜ "
            f"{t['share_text']} ｜ "
            f"약 {t['amount_kr']}"
        )

        sections[t["action"]].append(line)

    fields = []

    for title, lines in sections.items():

        if not lines:
            continue

        fields.append({
            "name": title,
            "value": "\n".join(lines),
            "inline": False
        })

    payload = {
        "embeds": [
            {
                "title": f"🏛️ {guru_name} 포트폴리오 변동",
                "description": (
                    f"📅 SEC 13F 공시일: {filing_date}"
                ),
                "color": 15158332,
                "fields": fields,
                "footer": {
                    "text": (
                        f"상위 {TOP_N}개 변동 기준 ｜ "
                        f"환율 {EXCHANGE_RATE:,}원"
                    )
                }
            }
        ]
    }

    try:

        res = requests.post(
            DISCORD_URL,
            json=payload,
            timeout=10
        )

        res.raise_for_status()

        print(f"디스코드 전송 완료: {guru_name}")

    except Exception as e:
        print(f"디스코드 전송 실패: {e}")


# =========================
# 메인 로직
# =========================

def get_13f_data():

    gurus = {
        "워런 버핏 (버크셔)": "0001067983",
        "레이 달리오 (Bridgewater)": "0001350694",
        "스탠리 드러켄밀러": "0001536411",
        "데이비드 테퍼": "0000905567",
        "Coatue Management": "0001135730",
        "Tiger Global": "0001167483"
    }

    for guru_name, cik in gurus.items():

        print(f"\n🔄 수집 중: {guru_name}")

        try:

            url = (
                f"https://data.sec.gov/submissions/"
                f"CIK{cik.zfill(10)}.json"
            )

            res = requests.get(
                url,
                headers=HEADERS,
                timeout=15
            )

            res.raise_for_status()

            data = res.json()

            recent = (
                data.get("filings", {})
                .get("recent", {})
            )

            forms = recent.get("form", [])
            accession_numbers = recent.get("accessionNumber", [])
            filing_dates = recent.get("filingDate", [])

            filing_indexes = [
                i for i, form in enumerate(forms)
                if form == "13F-HR"
            ]

            if len(filing_indexes) < 2:
                print("13F-HR 부족")
                continue

            current_idx = filing_indexes[0]
            previous_idx = filing_indexes[1]

            current_holdings = get_holdings_from_sec(
                cik,
                accession_numbers[current_idx]
            )

            previous_holdings = get_holdings_from_sec(
                cik,
                accession_numbers[previous_idx]
            )

            if not current_holdings:
                print("현재 보유종목 없음")
                continue

            trades = []

            all_tickers = (
                set(current_holdings.keys())
                | set(previous_holdings.keys())
            )

            for ticker in all_tickers:

                cur = current_holdings.get(
                    ticker,
                    {"shares": 0, "value": 0}
                )

                pre = previous_holdings.get(
                    ticker,
                    {"shares": 0, "value": 0}
                )

                share_diff = cur["shares"] - pre["shares"]

                value_diff = cur["value"] - pre["value"]

                if share_diff == 0:
                    continue

                if pre["shares"] == 0 and cur["shares"] > 0:
                    action = "신규진입 🔥"

                elif cur["shares"] == 0:
                    action = "전량매도 ❌"

                elif share_diff > 0:
                    action = "비중확대 🟢"

                else:
                    action = "비중축소 🔴"

                if share_diff > 0:
                    share_text = f"+{share_diff:,}주"
                else:
                    share_text = f"{share_diff:,}주"

                trades.append({
                    "ticker": ticker,
                    "action": action,
                    "share_text": share_text,
                    "amount_kr": format_krw(abs(value_diff)),
                    "sort_key": abs(value_diff)
                })

            trades = sorted(
                trades,
                key=lambda x: x["sort_key"],
                reverse=True
            )[:TOP_N]

            send_to_discord(
                guru_name,
                filing_dates[current_idx],
                trades
            )

        except Exception as e:
            print(f"{guru_name} 처리 실패: {e}")


# =========================
# 실행
# =========================

if __name__ == "__main__":

    try:
        get_13f_data()

    except Exception as e:
        print(f"전체 실행 실패: {e}")
