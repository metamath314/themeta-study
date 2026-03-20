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

# --- [설정] 솔라피 문자 발송 (오류 없는 API 방식) ---
def send_notification(student_name, total_minutes, parent_phone):
    if not GCP_CREDS or SOLAPI_KEY == "원장님의_솔라피_API_KEY": 
        return False
    
    date = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    salt = str(uuid.uuid4().hex)
    signature = hmac.new(SOLAPI_SECRET.encode(), (date + salt).encode(), hashlib.sha256).hexdigest()
    auth_str = f'HMAC-SHA256 apiKey={SOLAPI_KEY}, date={date}, salt={salt}, signature={signature}'
    
    headers = {'Authorization': auth_str, 'Content-Type': 'application/json'}
    text_content = f"[{student_name} 학생 자습 완료]\n오늘 총 {total_minutes}분 동안 집중하여 학습을 마쳤습니다. - 더메타 수학학원"
    
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

# --- [UI 디자인] ---
st.set_page_config(page_title="더메타 스마트 자습실", layout="wide")
st.markdown("""<style>.main { background-color: #f8f9fa; } .stButton>button { width:100%; border-radius:10px; height:3em; font-weight:bold; }</style>""", unsafe_allow_html=True)

# --- [비즈니스 로직] ---
def get_student_info(name):
    if not student_sh: return None
    df = pd.DataFrame(student_sh.get_all_records())
    student = df[df['이름'] == name]
    if not student.empty:
        return student.iloc[0]
    return None

# --- [메인 화면] ---
st.title("🏛️ 더메타 수학학원 : AI 스마트 자습실")
st.subheader("오늘의 학습 기록을 시작하세요.")

col1, col2 = st.columns([2, 1])

with col1:
    with st.container():
        st.info("이름을 입력하고 로그인 버튼을 눌러주세요.")
        student_name = st.text_input("학생 이름 입력", placeholder="예: 김응수")
        
        c1, c2 = st.columns(2)
        
        if c1.button("🔑 로그인 및 자습 시작"):
            if not student_name:
                st.warning("이름을 입력해주세요.")
            else:
                student_info = get_student_info(student_name)
                if student_info is not None:
                    st.session_state.start = datetime.now()
                    st.session_state.current_student = student_info
                    st.success(f"[{student_name}]님, 어서오세요! 자습 기록이 시작되었습니다.")
                    
                    # ★문제 해결: 모든 정보를 문자로 바꿔서 튕김 현상 원천 차단★
                    if log_sh:
                        try:
                            log_sh.append_row([
                                str(student_name), 
                                str(student_info['고유ID']), 
                                st.session_state.start.strftime("%Y-%m-%d %H:%M:%S"), 
                                "진행중", 
                                "0", 
                                "N"
                            ])
                        except Exception as e:
                            st.error(f"구글 시트 기록 중 오류 발생: {e}")
                else:
                    st.error("등록된 학생이 아닙니다. 학원에 문의하세요.")

        if c2.button("⏹️ 자습 종료 및 리포트 발송"):
            if 'start' in st.session_state and 'current_student' in st.session_state:
                st.session_state.end = datetime.now()
                duration = st.session_state.end - st.session_state.start
                total_minutes = max(1, round(duration.total_seconds() / 60)) # 최소 1분 보장
                
                student = st.session_state.current_student
                success = send_notification(student['이름'], total_minutes, student['학부모전화번호'])
                
                if log_sh:
                    try:
                        log_sh.append_row([
                            str(student['이름']), 
                            str(student['고유ID']), 
                            st.session_state.start.strftime("%Y-%m-%d %H:%M:%S"), 
                            st.session_state.end.strftime("%Y-%m-%d %H:%M:%S"), 
                            f"{total_minutes}분", 
                            "Y" if success else "N"
                        ])
                    except Exception as e:
                        st.error(f"종료 기록 중 오류: {e}")
                
                st.balloons()
                st.success(f"수고했어요! {total_minutes}분 동안 학습을 마쳤습니다. (문자 발송: {'대기/성공' if success else '테스트모드'})")
                
                del st.session_state.start
                del st.session_state.current_student
            else:
                st.warning("먼저 로그인 및 시작 버튼을 눌러주세요.")

with col2:
    st.markdown("### 🏆 오늘의 자습 현황")
    st.write("실시간 연동 준비 완료")
    st.image("https://images.unsplash.com/photo-1434030216411-0b793f4b4173?w=400", use_container_width=True, caption="스마트 브레인 시스템")
