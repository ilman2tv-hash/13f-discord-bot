import os, json, requests
import xml.etree.ElementTree as ET

WEBHOOK_URL = os.environ.get("SEC_FORM4_WEBHOOK_URL")
HEADERS = {"User-Agent": "ilman2tv@gmail.com"} # 본인 이메일 입력
STATE_FILE = "state_form4.json"
COMPANY_LIST_FILE = "monitored_companies.json"

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f: return json.load(f)
    return {}

def load_target_companies():
    if os.path.exists(COMPANY_LIST_FILE):
        with open(COMPANY_LIST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"AAPL": "0000320193"}

def is_target_role(root):
    """CEO, CFO, Chairman, Director 등 핵심 내부자인지 확인"""
    if root.findtext(".//isDirector") == "1": return True, "Director"
    
    title = root.findtext(".//officerTitle")
    if title:
        t_upper = title.upper()
        if "CEO" in t_upper or "CHIEF EXECUTIVE" in t_upper: return True, "CEO"
        if "CFO" in t_upper or "FINANCIAL" in t_upper: return True, "CFO"
        if "CHAIRMAN" in t_upper: return True, "Chairman"
        
    return False, "Other"

def run():
    state = load_state()
    targets = load_target_companies()

    for ticker, identifier in targets.items():
        cik = str(identifier)
        if not cik.isdigit(): continue

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
                    
                    # 💡 조건 1: 직책 확인 (핵심 임원만)
                    is_target, role_name = is_target_role(root)
                    if not is_target: break

                    total_buy_usd = 0
                    total_shares_bought = 0
                    post_transaction_shares = 0
                    
                    for trans in root.findall(".//nonDerivativeTransaction"):
                        t_code = trans.findtext(".//transactionCode")
                        # 💡 조건 2: Open Market Buy (P)만 해당
                        if t_code == "P":
                            shares = float(trans.findtext(".//transactionShares/value") or 0)
                            price = float(trans.findtext(".//transactionPricePerShare/value") or 0)
                            total_buy_usd += (shares * price)
                            total_shares_bought += shares
                            
                            # 거래 후 총 보유량 추출 (마지막 거래 기준)
                            post_val = trans.findtext(".//postTransactionAmounts/sharesOwnedFollowingTransaction/value")
                            if post_val:
                                post_transaction_shares = float(post_val)

                    # 구매 내역이 없으면 패스
                    if total_shares_bought == 0: break

                    # 💡 조건 3: 증가율 계산
                    increase_pct = 0
                    if post_transaction_shares > total_shares_bought:
                        prev_shares = post_transaction_shares - total_shares_bought
                        increase_pct = (total_shares_bought / prev_shares) * 100
                    elif post_transaction_shares == total_shares_bought:
                        increase_pct = 100.0 # 기존에 없다가 새로 산 경우 (100% 증가로 취급)

                    # 원화 변환 (환율 1350원 기준)
                    krw_amount = total_buy_usd * 1350
                    
                    # 💡 조건 4: 3억 원 이상 매수 OR 보유량 10% 이상 증가
                    if krw_amount >= 300_000_000 or increase_pct >= 10.0:
                        
                        # 금액 텍스트 예쁘게 포맷팅 (예: 4억 8천만 원)
                        eok = int(krw_amount // 100_000_000)
                        cheon = int((krw_amount % 100_000_000) // 10_000_000)
                        krw_text = f"{eok}억 {cheon}천만 원" if cheon > 0 else f"{eok}억 원"
                        if eok == 0: krw_text = f"{int(krw_amount/10000)}만 원"

                        link = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{accession}-index.htm"
                        
                        embed = {
                            "title": f"💰 {role_name} 자사주 매수",
                            "color": 3066993,
                            "description": (
                                f"**종목:** {ticker}\n\n"
                                f"**매수금액:**\n약 {krw_text}\n\n"
                                f"**보유량:**\n+{increase_pct:.1f}%\n\n"
                                f"[SEC 원문 확인]({link})"
                            )
                        }
                        if WEBHOOK_URL: requests.post(WEBHOOK_URL, json={"embeds": [embed]})
                        
                except Exception as e:
                    print(f"Form4 파싱 에러 ({ticker}): {e}")
                
                state[cik] = accession
                break # 최신 1개만 처리

    with open(STATE_FILE, "w") as f: json.dump(state, f)

if __name__ == "__main__":
    run()
