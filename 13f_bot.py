import os, json, requests
from collections import defaultdict
import xml.etree.ElementTree as ET

WEBHOOK_URL = os.environ.get("SEC_13F_WEBHOOK_URL")
HEADERS = {"User-Agent": "ilman2tv@gmail.com"} # 본인 이메일로 수정 권장
STATE_FILE = "state_13f.json"

# 타겟 구루 명단
GURUS = {
    "워런 버핏 (Berkshire)": "0001067983",
    "스탠리 드러켄밀러 (Duquesne)": "0001536411",
    "데이비드 테퍼 (Appaloosa)": "0000905567",
    "빌 애크먼 (Pershing Square)": "0001336528"
}

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f: return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, "w") as f: json.dump(state, f)

def send_discord(embed):
    if WEBHOOK_URL: requests.post(WEBHOOK_URL, json={"embeds": [embed]})

# (참고: API 호출 및 XML 파싱 함수는 기존에 작성하셨던 get_holdings_from_sec 함수를 그대로 활용하시면 됩니다. 
# 여기서는 핵심 흐름만 보여드립니다.)

def process_13f():
    state = load_state()
    all_portfolios = {}

    for name, cik in GURUS.items():
        # 1. API로 최신 13F-HR 공시 확인
        # 2. state에 저장된 accession number와 다르면 파싱 진행
        # 3. 기존 코드처럼 TOP 10 변화량(신규진입, 비중확대, 비중축소, 전량매도) 계산
        
        # 임시 예시 데이터 (실제로는 위에서 계산한 결과값)
        portfolio = [
            {"ticker": "AAPL", "status": "비중축소 🔴"},
            {"ticker": "CHUBB", "status": "신규진입 🔥"}
        ]
        
        if portfolio: # 새 공시가 있었다면
            all_portfolios[name] = portfolio
            # 개별 구루 알림 전송 로직 (기존 코드와 동일)
            # send_discord(개별_embed)
            state[cik] = "새로운_accession_number"

    # [핵심] 컨센서스 & 엑소더스 요약 전송
    if all_portfolios:
        buy_consensus = defaultdict(list)
        sell_exodus = defaultdict(list)

        for guru, port in all_portfolios.items():
            for stock in port:
                if stock["status"] in ["신규진입 🔥", "비중확대 🟢"]:
                    buy_consensus[stock["ticker"]].append(guru)
                elif stock["status"] in ["비중축소 🔴", "전량매도 ❌"]:
                    sell_exodus[stock["ticker"]].append(guru)

        hot_buys = {k: v for k, v in buy_consensus.items() if len(v) >= 2}
        hot_sells = {k: v for k, v in sell_exodus.items() if len(v) >= 2}

        if hot_buys or hot_sells:
            fields = []
            if hot_buys:
                buy_text = "\n".join([f"**{k}** ({len(v)}명): {', '.join(v)}" for k, v in hot_buys.items()])
                fields.append({"name": "🎯 스마트머니 동시 매수 (Consensus)", "value": buy_text, "inline": False})
            if hot_sells:
                sell_text = "\n".join([f"**{k}** ({len(v)}명): {', '.join(v)}" for k, v in hot_sells.items()])
                fields.append({"name": "🚨 스마트머니 동시 이탈 (Exodus)", "value": sell_text, "inline": False})

            send_discord({
                "title": "📊 13F 시즌 최종 요약 (스마트머니 겹치기)",
                "color": 3447003,
                "fields": fields
            })

    save_state(state)

if __name__ == "__main__":
    process_13f()
