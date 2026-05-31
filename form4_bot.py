import os, json, requests
import xml.etree.ElementTree as ET

WEBHOOK_URL = os.environ.get("SEC_FORM4_WEBHOOK_URL")
HEADERS = {"User-Agent": "your_email@example.com"}
STATE_FILE = "state_form4.json"

TARGET_COMPANIES = {
    "애플 (AAPL)": "0000320193",
    "테슬라 (TSLA)": "0001318605",
    "엔비디아 (NVDA)": "0001045810"
}

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f: return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, "w") as f: json.dump(state, f)

def send_discord(embed):
    if WEBHOOK_URL: requests.post(WEBHOOK_URL, json={"embeds": [embed]})

def run():
    state = load_state()

    for name, cik in TARGET_COMPANIES.items():
        url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
        res = requests.get(url, headers=HEADERS)
        if res.status_code != 200: continue
        
        recent = res.json().get("filings", {}).get("recent", {})
        for idx, form in enumerate(recent.get("form", [])):
            if form == "4":
                accession = recent["accessionNumber"][idx]
                if state.get(cik) == accession: break
                
                acc_clean = accession.replace("-", "")
                doc_name = recent["primaryDocument"][idx]
                xml_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{doc_name}"
                
                try:
                    xml_res = requests.get(xml_url, headers=HEADERS)
                    root = ET.fromstring(xml_res.content)
                    
                    owner_name = root.findtext(".//rptOwnerName") or "Unknown"
                    is_ceo = root.findtext(".//isOfficer") == "1"
                    title = root.findtext(".//officerTitle") or "내부자"
                    
                    total_buy = 0
                    total_shares = 0
                    for trans in root.findall(".//nonDerivativeTransaction"):
                        if trans.findtext(".//transactionCode") == "P": # 장내 순매수 필터!
                            shares = float(trans.findtext(".//transactionShares/value") or 0)
                            price = float(trans.findtext(".//transactionPricePerShare/value") or 0)
                            total_buy += (shares * price)
                            total_shares += shares

                    # 필터 조건: 매수 금액 10만 달러 이상
                    if total_buy >= 100000:
                        link = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{accession}-index.htm"
                        embed = {
                            "title": "👔 내부자 거래: 강력 순매수 🔥",
                            "color": 3066993,
                            "fields": [
                                {"name": "기업", "value": name, "inline": True},
                                {"name": "보고자", "value": f"{owner_name} ({title})", "inline": True},
                                {"name": "매수 금액", "value": f"${total_buy:,.0f}", "inline": False},
                                {"name": "매수 수량", "value": f"{total_shares:,.0f}주", "inline": True},
                                {"name": "상세보기", "value": f"[링크]({link})", "inline": False}
                            ]
                        }
                        send_discord(embed)
                        
                except Exception as e:
                    print(f"Error parsing XML: {e}")
                
                state[cik] = accession
                break # 최신 1개만 처리

    save_state(state)

if __name__ == "__main__":
    run()
