import os, json, requests

WEBHOOK_URL = os.environ.get("SEC_OWNERSHIP_WEBHOOK_URL")
HEADERS = {"User-Agent": "your_email@example.com"}
STATE_FILE = "state_ownership.json"

TARGET_COMPANIES = {
    "애플 (AAPL)": "0000320193",
    "테슬라 (TSLA)": "0001318605",
    "팔란티어 (PLTR)": "0001321655"
}

# 8-K 공시 코드 한글 번역 맵
ITEM_MAP = {
    "1.01": "중대 계약 체결", "1.02": "계약 해지", "1.03": "파산/수용",
    "2.01": "자산 취득/처분", "2.02": "실적 발표", "2.03": "재무 의무 발생",
    "3.01": "상장 폐지/요건 미달", "4.01": "회계법인 변경", "4.02": "재무제표 오류",
    "5.01": "경영권 변경", "5.02": "임원/이사 교체", "5.03": "정관 변경",
    "8.01": "기타 주요 사건", "9.01": "재무제표 및 첨부"
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
            if form in ["SC 13D", "SC 13G", "8-K"]:
                accession = recent["accessionNumber"][idx]
                if state.get(cik, {}).get(form) == accession: continue

                acc_clean = accession.replace("-", "")
                link = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{accession}-index.htm"
                
                # 8-K일 경우 내용 요약 추출
                summary = "링크를 클릭해 세부내용을 확인하세요."
                if form == "8-K" and "items" in recent and recent["items"][idx]:
                    items_str = recent["items"][idx]
                    translated = [ITEM_MAP.get(i.strip(), i.strip()) for i in items_str.split(",")]
                    summary = "📌 **핵심 요약:**\n" + "\n".join([f"• {t}" for t in translated])

                embed = {
                    "title": f"🚨 [{form}] 기업 주요 공시 감지",
                    "color": 16711680 if form == "8-K" else 15105570,
                    "fields": [
                        {"name": "기업", "value": name, "inline": True},
                        {"name": "공시일", "value": recent["filingDate"][idx], "inline": True},
                        {"name": "공시 내용", "value": summary, "inline": False},
                        {"name": "원문 링크", "value": f"[SEC 원문 바로가기]({link})", "inline": False}
                    ]
                }
                if WEBHOOK_URL: requests.post(WEBHOOK_URL, json={"embeds": [embed]})

                if cik not in state: state[cik] = {}
                state[cik][form] = accession
                break

    save_state(state)

if __name__ == "__main__":
    run()
