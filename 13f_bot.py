import os
import requests
import xml.etree.ElementTree as ET

# 깃허브 Settings -> Secrets에 등록한 13F 전용 디스코드 웹훅 주소
DISCORD_URL = os.environ.get('SEC_13F_WEBHOOK_URL')

def get_holdings_from_sec(cik, accession_num):
    """SEC에서 13F-HR 공시의 XML 정보를 파싱하여 {주식명: 수량} 딕셔너리를 반환합니다."""
    headers = {'User-Agent': 'YourName YourEmail@domain.com'}
    acc_clean = accession_num.replace('-', '')
    
    holdings = {}
    try:
        # SEC EDGAR에서 해당 공시 폴더의 파일 목록 조회
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
            
            for info in root.findall('.//ns:infoTable', ns) if ns else root.findall('.//infoTable'):
                issuer = info.find('.//ns:nameOfIssuer', ns).text if ns else info.find('.//nameOfIssuer').text
                shrs_amt = info.find('.//ns:sshPrnamt', ns) if ns else info.find('.//sshPrnamt')
                if shrs_amt is None:
                    shrs_amt = info.find('.//ns:ssh_prn_amt', ns) if ns else info.find('.//ssh_prn_amt')
                
                if issuer and shrs_amt is not None:
                    shares = int(shrs_amt.text)
                    # 대문자로 통일하여 저장
                    issuer_upper = issuer.upper().strip()
                    holdings[issuer_upper] = holdings.get(issuer_upper, 0) + shares
    except Exception as e:
        print(f"공시 파싱 중 오류 발생 (Accession: {accession_num}): {e}")
        
    return holdings

def get_13f_data():
    headers = {'User-Agent': 'jungseunghun ilman2tv@gmail.com'}
    
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
                print(f"{name}의 13F 공시를 찾을 수 없습니다.")
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
                
                # 매수 및 신규진입 계산
                for ticker, cur_shares in current_holdings.items():
                    if ticker not in prev_holdings:
                        trades.append({"ticker": ticker, "action": "신규진입 🔥", "shares": f"{cur_shares:,} 주", "change": "New"})
                    else:
                        prev_shares = prev_holdings[ticker]
                        diff = cur_shares - prev_shares
                        if diff > 0:
                            pct = (diff / prev_shares) * 100
                            trades.append({"ticker": ticker, "action": "매수 🟢", "shares": f"+{diff:,} 주", "change": f"+{pct:.1f}%"})
                            
                # 매도 계산
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
            
            # 주요 변동사항 상위 12개만 추려 전송
            trades = trades[:12] if trades else []
            send_to_discord(name, filing_date, trades)
            
        except Exception as e:
            print(f"{name} 데이터 가져오기 실패: {e}")

def convert_corporate_name(raw_name):
    """💡 복잡하고 긴 미국 법인명을 개인 투자자에게 친숙한 티커와 이름으로 변환합니다."""
    # 자주 등장하는 거장들의 핵심 보유 종목 변환 사전
    name_dict = {
        "APPLE INC": "AAPL (애플)",
        "NVIDIA CORP": "NVDA (엔비디아)",
        "MICROSOFT CORP": "MSFT (마이크로)",
        "AMAZON COM INC": "AMZN (아마존)",
        "REALTY INCOME CORP": "O (리얼티인컴)",
        "ALPHABET INC": "GOOGL (구글)",
        "META PLATFORMS INC": "META (메타)",
        "TESLA INC": "TSLA (테슬라)",
        "BERKSHIRE HATHAWAY INC": "BRK (버크셔)",
        "JPMORGAN CHASE & CO": "JPM (제이피모간)",
        "CHEVRON CORP NEW": "CVX (셰브론)",
        "BANK AMERICA CORP": "BAC (뱅크오브A)",
        "COCA COLA CO": "KO (코카콜라)",
        "COSTCO WHOLESALE CORP NEW": "COST (코스트코)",
        "NETFLIX INC": "NFLX (넷플릭스)",
        "BROADCOM INC": "AVGO (브로드컴)",
        "EXXON MOBIL CORP": "XOM (엑슨모빌)",
        "VISA INC": "V (비자카드)",
        "PROCTER & GAMBLE CO": "PG (P&G)",
        "PFIZER INC": "PFE (화이자)",
        "VERIZON COMMUNICATIONS INC": "VZ (버라이즌)",
        "SCHWAB CHARLES CORP": "SCHW (찰스슈왑)"
    }
    
    # 사전에 있으면 변환된 이름을, 없으면 앞 글자 14자만 깔끔하게 잘라서 반환
    for key, value in name_dict.items():
        if key in raw_name:
            return value
            
    return raw_name[:14].strip()

def send_to_discord(guru_name, date, trades):
    try:
        month = int(date.split('-')[1])
        if 4 <= month <= 6:
            period = "1분기 (1월 ~ 3월)"
        elif 7 <= month <= 9:
            period = "2분기 (4월 ~ 6월)"
        elif 10 <= month <= 12:
            period = "3분기 (7월 ~ 9월)"
        else:
            period = "4분기 (10월 ~ 12월)"
    except:
        period = "분기 데이터"

    sell_list = ""
    buy_list = ""
    new_list = ""
    
    for t in trades:
        # 💡 법인명을 보기 좋은 한글/티커 조합으로 가공합니다.
        clean_name = convert_corporate_name(t['ticker'])
        # 디스코드 가로 줄맞춤을 위해 14글자 포맷팅 적용
        line = f" ` {clean_name:<14} ` ｜ **{t['shares']}** `({t['change']})`\n"
        
        if "매도" in t['action']:
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
            "description": f"📊 **대상 기간:** {period}\n📅 **공시 확인일:** {date}  |  📄 **보고서:** 13F-HR\n──────────────────────────────",
            "color": 15158332,  
            "fields": [
                {"name": "🔴 이번 분기 매도 (Decrease)", "value": sell_list, "inline": False},
                {"name": "🟢 이번 분기 매수 (Increase)", "value": buy_list, "inline": False},
                {"name": "🔥 이번 분기 신규 진입 (New Entry)", "value": new_list, "inline": False},
                {"name": "──────────────────────────────", "value": "*🔗 본 알림은 SEC EDGAR 시스템과 연동되어 실시간으로 발송됩니다.*", "inline": False}
            ]
        }]
    }
    
    requests.post(DISCORD_URL, json=payload)

if __name__ == "__main__":
    get_13f_data()
