import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time

# --- [설정] 구글 시트 및 스타일 ---
def init_sheet():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
        client = gspread.authorize(creds)
        # 구글 시트에 'themeta_log'라는 이름의 시트가 있어야 함
        return client.open("themeta_log").sheet1
    except:
        return None

sheet = init_sheet()

st.set_page_config(page_title="더메타 스마트 자습실", layout="wide")
st.markdown("""<style>.main { background-color: #f8f9fa; } .stButton>button { width:100%; border-radius:10px; height:3em; font-weight:bold; }</style>""", unsafe_allow_html=True)

# --- [사이드바] 실시간 대시보드 ---
with st.sidebar:
    st.header("🏆 실시간 자습 현황")
    st.metric("현재 열공 중", "12명", "+2")
    st.write("---")
    st.write("최근 완료 학생: 홍길동(120분)")

# --- [메인] 시연 섹션 ---
st.title("🏛️ 더메타 수학학원 : AI 자습 관리 시스템")
st.subheader("데모 페이지 시연 모드")

col1, col2 = st.columns([2, 1])

with col1:
    with st.container():
        st.info("실제로 이름을 입력하고 시작/종료를 눌러보세요.")
        name = st.text_input("학생 이름 입력", placeholder="예: 시연원장님")
        
        c1, c2 = st.columns(2)
        if c1.button("▶️ 자습 시작"):
            st.session_state.start = datetime.now()
            st.success(f"[{name}]님, 자습 기록이 시작되었습니다!")
            if sheet: sheet.append_row([name, st.session_state.start.strftime("%H:%M:%S"), "진행중"])

        if c2.button("⏹️ 자습 종료"):
            if 'start' in st.session_state:
                st.balloons()
                st.success("자습이 완료되었습니다! 학부모님께 즉시 알림이 발송됩니다.")
            else:
                st.warning("먼저 시작 버튼을 눌러주세요.")

with col2:
    st.markdown("### 📸 학습 인증샷 (OCR)")
    st.file_uploader("오늘 푼 문제집을 찍어주세요", type=['jpg', 'jpeg', 'png'])
    st.image("https://images.unsplash.com/photo-1434030216411-0b793f4b4173?w=400", use_container_width=True, caption="샘플 인증샷")

st.markdown("---")
st.caption("© 2026 더메타 수학학원 스마트 브레인 시스템")