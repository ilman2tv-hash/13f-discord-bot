import os
import time
import logging
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from collections import defaultdict
import tenacity

# ====================== 설정 ======================
DISCORD_URL = os.environ.get('SEC_13F_WEBHOOK_URL')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

ticker_cache = {}

# ====================== Helper Functions ======================
@tenacity.retry(wait=tenacity.wait_exponential(min=1, max=10), stop=tenacity.stop_after_attempt(4), reraise=True)
def requests_get(url, **kwargs):
    headers = kwargs.pop('headers', {})
    headers.setdefault('User-Agent', 'jungseunghun ilman2tv@gmail.com')
    return requests.get(url, headers=headers, timeout=15, **kwargs)

def get_ticker_from_cusip(cusip: str) -> str | None:
    if not cusip or len(cusip) < 6:
        return None
    if cusip in ticker_cache:
        return ticker_cache[cusip]

    try:
        url = f"https://query1.finance.yahoo.com/v1/finance/search?q={cusip}"
        res = requests_get(url)
        if res.status_code == 200:
            quotes = res.json().get('quotes', [])
            if quotes:
                ticker = quotes[0].get('symbol')
                ticker_cache[cusip] = ticker
                return ticker
    except:
        pass
    ticker_cache[cusip] = None
    return None

def convert_corporate_name(raw_name: str) -> str:
    name_map = {
        "APPLE INC": "AAPL", "NVIDIA CORP": "NVDA", "MICROSOFT CORP": "MSFT",
        "AMAZON COM INC": "AMZN", "ALPHABET INC": "GOOGL", "META PLATFORMS": "META",
        "BERKSHIRE HATHAWAY": "BRK.B",
    }
    upper = raw_name.upper().strip()
    for key, ticker in name_map.items():
        if key in upper:
            return ticker
    return ''.join([c for c in upper.split()[0] if c.isalnum()])[:12]

# ====================== 13F 파싱 ======================
def get_holdings_from_sec(cik: str, accession_num: str):
    acc_clean = accession_num.replace('-', '')
    holdings = defaultdict(lambda: {"shares": 0, "value": 0})

    try:
        folder_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/index.json"
        res = requests_get(folder_url)
        files = res.json().get('directory', {}).get('item', [])

        xml_file = next((f['name'] for f in files if f['name'].endswith('.xml') and 'infotable' in f['name'].lower()), None)
        if not xml_file:
            xml_file = next((f['name'] for f in files if f['name'].endswith('.xml')), None)
        if not xml_file:
            return {}

        xml_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{xml_file}"
        xml_res = requests_get(xml_url)
        root = ET.fromstring(xml_res.content)

        # ✅ 수정된 부분
        ns = {'ns': root.tag.split('}')[0].strip('{')}} if '}' in root.tag else {}

        info_tables = (root.findall('.//ns:infoTable', ns) or 
                      root.findall('.//infoTable') or 
                      root.findall('.//{*}infoTable'))

        for info in info_tables:
            def safe_text(tag):
                for path in [f'.//ns:{tag}', f'.//{tag}', f'.//{{*}}{tag}']:
                    elem = info.find(path, ns)
                    if elem is not None and elem.text:
                        return elem.text.strip()
                return None

            issuer = safe_text('nameOfIssuer')
            cusip = safe_text('cusip')
            shares = safe_text('sshPrnamt') or safe_text('ssh_prn_amt')
            value = safe_text('value')

            if issuer and shares:
                try:
                    shares_int = int(shares)
                    value_int = int(value) if value else 0
                    ticker = get_ticker_from_cusip(cusip) or convert_corporate_name(issuer)
                    if ticker:
                        holdings[ticker]["shares"] += shares_int
                        holdings[ticker]["value"] += value_int
                except:
                    continue
    except Exception as e:
        logging.error(f"파싱 오류 ({cik}): {e}")

    return holdings

# ====================== 한국식 금액 ======================
def format_korean_value(value_thousands: int) -> str:
    if not value_thousands or value_thousands <= 0:
        return "-"
    dollars = value_thousands * 1000
    if dollars >= 1_000_000_000_000:
        return f"{dollars / 1_000_000_000_000:.2f}조"
    elif dollars >= 100_000_000:
        return f"{int(dollars / 100_000_000)}억"
    else:
        return f"{dollars / 1_000_000:.1f}백만"

# ====================== Discord 전송 ======================
def send_combined_discord_report(results):
    if not DISCORD_URL or not results:
        return

    latest_date = max([r['filing_date'] for r in results], default="Unknown")
    year = latest_date[:4]
    month = int(latest_date[5:7])
    quarter = {1:"1분기",2:"1분기",3:"1분기",4:"2분기",5:"2분기",6:"2분기",
               7:"3분기",8:"3분기",9:"3분기",10:"4분기",11:"4분기",12:"4분기"}.get(month, "")

    fields = []
    
    for result in results:
        guru_name = result['name']
        trades = result['trades'][:8]
        
        table = "| 티커   | 유형     | 변동내역                    | 금액      |\n"
        table += "|--------|----------|-----------------------------|-----------|\n"
        
        for t in trades:
            value_str = format_korean_value(t.get('value', 0))
            change = t['change']
            
            if "-100%" in change:
                type_str = "🔴 매도"
                change_str = "전량매도"
            elif "New" in change:
                type_str = "✨ 신규"
                change_str = "신규진입"
            elif "+" in change or "매수" in str(t.get('action', '')):
                type_str = "🟢 매수"
                change_str = change
            else:
                type_str = "🔴 매도"
                change_str = change

            line = f"| `{t['ticker']:<5}` | {type_str} | {t['shares']} ({change_str}) | **{value_str}** |\n"
            table += line

        fields.append({
            "name": f"🏛️ {guru_name}",
            "value": f"```{table}```",
            "inline": False
        })

    payload = {
        "embeds": [{
            "title": "🔔 13F 매크로 Guru 변동 알림",
            "description": f"**{year}년 {quarter}** | 공시 기간: {latest_date}",
            "color": 0x1E88E5,
            "fields": fields,
            "footer": {"text": "13F AI Parser v2.7 • 매크로 중심"},
            "timestamp": datetime.utcnow().isoformat()
        }]
    }

    try:
        res = requests.post(DISCORD_URL, json=payload, timeout=10)
        if res.status_code in (200, 204):
            logging.info("✅ 알림 전송 완료")
    except Exception as e:
        logging.error(f"Discord 전송 에러: {e}")

# ====================== 메인 ======================
def get_13f_data():
    gurus = {
        "스탠리 드러켄밀러": "0001568832",
        "데이비드 테퍼": "0000905567",
        "폴 튜더 존스": "0000923093",
        "레이 달리오 (Bridgewater)": "0001350694",
        "빌 애크먼 (Pershing Square)": "0001336528",
    }

    all_results = []

    for name, cik in gurus.items():
        logging.info(f"🔄 {name} 데이터 수집 중...")
        try:
            url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
            response = requests_get(url)
            data = response.json()

            recent = data['filings']['recent']
            f_idx = [i for i, form in enumerate(recent['form']) if form == '13F-HR']

            if not f_idx:
                continue

            latest_i = f_idx[0]
            filing_date = recent['filingDate'][latest_i]
            acc_num = recent['accessionNumber'][latest_i]

            current = get_holdings_from_sec(cik, acc_num)
            trades = []

            if len(f_idx) >= 2:
                prev_acc = recent['accessionNumber'][f_idx[1]]
                prev = get_holdings_from_sec(cik, prev_acc)

                all_tickers = set(current.keys()) | set(prev.keys())

                for ticker in all_tickers:
                    cur = current.get(ticker, {"shares": 0, "value": 0})
                    pre = prev.get(ticker, {"shares": 0, "value": 0})
                    cur_s = cur["shares"]
                    pre_s = pre["shares"]

                    if pre_s == 0 and cur_s > 0:
                        trades.append({"ticker": ticker, "shares": f"{cur_s:,} 주", "change": "New", "value": cur["value"]})
                    elif cur_s == 0 and pre_s > 0:
                        trades.append({"ticker": ticker, "shares": f"-{pre_s:,} 주", "change": "-100%", "value": pre["value"]})
                    elif cur_s > pre_s:
                        diff = cur_s - pre_s
                        pct = (diff / pre_s) * 100
                        trades.append({"ticker": ticker, "shares": f"+{diff:,} 주", "change": f"+{pct:.1f}%", "value": cur["value"]})
                    elif cur_s < pre_s:
                        diff = pre_s - cur_s
                        pct = (diff / pre_s) * 100
                        trades.append({"ticker": ticker, "shares": f"-{diff:,} 주", "change": f"-{pct:.1f}%", "value": cur["value"]})

            trades = sorted(trades, key=lambda x: abs(x.get('value', 0)), reverse=True)
            
            if trades:
                all_results.append({"name": name, "trades": trades, "filing_date": filing_date})

            time.sleep(0.8)

        except Exception as e:
            logging.error(f"{name} 처리 실패: {e}")

    send_combined_discord_report(all_results)

if __name__ == "__main__":
    get_13f_data()
