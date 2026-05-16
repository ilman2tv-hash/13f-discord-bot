import os
import requests
import xml.etree.ElementTree as ET

# 깃허브 Settings -> Secrets에 등록한 13F 전용 디스코드 웹훅 주소
DISCORD_URL = os.environ.get('SEC_13F_WEBHOOK_URL')

def get_ticker_from_cusip(cusip):
    """💡 CUSIP 금융 번호나 법인명을 기반으로 실제 영문 티커를 실시간 조회합니다."""
    if not cusip:
        return None
    try:
        # 오픈 금융 API를 통해 CUSIP 번호로 정확한 주식 티커(Ticker)를 역추적
        url = f"https://query1.finance.yahoo.com/v1/finance/search?q={cusip}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            quotes = data.get('quotes', [])
            if quotes:
                # 가장 신뢰도 높은 첫 번째 검색 결과의 티커 반환 (예: AAPL, NVDA)
                return quotes[0].get('symbol')
    except:
        pass
    return None

def get_holdings_from_sec(cik, accession_num):
    """SEC에서 13F-HR 공시의 XML 정보를 파싱하여 {티커_또는_이름: 수량} 딕셔너리를 반환합니다."""
    headers = {'User-Agent': 'jungseunghun ilman2tv@gmail.com'}
    acc_clean = accession_num.replace('-', '')
    
    holdings = {}
    try:
        folder_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/index.json"
        res = requests.get(folder_url, headers=headers)
        if res.status_code != 200:
            return holdings
            
        files = res.json().get('directory', {}).get('item', [])
        xml_file = ""
        for f in files:
            name = f.get('name', '')
            if name.endswith('.xml') and ('table' in name.lower() or 'information' in name.lower()):
                xml_file = name
                break
        
        if not xml_file:
            for f in files:
                if f.get('name', '').endswith('.xml'):
                    xml_file = f.get('name', '')
                    break
                    
        if xml_file:
            xml_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{xml_file}"
            xml_res = requests.get(xml_url, headers=headers)
            root = ET.fromstring(xml_res.content)
            
            ns = {'ns': root.tag.split('}')[0].strip('{')} if '}' in root.tag else {}
            
            # 딱 12개 주요 종목만 효율적으로 변환하기 위해 카운트 제어
            count = 0
            for info in root.findall('.//ns:infoTable', ns) if ns else root.findall('.//infoTable'):
                if count > 30: # 너무 많은 중소형주 조회를 방지해 속도 업
                    break
                    
                issuer = info.find('.//ns:nameOfIssuer', ns).text if ns else info.find('.//nameOfIssuer').text
                cusip = info.find('.//ns:cusip', ns).text if ns else info.find('.//cusip').text
                shrs_amt = info.find('.//ns:sshPrnamt', ns) if ns else info.find('.//sshPrnamt')
                if shrs_amt is None:
                    shrs_amt = info.find('.//ns:ssh_prn_amt', ns) if ns else info.find('.//ssh_prn_amt')
                
                if issuer and shrs_amt is not None:
                    shares = int(shrs_amt.text)
                    
                    # 🚀 [핵심] 실시간 티커 조회 엔진 가동
                    ticker = get_ticker_from_cusip(cusip)
                    if not ticker:
                        # 티커 조회가 안 되면 기존 한글 변환 사전 활용
                        ticker = convert_corporate_name(issuer.upper().strip())
                    
                    holdings[ticker] = holdings.get(ticker, 0) + shares
                    count += 1
    except Exception as e:
        print(f"공시 파싱 중 오류 발생: {e}")
        
    return holdings

def get_13f_data():
    headers = {'User-Agent': 'YourName YourEmail@domain.com'}
    gurus = {
        "버크셔 해서웨이 (워런 버핏)": "0001067983",
        "스탠리 드러켄밀러": "0001568832",
        "폴 튜더 존스": "0000921703",
        "마이클 버리": "0001649339",
        "레이 달리오": "0001350694"
    }
    
    for name, cik in gurus.items():
        url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
        try:
            response = requests.get(url, headers=headers)
            data = response.json()
            recent_docs = data['filings']['recent']
            f_idx = [i for i, form in enumerate(recent_docs['form']) if form == '13F-HR']
            
            if len(f_idx) < 1:
                continue
                
            latest_i = f_idx[0]
            filing_date = recent_docs['filingDate'][latest_i]
            latest_acc = recent_docs['accessionNumber'][latest_i]
            
            current_holdings = get_holdings_from_sec(cik, latest_acc)
            trades = []
            
            if len(f_idx) >= 2:
                prev_i = f_idx[1]
                prev_acc = recent_docs['accessionNumber'][prev_i]
                prev_holdings = get_holdings_from_sec(cik, prev_acc)
                
                for ticker, cur_shares in current_holdings.items():
                    if ticker not in prev_holdings:
                        trades.append({"ticker": ticker, "action": "신규진입 🔥", "shares": f"{cur_shares:,} 주", "change": "New"})
                    else:
                        prev_shares = prev_holdings[ticker]
                        diff = cur_shares - prev_shares
                        if diff > 0:
                            pct = (diff / prev_shares) * 100
                            trades.append({"ticker": ticker, "action": "매수 🟢", "shares": f"+{diff:,} 주", "change": f"+{pct:.1f}%"})
                            
                for ticker, prev_shares in prev_holdings.items():
                    if ticker not in current_holdings:
                        trades.append({"ticker": ticker, "action": "전량매도 🔴", "shares": f"-{prev_shares:,} 주", "change": "-100%"})
                    else:
                        cur_shares = current_holdings[ticker]
                        diff = prev_shares - cur_shares
                        if diff > 0:
                            pct = (diff / prev_shares) * 100
                            trades.append({"ticker": ticker, "action": "매도 🔴", "shares": f"-{diff:,} 주", "change": f"-{pct:.1f}%"})
            else:
                sorted_holdings = sorted(current_holdings.items(), key=lambda x: x[1], reverse=True)[:5]
                for ticker, shares in sorted_holdings:
                    trades.append({"ticker": ticker, "action": "보유 🪙", "shares": f"{shares:,} 주", "change": "보유중"})
            
            trades = trades[:10] if trades else []
            send_to_discord(name, filing_date, trades)
        except Exception as e:
            print(f"{name} 실패: {e}")

def convert_corporate_name(raw_name):
    """백업용 한글 변환 사전"""
    name_dict = {
        "APPLE INC": "AAPL (애플)", "NVIDIA CORP": "NVDA (엔비디아)", "MICROSOFT CORP": "MSFT (마이크로)",
        "AMAZON COM INC": "AMZN (아마존)", "REALTY INCOME CORP": "O (리얼티인컴)", "ALPHABET INC": "GOOGL (구글)",
        "VERIZON COMMUNICATIONS": "VZ (버라이즌)", "PFIZER INC": "PFE (화이자)"
    }
    for key, value in name_dict.items():
        if key in raw_name:
            return value
    return raw_name[:12]

def send_to_discord(guru_name, date, trades):
    try:
        month = int(date.split('-')[1])
        if 4 <= month <= 6: period = "1분기 (1월 ~ 3월)"
        elif 7 <= month <= 9: period = "2분기 (4월 ~ 6월)"
        elif 10 <= month <= 12: period = "3분기 (7월 ~ 9월)"
        else: period = "4분기 (10월 ~ 12월)"
    except:
        period = "분기 데이터"

    sell_list, buy_list, new_list = "", "", ""
    
    for t in trades:
        # 이제 t['ticker']에는 깔끔한 영문 티커(예: AAPL, NVDA, O)가 들어옵니다!
        line = f" ` {t['ticker']:<10} ` ｜ **{t['shares']}** `({t['change']})`\n"
        
        if "매도" in t['action']: sell_list += f"📉 {line}"
        elif "매수" in t['action']: buy_list += f"📈 {line}"
        elif "신규" in t['action']: new_list += f"✨ {line}"
        else: buy_list += f"🪙 {line}"
            
    sell_list = sell_list if sell_list else "❌ 이번 분기 주요 매도 내역 없음\n"
    buy_list = buy_list if buy_list else "❌ 이번 분기 주요 매수 내역 없음\n"
    new_list = new_list if new_list else "❌ 이번 분기 주요 신규 진입 없음\n"
        
    payload = {
        "embeds": [{
            "title": f"🏛️ {guru_name}",
            "description": f"📊 **대상 기간:** {period}\n📅 **공시 확인일:** {date}\n──────────────────────────────",
            "color": 15158332,  
            "fields": [
                {"name": "🔴 이번 분기 매도 (Decrease)", "value": sell_list, "inline": False},
                {"name": "🟢 이번 분기 매수 (Increase)", "value": buy_list, "inline": False},
                {"name": "🔥 이번 분기 신규 진입 (New Entry)", "value": new_list, "inline": False},
                {"name": "──────────────────────────────", "value": "*🔗 본 알림은 인공지능 티커 변환 엔진이 적용되어 발송됩니다.*", "inline": False}
            ]
        }]
    }
    requests.post(DISCORD_URL, json=payload)

if __name__ == "__main__":
    get_13f_data()
