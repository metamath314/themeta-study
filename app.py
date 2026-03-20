import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import requests
import json
import uuid
import hmac
import hashlib

# --- [1. 보안 설정: Secrets에서 불러오기] ---
try:
    GCP_CREDS = json.loads(st.secrets["gcp_service_account"])
    SOLAPI_KEY = st.secrets["solapi_api_key"]
    SOLAPI_SECRET = st.secrets["solapi_api_secret"]
    SENDER_PHONE = st.secrets["sender_phone"]
except Exception as e:
    st.error("보안 설정(Secrets)이 완료되지 않았습니다. 관리자 설정을 확인하세요.")
    GCP_CREDS = None

# --- [2. 구글 시트 초기화] ---
@st.cache_resource(ttl=600)
def init_sheet(creds_data):
    if not creds_data: return None, None
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_data, scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open("themeta_db")
        return spreadsheet.worksheet("Students_DB"), spreadsheet.worksheet("Attendance_Log")
    except Exception as e:
        st.error(f"구글 시트 연결 실패: {e}")
        return None, None

student_sh, log_sh = init_sheet(GCP_CREDS)

# --- [3. 솔라피 문자 발송 함수 (보안 및 번호 보정 강화)] ---
def send_notification(student_name, total_minutes, parent_phone):
    if not GCP_CREDS or SOLAPI_KEY == "원장님의_솔라피_API_KEY": 
        return False
    
    # [번호 보정] 0이 빠졌거나 하이픈이 있는 경우 처리
    phone = str(parent_phone).replace('-', '').strip()
    if phone.startswith('10') and len(phone) == 10:
        phone = '0' + phone
    
    # API 인증용 시그니처 생성
    date = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    salt = str(uuid.uuid4().hex)
    signature = hmac.new(SOLAPI_SECRET.encode(), (date + salt).encode(), hashlib.sha256).hexdigest()
    auth_str = f'HMAC-SHA256 apiKey={SOLAPI_KEY}, date={date}, salt={salt}, signature={signature}'
    
    headers = {'Authorization': auth_str, 'Content-Type': 'application/json'}
    text_content = f"[{student_name} 학생 하원]\n오늘 총 {total_minutes}분간 자습을 성실히 마쳤습니다. 격려 부탁드립니다! - 더메타 수학학원"
    
    data = {
        'message': {
            'to': phone,
            'from': str(SENDER_PHONE).replace('-', ''),
            'text': text_content
        }
    }
    try:
        res = requests.post('https://api.solapi.com/messages/v4/send', headers=headers, json=data)
        return res.status_code == 200
    except:
        return False

# --- [4. 앱 상태 관리 변수 설정] ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'is_studying' not in st.session_state: st.session_state.is_studying = False
if 'accumulated_seconds' not in st.session_state: st.session_state.accumulated_seconds = 0
if 'start_time' not in st.session_state: st.session_state.start_time = None

# --- [5. UI 디자인] ---
st.set_page_config(page_title="더메타 스마트 자습실", layout="wide")
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button { width:100%; border-radius:12px; height:3.5em; font-weight:bold; font-size: 1.1em; }
    .status-box { padding: 20px; border-radius: 15px; margin-bottom: 20px; text-align: center; }
    </style>
    """, unsafe_allow_html=True)

# --- [6. 메인 로직] ---
st.title("🏛️ 더메타 수학학원 : AI 스마트 자습실")

col1, col2 = st.columns([1.5, 1])

with col1:
    # [A. 로그인 화면: 부정행위 방지 위해 이름+ID 체크]
    if not st.session_state.logged_in:
        st.subheader("🔐 학생 인증 로그인")
        with st.form("login_form"):
            input_name = st.text_input("학생 이름", placeholder="이름 입력")
            input_id = st.text_input("고유 ID (비밀번호)", type="password", placeholder="숫자 4자리")
            submit = st.form_submit_button("🔑 자습실 입장")
            
            if submit:
                if student_sh:
                    df = pd.DataFrame(student_sh.get_all_records())
                    # 이름과 고유ID(숫자)가 모두 일치하는 행 탐색
                    student = df[(df['이름'] == input_name) & (df['고유ID'].astype(str) == input_id)]
                    
                    if not student.empty:
                        st.session_state.logged_in = True
                        st.session_state.current_student = student.iloc[0]
                        st.session_state.accumulated_seconds = 0
                        st.rerun()
                    else:
                        st.error("⚠️ 이름 또는 고유 ID가 올바르지 않습니다.")
                else:
                    st.error("데이터베이스 연결에 문제가 있습니다.")

    # [B. 자습 관리 화면: 일시정지 및 누적 시간]
    else:
        student = st.session_state.current_student
        st.success(f"🎓 **{student['이름']}** 학생, 오늘 공부를 응원합니다!")
        
        # 현재 누적된 시간 계산 (분 단위 표시용)
        current_acc = st.session_state.accumulated_seconds
        if st.session_state.is_studying:
            current_acc += (datetime.now() - st.session_state.start_time).total_seconds()
        
        display_min = round(current_acc / 60, 1)
        st.metric("현재까지 누적 자습 시간", f"{display_min} 분")

        st.divider()

        c1, c2 = st.columns(2)
        
        # 1. 시작 및 재개
        if not st.session_state.is_studying:
            if c1.button("▶️ 자습 시작 / 다시 시작"):
                st.session_state.is_studying = True
                st.session_state.start_time = datetime.now()
                st.rerun()
        # 2. 일시 정지 (누적치 저장)
        else:
            if c1.button("⏸️ 일시 정지 (휴식/식사)"):
                duration = (datetime.now() - st.session_state.start_time).total_seconds()
                st.session_state.accumulated_seconds += duration
                st.session_state.is_studying = False
                st.rerun()
        
        # 3. 최종 하원 (문자 발송 및 로그 기록)
        if c2.button("⏹️ 최종 하원 (문자 전송)"):
            with st.spinner("하원 리포트를 부모님께 발송 중..."):
                if st.session_state.is_studying:
                    duration = (datetime.now() - st.session_state.start_time).total_seconds()
                    st.session_state.accumulated_seconds += duration
                
                total_minutes = max(1, round(st.session_state.accumulated_seconds / 60))
                
                # 솔라피 실전 발송
                success = send_notification(student['이름'], total_minutes, student['학부모전화번호'])
                
                # 구글 시트 로그 남기기
                if log_sh:
                    try:
                        log_sh.append_row([
                            str(student['이름']), 
                            str(student['고유ID']), 
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "하원완료", 
                            f"{total_minutes}분", 
                            "Y" if success else "N"
                        ])
                    except: pass
                
                st.balloons()
                msg = f"오늘 총 {total_minutes}분 자습 완료! 문자 발송 성공." if success else f"오늘 {total_minutes}분 자습 완료. (문자 발송 실패 - 잔액 또는 번호 확인)"
                st.success(msg)
                
                # 세션 초기화 (로그아웃 효과)
                st.session_state.logged_in = False
                st.session_state.is_studying = False
                st.session_state.accumulated_seconds = 0

with col2:
    st.markdown("### 📢 자습실 안내")
    st.info("""
    1. **입장:** 본인의 이름과 고유 ID를 입력하세요.
    2. **기록:** 자리에 앉으면 '자습 시작'을 누르세요.
    3. **휴식:** 밥을 먹거나 쉴 때는 '일시 정지'를 누르세요.
    4. **귀가:** 집에 갈 때 '최종 하원'을 누르면 부모님께 문자가 갑니다.
    """)
    st.image("https://images.unsplash.com/photo-1497633762265-9d179a990aa6?w=400", use_container_width=True)
