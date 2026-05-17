import os
import json
import time
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
LAST_SENT_FILE = "last_sent.json"


# =========================
# 저장 파일 관리
# =========================

def load_last_sent():
    if not os.path.exists(LAST_SENT_FILE):
        return {}

    try:
        with open(LAST_SENT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def save_last_sent(data):
    try:
        with open(LAST_SENT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"last_sent 저장 실패: {e}")


# =========================
# 유틸
# =========================

def safe_int(value):
    try:
        return int(float(value))
    except:
        return 0


def safe_text(elem):
    try:
        return elem.text.strip()
    except:
        return ""


def format_krw(usd_value_k):
    try:
        usd_value_k = int(usd_value_k or 0)
    except:
        return "0원"

    krw = usd_value_k * 1000 * EXCHANGE_RATE

    if krw >= 1_000_000_000_000:
        cho = krw // 1_000_000_000_000
        eok = (krw % 1_000_000_000_000) // 100_000_000
        return f"{cho}조 {eok}억" if eok else f"{cho}조"

    return f"{krw // 100_000_000}억"


# =========================
# 티커 조회
# 상위 7개만 조회
# =========================

def get_ticker_from_cusip(cusip):
    if not cusip:
        return None

    try:
        url = f"https://query1.finance.yahoo.com/v1/finance/search?q={cusip}"

        res = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=8
        )

        if res.status_code != 200:
            return None

        quotes = res.json().get("quotes", [])

        if not quotes:
            return None

        return quotes[0].get("symbol")

    except:
        return None


# =========================
# SEC 13F XML 파싱
# =========================

def get_holdings_from_sec(cik, accession_num):
    holdings = {}

    try:
        acc_clean = accession_num.replace("-", "")

        folder_url = (
            f"https://www.sec.gov/Archives/edgar/data/"
            f"{int(cik)}/{acc_clean}/index.json"
        )

        res = requests.get(
            folder_url,
            headers=HEADERS,
            timeout=15
        )

        res.raise_for_status()

        files = (
            res.json()
            .get("directory", {})
            .get("item", [])
        )

        xml_file = next(
            (
                f.get("name", "")
                for f in files
                if (
                    f.get("name", "").lower().endswith(".xml")
                    and "table" in f.get("name", "").lower()
                )
            ),
            None
        )

        if not xml_file:
            print(f"XML 없음: {cik}")
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
                    issuer = safe_text(info.find(".//ns:nameOfIssuer", ns))
                    cusip = safe_text(info.find(".//ns:cusip", ns))
                    value = safe_text(info.find(".//ns:value", ns))
                    shares = safe_text(info.find(".//ns:sshPrnamt", ns))
                else:
                    issuer = safe_text(info.find(".//nameOfIssuer"))
                    cusip = safe_text(info.find(".//cusip"))
                    value = safe_text(info.find(".//value"))
                    shares = safe_text(info.find(".//sshPrnamt"))

                if not issuer or not cusip:
                    continue

                holdings[cusip] = {
                    "issuer": issuer,
                    "cusip": cusip,
                    "shares": safe_int(shares),
                    "value": safe_int(value)
                }

            except Exception as e:
                print(f"종목 파싱 실패: {e}")

    except Exception as e:
        print(f"SEC 수집 실패: {cik} / {e}")

    return holdings


# =========================
# 디스코드 전송
# =========================

def send_to_discord(guru_name, filing_date, portfolio):
    if not DISCORD_URL:
        print("디스코드 웹훅 없음")
        return False

    if not portfolio:
        print(f"{guru_name}: 전송할 포트폴리오 없음")
        return False

    lines = []

    for p in portfolio:
        line = (
            f"`{p['display_name']}` ｜ "
            f"{p['status']} ｜ "
            f"약 {p['amount_kr']}"
        )
        lines.append(line)

    payload = {
        "embeds": [
            {
                "title": f"🏛️ {guru_name} TOP {TOP_N} 포트폴리오",
                "description": (
                    f"📅 SEC 13F 공시일: {filing_date}\n\n"
                    + "\n".join(lines)
                ),
                "color": 15158332,
                "footer": {
                    "text": (
                        f"현재 보유 비중 기준 TOP {TOP_N} ｜ "
                        f"새 공시일 때만 알림 ｜ "
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
        return True

    except Exception as e:
        print(f"디스코드 전송 실패: {guru_name} / {e}")
        return False


# =========================
# 메인
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

    last_sent = load_last_sent()

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

            recent = (
                res.json()
                .get("filings", {})
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
                print(f"{guru_name}: 13F 부족")
                continue

            current_idx = filing_indexes[0]
            previous_idx = filing_indexes[1]

            current_accession = accession_numbers[current_idx]

            # 이미 보낸 공시면 건너뜀
            if last_sent.get(cik) == current_accession:
                print(f"{guru_name}: 새 공시 없음, 알림 생략")
                continue

            current_holdings = get_holdings_from_sec(
                cik,
                current_accession
            )

            previous_holdings = get_holdings_from_sec(
                cik,
                accession_numbers[previous_idx]
            )

            if not current_holdings:
                print(f"{guru_name}: 현재 보유 없음")
                continue

            portfolio = []

            for cusip, cur in current_holdings.items():
                pre = previous_holdings.get(
                    cusip,
                    {
                        "shares": 0,
                        "value": 0
                    }
                )

                cur_shares = cur["shares"]
                pre_shares = pre["shares"]

                if pre_shares == 0 and cur_shares > 0:
                    status = "신규진입 🔥"
                elif cur_shares > pre_shares:
                    status = "비중확대 🟢"
                elif cur_shares < pre_shares:
                    status = "비중축소 🔴"
                else:
                    status = "유지 ➖"

                portfolio.append({
                    "issuer": cur["issuer"],
                    "cusip": cusip,
                    "status": status,
                    "value": cur["value"],
                    "amount_kr": format_krw(cur["value"])
                })

            portfolio = sorted(
                portfolio,
                key=lambda x: x["value"],
                reverse=True
            )[:TOP_N]

            for p in portfolio:
                ticker = get_ticker_from_cusip(p["cusip"])

                if ticker:
                    p["display_name"] = ticker
                else:
                    p["display_name"] = p["issuer"][:18]

                time.sleep(0.2)

            sent = send_to_discord(
                guru_name,
                filing_dates[current_idx],
                portfolio
            )

            # 디스코드 전송 성공했을 때만 저장
            if sent:
                last_sent[cik] = current_accession
                save_last_sent(last_sent)

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
