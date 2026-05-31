import os, json, re, requests

WEBHOOK_URL = os.environ.get("SEC_OWNERSHIP_WEBHOOK_URL")
HEADERS = {"User-Agent": "ilman2tv@gmail.com"} # 본인 이메일 입력
STATE_FILE = "state_ownership.json"
COMPANY_LIST_FILE = "monitored_companies.json"

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f: return json.load(f)
    return {}

def load_target_companies():
    if os.path.exists(COMPANY_LIST_FILE):
        with open(COMPANY_LIST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"AAPL": "0000320193"} # 13F 봇이 만든 파일이 없을 때 기본값

def extract_13dg_info(text_content):
    """13D/G 원문에서 보고자 이름과 지분율(%)을 추출하는 정규식"""
    name_match = re.search(r"(?:NAME OF REPORTING PERSON|NAME OF REPORTING PERSONS).*?\n.*?\n?.*?([A-Za-z0-9\s\,\.\&]+)", text_content, re.IGNORECASE)
    pct_match = re.search(r"(?:PERCENT OF CLASS|PERCENT OF CLASS REPRESENTED).*?\n.*?\n?.*?([0-9\.]+)\s*%", text_content, re.IGNORECASE)
    
    name = name_match.group(1).strip() if name_match else "알 수 없는 기관"
    # 이름이 너무 길게 잡히는 경우 방지
    name = name.split('\n')[0][:30].strip()
    pct = float(pct_match.group(1)) if pct_match else 0.0
    return name, pct

def run():
    state = load_state()
    targets = load_target_companies()
    target_forms = ["SC 13D", "SC 13G"]
    
    for ticker, identifier in targets.items():
        cik = str(identifier)
        if not cik.isdigit(): continue

        res = requests.get(f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json", headers=HEADERS)
        if res.status_code != 200: continue
        
        recent = res.json().get("filings", {}).get("recent", {})
        for idx, form in enumerate(recent.get("form", [])):
            if form in target_forms:
                accession = recent["accessionNumber"][idx]
                
                # 중복 알림 방지
                if state.get(cik, {}).get("last_acc") == accession: continue

                acc_clean = accession.replace("-", "")
                txt_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{accession}.txt"
                link = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{accession}-index.htm"
                
                try:
                    txt_res = requests.get(txt_url, headers=HEADERS, timeout=10)
                    reporter_name, current_pct = extract_13dg_info(txt_res.text)
                    
                    if current_pct > 0:
                        prev_pct = state.get(cik, {}).get("last_pct", 0.0)
                        
                        # 💡 핵심 조건: 신규 5% 이상 또는 기존 대비 2% 이상 증가
                        is_new_major = (prev_pct < 5.0 and current_pct >= 5.0)
                        is_significant_increase = (current_pct - prev_pct >= 2.0)
                        
                        if is_new_major or is_significant_increase:
                            title_prefix = "🔥 신규 대주주 등장" if is_new_major else "🚀 대주주 지분 대폭 확대"
                            
                            embed = {
                                "title": f"📢 [13D/G] {title_prefix}",
                                "color": 15105570 if form == "SC 13G" else 16711680,
                                "description": f"**종목:** {ticker}\n**기관:** {reporter_name}\n\n**보유비율:** {current_pct}%\n*(이전 보유율: {prev_pct}%)*",
                                "fields": [
                                    {"name": "원문 링크", "value": f"[SEC 공시 확인하기]({link})", "inline": False}
                                ]
                            }
                            if WEBHOOK_URL: requests.post(WEBHOOK_URL, json={"embeds": [embed]})
                        
                        # 상태 업데이트 (마지막 공시 번호 및 지분율 저장)
                        if cik not in state: state[cik] = {}
                        state[cik]["last_acc"] = accession
                        state[cik]["last_pct"] = current_pct
                
                except Exception as e:
                    print(f"13D/G 파싱 에러 ({ticker}): {e}")
                
                break # 해당 종목의 최신 공시 1개만 확인

    with open(STATE_FILE, "w") as f: json.dump(state, f)

if __name__ == "__main__":
    run()
