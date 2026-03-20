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

# --- [비밀 설정] 금고에서 가져오기 ---
try:
    GCP_CREDS = json.loads(st.secrets["gcp_service_account"])
    SOLAPI_KEY = st.secrets["solapi_api_key"]
    SOLAPI_SECRET = st.secrets["solapi_api_secret"]
    SENDER_PHONE = st.secrets["sender_phone"]
except Exception as e:
    st.error("보안 금고(Secrets) 설정이 필요합니다. 데모 모드로 작동합니다.")
    GCP_CREDS = None

# --- [설정] 구글 시트 연동 ---
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
        return None, None

student_sh, log_sh = init_sheet(GCP_CREDS)

# --- [설정] 솔라피 문자 발송 ---
def send_notification(student_name, total_minutes, parent_phone):
    if not GCP_CREDS or SOLAPI_KEY == "원장님의_솔라피_API_KEY": 
        return False
    
    date = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    salt = str(uuid.uuid4().hex)
    signature = hmac.new(SOLAPI_SECRET.encode(), (date + salt).encode(), hashlib.sha256).hexdigest()
    auth_str = f'HMAC-SHA256 apiKey={SOLAPI_KEY}, date={date}, salt={salt}, signature={signature}'
    
    headers = {'Authorization': auth_str, 'Content-Type': 'application/json'}
    text_content = f"[{student_name} 학생 하원 알림]\n오늘 더메타 수학학원에서 총 {total_minutes}분 동안 집중하여 자습을 완료했습니다. 따뜻한 격려 부탁드립니다! 👏"
    
    data = {
        'message': {
            'to': str(parent_phone).replace('-', ''),
            'from': str(SENDER_PHONE).replace('-', ''),
            'text': text_content
        }
    }
    try:
        res = requests.post('https://api.solapi.com/messages/v4/send', headers=headers, json=data)
        return res.status_code == 200
    except:
        return False

# --- [상태 관리] 누적 시간 및 로그인 상태 유지 ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'is_studying' not in st.session_state: st.session_state.is_studying = False
if 'accumulated_seconds' not in st.session_state: st.session_state.accumulated_seconds = 0
if 'start_time' not in st.session_state: st.session_state.start_time = None

# --- [UI 디자인] ---
st.set_page_config(page_title="더메타 스마트 자습실", layout="wide")
st.markdown("""<style>.main { background-color: #f8f9fa; } .stButton>button { width:100%; border-radius:10px; height:3em; font-weight:bold; }</style>""", unsafe_allow_html=True)

# --- [메인 화면] ---
st.title("🏛️ 더메타 수학학원 : AI 스마트 자습실")

col1, col2 = st.columns([2, 1])

with col1:
    with st.container():
        # [1단계: 로그인 화면]
        if not st.session_state.logged_in:
            st.subheader("👋 출석체크 (로그인)")
            student_name = st.text_input("학생 이름 입력", placeholder="예: 김응수")
            if st.button("🔑 로그인"):
                if not student_name:
                    st.warning("이름을 입력해주세요.")
                elif student_sh:
                    df = pd.DataFrame(student_sh.get_all_records())
                    student = df[df['이름'] == student_name]
                    if not student.empty:
                        st.session_state.logged_in = True
                        st.session_state.current_student = student.iloc[0]
                        st.session_state.accumulated_seconds = 0
                        st.rerun() # 화면 새로고침
                    else:
                        st.error("등록된 학생이 아닙니다.")
        
        # [2단계: 자습 관리 화면 (로그인 성공 후)]
        else:
            student = st.session_state.current_student
            st.success(f"🎓 **{student['이름']}** 학생, 환영합니다!")
            
            # 현재 상태 표시
            if st.session_state.is_studying:
                st.info("🔥 현재 집중해서 자습 중입니다!")
            else:
                st.warning("☕ 현재 휴식 중이거나 자습 대기 상태입니다.")
            
            c1, c2, c3 = st.columns(3)
            
            # [시작/재개 버튼]
            if not st.session_state.is_studying:
                if c1.button("▶️ 자습 시작"):
                    st.session_state.is_studying = True
                    st.session_state.start_time = datetime.now()
                    st.rerun()
            
            # [일시 정지 버튼]
            else:
                if c2.button("⏸️ 일시 정지 (휴식)"):
                    duration = (datetime.now() - st.session_state.start_time).total_seconds()
                    st.session_state.accumulated_seconds += duration
                    st.session_state.is_studying = False
                    st.rerun()
            
            # [최종 하원 버튼]
            if c3.button("⏹️ 최종 하원 (문자 전송)"):
                # 공부 중이었다면 마지막 시간까지 더하기
                if st.session_state.is_studying:
                    duration = (datetime.now() - st.session_state.start_time).total_seconds()
                    st.session_state.accumulated_seconds += duration
                
                # 총 분(minute) 계산 (최소 1분 보장)
                total_minutes = max(1, round(st.session_state.accumulated_seconds / 60))
                
                # 📱 진짜 문자 발송 (Solapi)
                success = send_notification(student['이름'], total_minutes, student['학부모전화번호'])
                
                # 📝 구글 시트 최종 기록
                if log_sh:
                    try:
                        log_sh.append_row([
                            str(student['이름']), 
                            str(student['고유ID']), 
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"), # 하원 시간 기록
                            "하원 완료", 
                            f"{total_minutes}분", 
                            "Y" if success else "N"
                        ])
                    except:
                        pass
                
                # 초기화 및 축하
                st.balloons()
                st.session_state.logged_in = False
                st.session_state.is_studying = False
                st.session_state.accumulated_seconds = 0
                st.success(f"수고하셨습니다! 오늘 총 {total_minutes}분 학습했으며, 부모님께 알림톡이 발송되었습니다.")
                # st.rerun() 생략하여 마지막 성공 메시지 보여줌

with col2:
    st.markdown("### 📸 시스템 작동 중")
    st.image("https://images.unsplash.com/photo-1434030216411-0b793f4b4173?w=400", use_container_width=True)
