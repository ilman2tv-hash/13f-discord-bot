import os
import requests
import json

# 💡 13F 전용 디스코드 비밀번호 주소를 가져옵니다!
DISCORD_URL = os.environ.get('SEC_13F_WEBHOOK_URL')

def get_13f_data():
    # ⭐ 중요: SEC 서버 차단을 막기 위해 본인 이름과 이메일 양식으로 꼭 수정해 주세요!
    headers = {'User-Agent': 'JUNGSEUNGHUN ilman2tv@gmail.com'}
    
    # 우리가 추적할 월가 거장 5인방 라인업
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
            for i, form in enumerate(recent_docs['form']):
                if form == '13F-HR':
                    filing_date = recent_docs['filingDate'][i]
                    
                    # 디스코드에 가독성 좋게 뿌려줄 매매 예시 데이터
                    trades = [
                        {"ticker": "AAPL (애플)", "action": "매도 🔴", "shares": "5,000,000 주", "change": "-3.1%"},
                        {"ticker": "O (리얼티인컴)", "action": "매수 🟢", "shares": "1,200,000 주", "change": "+8.5%"},
                        {"ticker": "JEPI", "action": "신규진입 🔥", "shares": "350,000 주", "change": "New"}
                    ]
                    
                    send_to_discord(name, filing_date, trades)
                    break 
        except Exception as e:
            print(f"{name} 데이터 가져오기 실패: {e}")

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
        line = f" ` {t['ticker'].split(' ')[0]:<6} ` ｜ **{t['shares']}** `({t['change']})`\n"
        
        if "매도" in t['action']:
            sell_list += f"📉 {line}"
        elif "매수" in t['action']:
            buy_list += f"📈 {line}"
        elif "신규" in t['action']:
            new_list += f"✨ {line}"
            
    sell_list = sell_list if sell_list else "❌ 이번 분기 매도 내역 없음\n"
    buy_list = buy_list if buy_list else "❌ 이번 분기 매수 내역 없음\n"
    new_list = new_list if new_list else "❌ 이번 분기 신규 진입 없음\n"
        
    payload = {
        "embeds": [{
            "title": f"🏛️ {guru_name}",
            "description": f"📊 **대상 기간:** {period}\n📅 **공시 확인일:** {date}  |  📄 **보고서:** 13F-HR\n──────────────────────────────",
            "color": 15158332,  
            "fields": [
                {"name": "🔴 이번 분기 매도 (Decrease)", "value": sell_list, "inline": False},
                {"name": "🟢 이번 분기 매수 (Increase)", "value": buy_list, "inline": False},
                {"name": "🔥 이번 분기 신규 진입 (New Entry)", "value": new_list, "inline": False},
                {"name": "──────────────────────────────", "value": "*🔗 본 알림은 SEC EDGAR 시스템과 연동되어 발송됩니다.*", "inline": False}
            ]
        }]
    }
    
    requests.post(DISCORD_URL, json=payload)

if __name__ == "__main__":
    get_13f_data()
