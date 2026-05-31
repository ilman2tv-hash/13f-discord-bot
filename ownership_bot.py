import os, json, requests

WEBHOOK_URL = os.environ.get("SEC_OWNERSHIP_WEBHOOK_URL")
HEADERS = {"User-Agent": "your_email@example.com"}
STATE_FILE = "state_ownership.json"

TARGET_COMPANIES = {
    "애플 (AAPL)": "0000320193",
    "테슬라 (TSLA)": "0001318605",
    "팔란티어 (PLTR)": "0001321655"
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
    target_forms = ["SC 13D", "SC 13G", "8-K"]

    for name, cik in TARGET_COMPANIES.items():
        url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
        res = requests.get(url, headers=HEADERS)
        if res.status_code != 200: continue
        
        recent = res.json().get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accessions = recent.get("accessionNumber", [])
        dates = recent.get("filingDate", [])

        for idx, form in enumerate(forms):
            if form in target_forms:
                accession = accessions[idx]
                
                if state.get(cik, {}).get(form) == accession:
                    continue # 이미 알림 보낸 공시

                acc_clean = accession.replace("-", "")
                link = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{accession}-index.htm"

                embed = {
                    "title": f"🚨 [{form}] 주요 이벤트 감지",
                    "description": f"**기업:** {name}",
                    "color": 16711680 if form == "8-K" else 15105570,
                    "fields": [
                        {"name": "공시일", "value": dates[idx], "inline": True},
                        {"name": "원문 링크", "value": f"[SEC 원문 보기]({link})", "inline": False}
                    ]
                }
                send_discord(embed)

                if cik not in state: state[cik] = {}
                state[cik][form] = accession
                break # 최신 1개만 처리

    save_state(state)

if __name__ == "__main__":
    run()
