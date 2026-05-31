import os, json, time, requests
from collections import defaultdict
import xml.etree.ElementTree as ET

WEBHOOK_URL = os.environ.get("SEC_13F_WEBHOOK_URL")
HEADERS = {"User-Agent": "ilman2tv@gmail.com"} # ⚠️ 본인 이메일로 반드시 변경
STATE_FILE = "state_13f.json"
COMPANY_LIST_FILE = "monitored_companies.json"
EXCHANGE_RATE = 1350
TOP_N = 10

IS_MANUAL_RUN = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"

GURUS = {
    "워런 버핏 (Berkshire)": "0001067983",
    "스탠리 드러켄밀러 (Duquesne)": "0001536411",
    "데이비드 테퍼 (Appaloosa)": "0000905567",
    "빌 애크먼 (Pershing Square)": "0001336528",
    "레이 달리오 (Bridgewater)": "0001350694"
}

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f: return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, "w") as f: json.dump(state, f)

def safe_int(val):
    try: return int(float(val))
    except: return 0

def format_krw(usd):
    krw = safe_int(usd) * EXCHANGE_RATE
    if krw >= 1_000_000_000_000:
        return f"{krw // 1_000_000_000_000}조 {(krw % 1_000_000_000_000) // 100_000_000}억"
    return f"{krw // 100_000_000}억"

def get_ticker_and_cik_from_cusip(cusip):
    try:
        res = requests.get(f"https://query1.finance.yahoo.com/v1/finance/search?q={cusip}", headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        if res.status_code == 200 and res.json().get("quotes"):
            return res.json()["quotes"][0].get("symbol")
    except: pass
    return None

def get_holdings(cik, acc_num):
    holdings = {}
    try:
        acc_clean = acc_num.replace("-", "")
        res = requests.get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/index.json", headers=HEADERS)
        if res.status_code != 200: return holdings
        
        files = res.json().get("directory", {}).get("item", [])
        
        # 💡 [핵심수정] 파일명이 달라도 강제로 표(infoTable) XML 찾아내기
        xml_files = [f["name"] for f in files if f["name"].endswith(".xml")]
        xml_file = next((x for x in xml_files if "table" in x.lower() or "info" in x.lower()), None)
        if not xml_file and xml_files:
            xml_file = max(xml_files, key=lambda f: next((item["size"] for item in files if item["name"] == f), 0))
            
        if not xml_file: return holdings

        xml_res = requests.get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{xml_file}", headers=HEADERS)
        root = ET.fromstring(xml_res.content)
        
        # 💡 [핵심수정] 펀드마다 다른 양식(네임스페이스)을 씹어먹는 우회 탐색 로직
        for info in root.iter():
            if 'infoTable' in info.tag:
                issuer = next((c.text for c in info if 'nameOfIssuer' in c.tag), "")
                cusip = next((c.text for c in info if 'cusip' in c.tag), "")
                
                val_elem = next((c for c in info if 'value' in c.tag), None)
                val = val_elem.text if val_elem is not None else "0"
                
                shares_elem = next((c for c in info.iter() if 'sshPrnamt' in c.tag), None)
                shares = shares_elem.text if shares_elem is not None else "0"
                
                if cusip and issuer:
                    holdings[cusip] = {"issuer": issuer.strip(), "cusip": cusip.strip(), "value": safe_int(val), "shares": safe_int(shares)}
    except: pass
    return holdings

def process_13f():
    state = load_state()
    guru_filings = []

    for name, cik in GURUS.items():
        time.sleep(1) 
        res = requests.get(f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json", headers=HEADERS)
        if res.status_code != 200: continue
        
        recent = res.json().get("filings", {}).get("recent", {})
        idx_13f = [i for i, f in enumerate(recent.get("form", [])) if f == "13F-HR"]
        if len(idx_13f) < 2: continue

        cur_acc = recent["accessionNumber"][idx_13f[0]]
        pre_acc = recent["accessionNumber"][idx_13f[1]]
        date = recent["filingDate"][idx_13f[0]]
        
        report_dates = recent.get("reportDate", [])
        report_date = report_dates[idx_13f[0]] if report_dates else date[:7]

        guru_filings.append({
            "name": name, "cik": cik, "cur_acc": cur_acc, "pre_acc": pre_acc,
            "date": date, "report_date": report_date
        })

    if not guru_filings: return

    latest_report_date = max(f["report_date"] for f in guru_filings)
    current_season_filings = [f for f in guru_filings if f["report_date"] == latest_report_date]
    any_new = any(state.get(f["cik"]) != f["cur_acc"] for f in current_season_filings)
    
    if not any_new and not IS_MANUAL_RUN: return 

    all_portfolios = {}
    discovered_companies = {}

    for filing in current_season_filings:
        cik, name, cur_acc, pre_acc, date = filing["cik"], filing["name"], filing["cur_acc"], filing["pre_acc"], filing["date"]
        
        cur_holdings = get_holdings(cik, cur_acc)
        pre_holdings = get_holdings(cik, pre_acc)
        
        portfolio = []
        for cusip, cur in cur_holdings.items():
            pre_shares = pre_holdings.get(cusip, {}).get("shares", 0)
            cur_shares = cur["shares"]
            
            if pre_shares == 0: status = "신규진입 🔥"
            elif cur_shares > pre_shares: status = "비중확대 🟢"
            elif cur_shares < pre_shares: status = "비중축소 🔴"
            else: status = "유지 ➖"
            
            portfolio.append({
                "issuer": cur["issuer"], "cusip": cusip, "status": status, 
                "value": cur["value"], "krw": format_krw(cur["value"])
            })

        portfolio = sorted(portfolio, key=lambda x: x["value"], reverse=True)[:TOP_N]
        for p in portfolio:
            p["ticker"] = get_ticker_and_cik_from_cusip(p["cusip"]) or p["issuer"][:10]
            if p["status"] in ["신규진입 🔥", "비중확대 🟢"]:
                discovered_companies[p["ticker"]] = p["cusip"]
            time.sleep(0.5)

        if portfolio:
            all_portfolios[name] = portfolio

        # 💡 [핵심수정] 데이터(portfolio)가 텅 비었을 때는 절대 보내지 않도록 방어 로직 복구
        if (state.get(cik) != cur_acc or IS_MANUAL_RUN) and portfolio:
            fields = []
            for status_type in ["신규진입 🔥", "비중확대 🟢", "비중축소 🔴", "유지 ➖"]:
                items = [f"`{p['ticker']}` ｜ {p['status']} ｜ 약 {p['krw']}" for p in portfolio if p["status"] == status_type]
                if items: fields.append({"name": status_type, "value": "\n".join(items), "inline": False})
            
            if WEBHOOK_URL:
                requests.post(WEBHOOK_URL, json={"embeds": [{
                    "title": f"🏛️ {name} TOP {TOP_N} 포트폴리오",
                    "description": f"📅 공시일: {date}",
                    "color": 15158332,
                    "fields": fields
                }]})
                time.sleep(3) 
                
            state[cik] = cur_acc

    if discovered_companies:
        with open(COMPANY_LIST_FILE, "w", encoding="utf-8") as f:
            json.dump(discovered_companies, f, ensure_ascii=False, indent=2)

    buy_con, sell_con = defaultdict(list), defaultdict(list)
    for guru, port in all_portfolios.items():
        for s in port:
            if s["status"] in ["신규진입 🔥", "비중확대 🟢"]: buy_con[s["ticker"]].append(guru.split()[0])
            elif s["status"] in ["비중축소 🔴", "전량매도 ❌"]: sell_con[s["ticker"]].append(guru.split()[0])

    hot_b = {k: v for k, v in buy_con.items() if len(v) >= 2}
    hot_s = {k: v for k, v in sell_con.items() if len(v) >= 2}

    fields = []
    if hot_b: fields.append({"name": "🎯 동시에 담은 종목", "value": "\n".join([f"**{k}** ({len(v)}명): {', '.join(v)}" for k, v in hot_b.items()])})
    if hot_s: fields.append({"name": "🚨 동시에 줄인 종목", "value": "\n".join([f"**{k}** ({len(v)}명): {', '.join(v)}" for k, v in hot_s.items()])})
    
    if not hot_b and not hot_s:
        fields.append({"name": "👀 겹친 종목 없음", "value": "이번 분기 제출자 중에는 2명 이상 동시에 매수/매도한 종목이 없습니다.", "inline": False})
    
    if WEBHOOK_URL:
        title_prefix = "[수동조회 전체보기] " if IS_MANUAL_RUN else ""
        requests.post(WEBHOOK_URL, json={"embeds": [{
            "title": f"{title_prefix}📊 13F 이번 시즌 누적 요약 ({len(all_portfolios)}명 제출 완료)",
            "color": 3447003,
            "fields": fields
        }]})
    
    save_state(state)

if __name__ == "__main__":
    process_13f()
