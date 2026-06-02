import os
import json
import time
import requests
import feedparser
import xml.etree.ElementTree as ET

WEBHOOK_URL = os.environ.get("SEC_FORM4_WEBHOOK_URL")

# 주의: 아래 이메일 주소를 반드시 본인의 실제 이메일로 수정하세요.
HEADERS = {
    "User-Agent": "Form4Scanner/1.0 (ilman2tv@gmail.com)"
}

STATE_FILE = "state_form4.json"
FORM4_FEED = (
    "https://www.sec.gov/cgi-bin/browse-edgar"
    "?action=getcurrent&type=4&count=100&output=atom"
)

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"processed": []}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def is_target_role(root):
    if root.findtext(".//isDirector") == "1":
        return True, "Director"

    title = root.findtext(".//officerTitle")
    if title:
        t = title.upper()
        if "CEO" in t or "CHIEF EXECUTIVE" in t:
            return True, "CEO"
        if "CFO" in t or "CHIEF FINANCIAL" in t:
            return True, "CFO"
        if "CHAIRMAN" in t:
            return True, "Chairman"
        if "FOUNDER" in t:
            return True, "Founder"
        if "PRESIDENT" in t:
            return True, "President"

    return False, "Other"

def send_discord(ticker, role_name, krw_text, increase_pct, filing_url):
    embed = {
        "title": f"💰 {role_name} 자사주 매수",
        "color": 3066993,
        "description": (
            f"**종목:** {ticker}\n\n"
            f"**매수금액:**\n약 {krw_text}\n\n"
            f"**보유량 증가:**\n+{increase_pct:.1f}%\n\n"
            f"[SEC 원문 확인]({filing_url})"
        )
    }

    if WEBHOOK_URL:
        requests.post(
            WEBHOOK_URL,
            json={"embeds": [embed]},
            timeout=30
        )

def run():
    state = load_state()
    processed = set(state.get("processed", []))
    feed = feedparser.parse(FORM4_FEED)

    for entry in feed.entries:
        accession = entry.id.split("=")[-1]

        if accession in processed:
            continue

        filing_url = entry.link
        print("Processing:", accession)

        try:
            filing_page = requests.get(
                filing_url,
                headers=HEADERS,
                timeout=30
            )

            if filing_page.status_code != 200:
                continue

            xml_url = None
            for line in filing_page.text.split('"'):
                if line.endswith(".xml"):
                    if "Archives" in line:
                        xml_url = "https://www.sec.gov" + line
                        break

            if not xml_url:
                processed.add(accession)
                continue
            
            # SEC 서버 과부하 방지 및 IP 차단 예방
            time.sleep(0.2)

            xml_res = requests.get(
                xml_url,
                headers=HEADERS,
                timeout=30
            )

            if xml_res.status_code != 200:
                continue

            root = ET.fromstring(xml_res.content)
            issuer = root.findtext(".//issuerTradingSymbol")

            if not issuer:
                issuer = "UNKNOWN"

            is_target, role_name = is_target_role(root)

            if not is_target:
                processed.add(accession)
                continue

            total_buy_usd = 0
            total_shares_bought = 0
            post_transaction_shares = 0

            for trans in root.findall(".//nonDerivativeTransaction"):
                t_code = trans.findtext(".//transactionCode")

                if t_code != "P":
                    continue

                shares = float(trans.findtext(".//transactionShares/value") or 0)
                price = float(trans.findtext(".//transactionPricePerShare/value") or 0)

                total_buy_usd += shares * price
                total_shares_bought += shares

                post_val = trans.findtext(
                    ".//postTransactionAmounts/sharesOwnedFollowingTransaction/value"
                )

                if post_val:
                    post_transaction_shares = float(post_val)

            if total_shares_bought == 0:
                processed.add(accession)
                continue

            increase_pct = 0
            if post_transaction_shares > total_shares_bought:
                prev_shares = post_transaction_shares - total_shares_bought
                increase_pct = (total_shares_bought / prev_shares) * 100
            elif post_transaction_shares == total_shares_bought:
                increase_pct = 100

            krw_amount = total_buy_usd * 1350

            if krw_amount >= 300_000_000 or increase_pct >= 10:
                eok = int(krw_amount // 100_000_000)
                cheon = int((krw_amount % 100_000_000) // 10_000_000)

                if eok == 0:
                    krw_text = f"{int(krw_amount/10000)}만 원"
                else:
                    krw_text = f"{eok}억 {cheon}천만 원"

                send_discord(issuer, role_name, krw_text, increase_pct, filing_url)

            processed.add(accession)

        except Exception as e:
            print("ERROR:", accession, e)

    state["processed"] = list(processed)[-2000:]
    save_state(state)

if __name__ == "__main__":
    run()
