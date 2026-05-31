import os, json, time, requests
from collections import defaultdict
import xml.etree.ElementTree as ET

WEBHOOK_URL = os.environ.get("SEC_13F_WEBHOOK_URL")
HEADERS = {"User-Agent": "ilman2tv@gmail.com"} # 본인 이메일로 변경 필수
STATE_FILE = "state_13f.json"
COMPANY_LIST_FILE = "monitored_companies.json"
EXCHANGE_RATE = 1350
TOP_N = 10

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
        files = res.json().get("directory", {}).get("item", [])
        xml_file = next((f["name"] for f in files if f["name"].endswith(".xml") and "table" in f["name"].lower()), None)
        if not xml_file: return holdings

        xml_res = requests.get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{xml_file}", headers=HEADERS)
        root = ET.fromstring(xml_res.content)
        ns = {"ns": root.tag.split("}")[0].strip("{")} if "}" in root.tag else None
        
        info_tables = root.findall(".//ns:infoTable", ns) if ns else root.findall(".//infoTable")
        for info in info_tables:
            issuer = info.find(".//ns:nameOfIssuer", ns).text.strip() if ns else info.find(".//nameOfIssuer").text.strip()
            cusip = info.find(".//ns:cusip", ns).text.strip() if ns else info.find(".//cusip").text.strip()
            val = info.find(".//ns:value", ns).text.strip() if ns else info.find(".//value").text.strip()
            shares = info.find(".//ns:sshPrnamt", ns).text.strip() if ns else info.find(".//sshPrnamt").text.strip()
            if cusip: holdings[cusip] = {"issuer": issuer, "cusip": cusip, "value": safe_int(val), "shares": safe_int(shares)}
    except: pass
    return holdings

def process_13f():
    state = load_state()
    all_portfolios = {}
    discovered_companies = {}
    has_new_update = False # 새로운 공시가 하나라도 떴는지 확인하는 스위치

    for name, cik in GURUS.items():
        res = requests.get(f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json", headers=HEADERS)
        if res.status_code != 200: continue
        
        recent = res.json().get("filings", {}).get("recent", {})
        idx_13f = [i for i, f in enumerate(recent.get("form", [])) if f == "13F-HR"]
        if len(idx_13f) < 2: continue

        cur_acc = recent["accessionNumber"][idx_13f[0]]
        pre_acc = recent["accessionNumber"][idx_13f[1]]
        date = recent["filingDate"][idx_13f[0]]

        # 💡 [핵심] 알림 여부(상태)와 상관없이 일단 5명 전원의 최신 포트폴리오를 무조건 파싱합니다.
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
            time.sleep(0.3)

        # 5명의 데이터 바구니 완성
        if portfolio:
            all_portfolios[name] = portfolio

        # 💡 [핵심] 만약 이번에 처음 본 '새로운' 공시라면? 개별 알림을 보내고 스위치를 켭니다.
        if state.get(cik) != cur_acc and portfolio:
            has_new_update = True
            
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
            state[cik] = cur_acc

    # 💡 [핵심] 단 한 명이라도 새로운 공시가 떴다면, 5명 전체의 누적 데이터를 바탕으로 최종 요약을 쏩니다!
    if has_new_update:
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

        if hot_b or hot_s:
            fields = []
            if hot_b: fields.append({"name": "🎯 동시에 담은 종목", "value": "\n".join([f"**{k}** ({len(v)}명): {', '.join(v)}" for k, v in hot_b.items()])})
            if hot_s: fields.append({"name": "🚨 동시에 줄인 종목", "value": "\n".join([f"**{k}** ({len(v)}명): {', '.join(v)}" for k, v in hot_s.items()])})
            
            if WEBHOOK_URL:
                requests.post(WEBHOOK_URL, json={"embeds": [{
                    "title": f"📊 13F 최종 누적 요약 (현재 {len(all_portfolios)}명 데이터 기준)",
                    "color": 3447003,
                    "fields": fields
                }]})
    
    save_state(state)

if __name__ == "__main__":
    process_13f()
