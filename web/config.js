// 웹페이지 설정 (deploy/make_web_config.py가 .env를 읽어 만듭니다. 직접 고쳐도 됩니다)
// - API_BASE: 분석 서버 주소를 고정할 때만 넣음. 비워 두면 자동으로 찾음
//     1) 이 페이지를 분석 서버가 직접 제공하면(노트북 localhost) 같은 주소 사용
//     2) 아니면(Vercel) Supabase server_status 표에서 노트북 서버의 현재 공개 주소를 읽음
// - SUPABASE_ANON_KEY는 공개용 키입니다 (읽기 전용 정책). service_role 키는 절대 넣지 마세요.
window.API_BASE = "";
window.SUPABASE_URL = "";
window.SUPABASE_ANON_KEY = "";
