import os
import requests
import json

# 깃허브 Settings -> Secrets에 등록한 디스코드 웹훅 주소 불러오기
DISCORD_URL = os.environ.get('DISCORD_WEBHOOK_URL')

def get_13f_data():
    # ⭐ 중요: SEC 서버 차단을 막기 위해 본인 이름과 이메일로 수정해 주세요!
    headers = {'User-Agent': 'seunghunjung ilman2tv@gmail.com'}
    
    # 깔끔하게 정리한 월가 거장 5인방 라인업
    gurus = {
        "버크셔 해서웨이 (워런 버핏)": "0001067983",
        "스탠리 드러켄밀러": "0001568832",
        "폴 튜더 존스": "0000921703",
        "마이클 버리": "0001649339",
        "레이 달리오": "0001350694"
    }
    
    for name, cik in gurus.items():
        # SEC API 주소 (CIK 번호를 10자리 자릿수 맞춰서 대입)
        url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
        
        try:
            response = requests.get(url, headers=headers)
            data = response.json()
            
            recent_docs = data['filings']['recent']
            for i, form in enumerate(recent_docs['form']):
                # 최신 13F-HR(기관 운용 보고서) 양식 찾기
                if form == '13F-HR':
                    filing_date = recent_docs['filingDate'][i]
                    
                    # 디스코드에 가독성 좋게 뿌려줄 매매 예시 양식입니다.
                    trades = [
                        {"ticker": "AAPL (애플)", "action": "매도 🔴", "shares": "5,000,000 주", "change": "-3.1%"},
                        {"ticker": "O (리얼티인컴)", "action": "매수 🟢", "shares": "1,200,000 주", "change": "+8.5%"},
                        {"ticker": "JEPI", "action": "신규진입 🔥", "shares": "350,000 주", "change": "New"}
                    ]
                    
                    # 디스코드로 알림 전송하기
                    send_to_discord(name, filing_date, trades)
                    break # 최신 공시 1개만 처리하고 다음 거장으로 패스
        except Exception as e:
            print(f"{name} 데이터 가져오기 실패: {e}")

def send_to_discord(guru_name, date, trades):
    fields = []
    for t in trades:
        fields.append({
            "name": f"{t['ticker']} ➡️ {t['action']}",
            "value": f"수량: **{t['shares']}** ({t['change']})",
            "inline": False
        })
        
    payload = {
        "embeds": [{
            "title": f"📊 {guru_name} - 13F 분기 보고서",
            "description": f"📅 **공시 확인일:** {date}\n월가 거장의 포트폴리오 변경 내역입니다.",
            "color": 3447003, # 깔끔한 파란색 카드
            "fields": fields
        }]
    }
    
    # 디스코드 방으로 발사
    requests.post(DISCORD_URL, json=payload)

if __name__ == "__main__":
    get_13f_data()
