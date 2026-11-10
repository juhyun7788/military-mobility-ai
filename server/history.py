"""분석 기록 저장 (Supabase).

환경변수 SUPABASE_URL, SUPABASE_SERVICE_KEY가 있으면 분석이 끝날 때마다 Supabase `analyses` 표에 기록합니다.
없으면 아무것도 하지 않습니다 (내 PC 실행 등).

- 키는 서버에서만 씁니다 (HF Space Secrets에 넣음). 웹페이지·저장소에는 키가 없습니다.
- 표 만들기 SQL: deploy/supabase_schema.sql
"""

from __future__ import annotations

import os

import requests

URL = os.getenv("SUPABASE_URL", "").rstrip("/")
KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
ENABLED = bool(URL and KEY)
TABLE = "analyses"


def _headers(extra: dict | None = None) -> dict:
    h = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
    h.update(extra or {})
    return h


def save(row: dict) -> str | None:
    """기록 1건 저장. 실패해도 분석 결과에는 영향 없음 (오류 문구만 돌려줌)."""
    if not ENABLED:
        return None
    try:
        r = requests.post(f"{URL}/rest/v1/{TABLE}", json=row, headers=_headers({"Prefer": "return=minimal"}), timeout=15)
        return None if r.ok else f"기록 저장 실패 (HTTP {r.status_code})"
    except Exception as e:
        return f"기록 저장 실패 ({type(e).__name__})"


def recent(limit: int = 30) -> list[dict]:
    if not ENABLED:
        return []
    r = requests.get(
        f"{URL}/rest/v1/{TABLE}",
        params={"select": "id,created_at,kind,title,verdict_text,mobility,threat_level,demo",
                "order": "created_at.desc", "limit": str(limit)},
        headers=_headers(), timeout=15,
    )
    r.raise_for_status()
    return r.json()


def get(rid: int) -> dict | None:
    if not ENABLED:
        return None
    r = requests.get(f"{URL}/rest/v1/{TABLE}", params={"id": f"eq.{int(rid)}", "select": "*"}, headers=_headers(), timeout=15)
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else None
