import os, json, requests
import xml.etree.ElementTree as ET

WEBHOOK_URL = os.environ.get("SEC_FORM4_WEBHOOK_URL")
HEADERS = {"User-Agent": "ilman2tv@gmail.com"}
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

def run():
    state = load_state()

    for name, cik in TARGET_COMPANIES.items():
        res = requests.get(f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json", headers=HEADERS)
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
                    title = root.findtext(".//officerTitle") or "내부자/임원"
                    
                    total_amount = 0
                    total_shares = 0
                    action_type = ""
                    
                    for trans in root.findall(".//nonDerivativeTransaction"):
                        t_code = trans.findtext(".//transactionCode")
                        if t_code in ["P", "S"]: # P: 장내매수, S: 장내매도
                            shares = float(trans.findtext(".//transactionShares/value") or 0)
                            price = float(trans.findtext(".//transactionPricePerShare/value") or 0)
                            total_amount += (shares * price)
                            total_shares += shares
                            action_type = "순매수 🔥" if t_code == "P" else "순매도 📉"

                    # 10만 달러(약 1.3억) 이상일 경우에만 알림
                    if total_amount >= 100000:
                        link = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{accession}-index.htm"
                        embed = {
                            "title": f"👔 내부자 거래: 강력 {action_type}",
                            "color": 3066993 if "매수" in action_type else 15158332, # 매수 초록, 매도 빨강
                            "fields": [
                                {"name": "기업", "value": name, "inline": True},
                                {"name": "보고자", "value": f"{owner_name} ({title})", "inline": True},
                                {"name": f"총 {action_type[:3]} 금액", "value": f"${total_amount:,.0f} (약 {int((total_amount*1350)/100000000)}억)", "inline": False},
                                {"name": "수량", "value": f"{total_shares:,.0f}주", "inline": True},
                                {"name": "상세보기", "value": f"[링크]({link})", "inline": False}
                            ]
                        }
                        if WEBHOOK_URL: requests.post(WEBHOOK_URL, json={"embeds": [embed]})
                        
                except Exception as e:
                    print(f"Form4 에러: {e}")
                
                state[cik] = accession
                break

    save_state(state)

if __name__ == "__main__":
    run()
