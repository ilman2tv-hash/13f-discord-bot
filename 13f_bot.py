import os
import time
import requests
import xml.etree.ElementTree as ET

# 깃허브 Settings -> Secrets에 등록한 13F 전용 디스코드 웹훅 주소
DISCORD_URL = os.environ.get('SEC_13F_WEBHOOK_URL')

def get_ticker_from_cusip(cusip):
    """💡 CUSIP 금융 번호를 기반으로 실제 영문 티커를 조회합니다."""
    if not cusip:
        return None
    try:
        url = f"https://query1.finance.yahoo.com/v1/finance/search?q={cusip}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            quotes = data.get('quotes', [])
            if quotes:
                return quotes[0].get('symbol')
    except Exception as e:
        print(f"티커 조회 중 오류 ({cusip}): {e}")
    return None

def convert_corporate_name(raw_name):
    """백업용 한글 변환 사전"""
    name_dict = {
        "APPLE INC": "AAPL", "NVIDIA CORP": "NVDA", "MICROSOFT CORP": "MSFT",
        "AMAZON COM INC": "AMZN", "REALTY INCOME CORP": "O", "ALPHABET INC": "GOOGL",
        "VERIZON COMMUNICATIONS": "VZ", "PFIZER INC": "PFE"
    }
    for key, value in name_dict.items():
        if key in raw_name:
            return value
    return raw_name[:12]

def get_holdings_from_sec(cik, accession_num):
    """SEC에서 13F-HR 공시의 XML 정보를 파싱하여 {티커: 수량} 딕셔너리를 반환합니다."""
    headers = {'User-Agent': 'jungseunghun ilman2tv@gmail.com'}
    acc_clean = accession_num.replace('-', '')
    
    holdings = {}
    try:
        folder_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/index.json"
        res = requests.get(folder_url, headers=headers, timeout=10)
        if res.status_code != 200:
            return holdings
            
        files = res.json().get('directory', {}).get('item', [])
        xml_file = next((f.get('name', '') for f in files if f.get('name', '').endswith('.xml') and ('table' in f.get('name', '').lower() or 'information' in f.get('name', '').lower())), "")
        
        if not xml_file:
            xml_file = next((f.get('name', '') for f in files if f.get('name', '').endswith('.xml')), "")
                    
        if xml_file:
            xml_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{xml_file}"
            xml_res = requests.get(xml_url, headers=headers, timeout=10)
            root = ET.fromstring(xml_res.content)
            
            ns = {'ns': root.tag.split('}')[0].strip('{')} if '}' in root.tag else {}
            
            count = 0
            info_tables = root.findall('.//ns:infoTable', ns) if ns else root.findall('.//infoTable')
            
            for info in info_tables:
                if count >= 15:  # 디스코드 전송 가독성을 위해 한 기관당 상위 15개 선에서 제어
                    break
                    
                issuer = info.find('.//ns:nameOfIssuer', ns).text if ns else info.find('.//nameOfIssuer').text
                cusip = info.find('.//ns:cusip', ns).text if ns else info.find('.//cusip').text
                shrs_amt = info.find('.//ns:sshPrnamt', ns) if ns else info.find('.//sshPrnamt')
                if shrs_amt is None:
                    shrs_amt = info.find('.//ns:ssh_prn_amt', ns) if ns else info.find('.//ssh_prn_amt')
                
                if issuer and shrs_amt is not None:
                    try:
                        shares = int(shrs_amt.text)
                    except ValueError:
                        continue
                    
                    ticker = get_ticker_from_cusip(cusip)
                    time.sleep(0.2)  # 야후 API 차단 방지 딜레이
                    
                    if not ticker:
                        ticker = convert_corporate_name(issuer.upper().strip())
                    
                    holdings[ticker] = holdings.get(ticker, 0) + shares
                    count += 1
                    
    except Exception as e:
        print(f"공시 파싱 중 오류 발생: {e}")
        
    return holdings

def get_13f_data():
    headers = {'User-Agent': 'jungseunghun ilman2tv@gmail.com'}
    
    # 요청하신 새로운 구루/기관 라인업 반영
    gurus = {
        "버크셔 해서웨이 (워런 버핏)": "0001067983",
        "스탠리 드러켄밀러 (Duquesne)": "0001568832",
        "데이비드 테퍼 (Appaloosa)": "0000905567",
        "Bridgewater (레이 달리오)": "0001350694",
        "Coatue Management": "0001461573",
        "Tiger Global": "0001456346"
    }
    
    for name, cik in gurus.items():
        print(f"🔄 {name} 데이터 수집 중...")
        url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
        try:
            response = requests.get(url, headers=headers, timeout=10)
            data = response.json()
            recent_docs = data['filings']['recent']
            f_idx = [i for i, form in enumerate(recent_docs['form']) if form == '13F-HR']
            
            if not f_idx:
                print(f"❌ {name}: 최근 13F-HR 공시를 찾을 수 없습니다.")
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
                
                all_tickers = set(current_holdings.keys()) | set(prev_holdings.keys())
                
                for ticker in all_tickers:
                    cur_shares = current_holdings.get(ticker, 0)
                    prev_shares = prev_holdings.get(ticker, 0)
                    
                    if prev_shares == 0 and cur_shares > 0:
                        trades.append({"ticker": ticker, "action": "신규진입 🔥", "shares": f"{cur_shares:,} 주", "change": "New", "sort_key": cur_shares})
                    elif cur_shares == 0 and prev_shares > 0:
                        trades.append({"ticker": ticker, "action": "전량매도 🔴", "shares": f"-{prev_shares:,} 주", "change": "-100%", "sort_key": prev_shares})
                    elif cur_shares > prev_shares:
                        diff = cur_shares - prev_shares
                        pct = (diff / prev_shares) * 100
                        trades.append({"ticker": ticker, "action": "매수 🟢", "shares": f"+{diff:,} 주", "change": f"+{pct:.1f}%", "sort_key": diff})
                    elif cur_shares < prev_shares:
                        diff = prev_shares - cur_shares
                        pct = (diff / prev_shares) * 100
                        trades.append({"ticker": ticker, "action": "매도 🔴", "shares": f"-{diff:,} 주", "change": f"-{pct:.1f}%", "sort_key": diff})
                
                # 변동량이 큰 주요 종목 상위 10개 정렬
                trades = sorted(trades, key=lambda x: x['sort_key'], reverse=True)[:10]
            else:
                sorted_holdings = sorted(current_holdings.items(), key=lambda x: x[1], reverse=True)[:10]
                for ticker, shares in sorted_holdings:
                    trades.append({"ticker": ticker, "action": "보유 🪙", "shares": f"{shares:,} 주", "change": "보유중"})
            
            if trades:
                send_to_discord(name, filing_date, trades)
            
            time.sleep(0.5)  # SEC 디도스 오해 방지 딜레이
            
        except Exception as e:
            print(f"❌ {name} 처리 중 실패: {e}")

def send_to_discord(guru_name, date, trades):
    if not DISCORD_URL:
        print(f"⚠️ 디스코드 웹훅 URL이 설정되지 않아 {guru_name} 전송을 건너뜁니다.")
        return

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
        line = f" ` {t['ticker']:<12} ` ｜ **{t['shares']}** `({t['change']})`\n"
        
        if "전량매도" in t['action'] or t['action'] == "매도 🔴": 
            sell_list += f"📉 {line}"
        elif "매수" in t['action']: 
            buy_list += f"📈 {line}"
        elif "신규" in t['action']: 
            new_list += f"✨ {line}"
        else: 
            buy_list += f"🪙 {line}"
            
    sell_list = sell_list if sell_list else "❌ 이번 분기 주요 매도 내역 없음\n"
    buy_list = buy_list if buy_list else "❌ 이번 분기 주요 매수 내역 없음\n"
    new_list = new_list if new_list else "❌ 이번 분기 주요 신규 진입 없음\n"
        
    payload = {
        "embeds": [{
            "title": f"🏛️ {guru_name}",
            "description": f"📊 **대상 기간:** {period}\n📅 **공시 확인일:** {date}\n──────────────────────────────",
            "color": 15158332,  
            "fields": [
                {"name": "🔴 이번 분기 매도 (Decrease / Liquidated)", "value": sell_list, "inline": False},
                {"name": "🟢 이번 분기 매수 (Increase)", "value": buy_list, "inline": False},
                {"name": "🔥 이번 분기 신규 진입 (New Entry)", "value": new_list, "inline": False},
                {"name": "──────────────────────────────", "value": "*🔗 본 알림은 인공지능 티커 변환 엔진이 적용되어 발송됩니다.*", "inline": False}
            ]
        }]
    }
    
    try:
        res = requests.post(DISCORD_URL, json=payload, timeout=10)
        if res.status_code == 204:
            print(f"✅ {guru_name} 디스코드 전송 완료!")
        else:
            print(f"⚠️ 디스코드 전송 실패 ({res.status_code}): {res.text}")
    except Exception as e:
        print(f"디스코드 전송 중 에러: {e}")

if __name__ == "__main__":
    get_13f_data()
