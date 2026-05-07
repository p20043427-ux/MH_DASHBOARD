"""
tests/test_sql_validator.py — llm/sql_generator.py SqlValidator 단위 테스트

Oracle 연결 없이 순수 정규식·로직 레이어만 검증합니다.
실행: pytest tests/test_sql_validator.py -v
"""
import os
import sys
import pytest
from pathlib import Path

# Oracle 의존성 없이 SqlValidator 만 임포트하기 위한 경로 설정
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# settings 필수 환경변수 사전 설정
os.environ.setdefault("GOOGLE_API_KEY", "AIzaFakeKeyForTests")
os.environ.setdefault("ADMIN_PASSWORD", "TestAdminPass123!")

from llm.sql_generator import SqlValidator


@pytest.fixture
def validator():
    """화이트리스트 없는 SqlValidator (Oracle 연결 없이 로드)."""
    v = SqlValidator.__new__(SqlValidator)
    v.whitelist = []  # 화이트리스트 비워서 Oracle 조회 건너뜀
    v.max_rows = 5000
    return v


# ── Layer 1: SELECT 시작 확인 ────────────────────────────────────────

class TestLayer1SelectStart:
    def test_valid_select(self, validator):
        ok, sql, err = validator.validate("SELECT * FROM V_OPD_KPI FETCH FIRST 10 ROWS ONLY")
        assert ok is True

    def test_insert_blocked(self, validator):
        ok, _, err = validator.validate("INSERT INTO tbl VALUES (1)")
        assert ok is False
        assert "SELECT" in err

    def test_update_blocked(self, validator):
        ok, _, err = validator.validate("UPDATE tbl SET col=1")
        assert ok is False

    def test_delete_blocked(self, validator):
        ok, _, err = validator.validate("DELETE FROM tbl")
        assert ok is False

    def test_ctas_blocked(self, validator):
        ok, _, err = validator.validate("CREATE TABLE t AS SELECT * FROM v")
        assert ok is False


# ── Layer 2: 위험 패턴 차단 ─────────────────────────────────────────

class TestLayer2DangerousPatterns:
    def test_drop_in_comment_blocked(self, validator):
        ok, _, err = validator.validate("SELECT 1 -- DROP TABLE users")
        assert ok is False

    def test_multi_statement_semicolon(self, validator):
        ok, _, err = validator.validate(
            "SELECT 1 FROM DUAL; DROP TABLE users"
        )
        assert ok is False
        assert "세미콜론" in err

    def test_dbms_package_blocked(self, validator):
        ok, _, err = validator.validate("SELECT DBMS_OUTPUT.PUT_LINE('x') FROM DUAL")
        assert ok is False

    def test_sys_schema_blocked(self, validator):
        ok, _, err = validator.validate("SELECT * FROM SYS.USER$ FETCH FIRST 1 ROWS ONLY")
        assert ok is False

    def test_dba_view_blocked(self, validator):
        ok, _, err = validator.validate("SELECT * FROM DBA_USERS FETCH FIRST 1 ROWS ONLY")
        assert ok is False

    def test_v_dollar_blocked(self, validator):
        ok, _, err = validator.validate("SELECT * FROM V$SESSION FETCH FIRST 1 ROWS ONLY")
        assert ok is False

    def test_utl_http_blocked(self, validator):
        ok, _, err = validator.validate(
            "SELECT UTL_HTTP.REQUEST('http://evil.com') FROM DUAL"
        )
        assert ok is False


# ── 행 제한 자동 추가 ────────────────────────────────────────────────

class TestRowLimit:
    def test_fetch_first_added_when_missing(self, validator):
        ok, safe_sql, _ = validator.validate("SELECT * FROM V_OPD_KPI")
        assert ok is True
        upper = safe_sql.upper()
        assert "FETCH FIRST" in upper or "ROWNUM" in upper, (
            "행 제한(FETCH FIRST / ROWNUM) 이 자동으로 추가되어야 합니다"
        )

    def test_existing_fetch_normalized(self, validator):
        """FETCH FIRST 포함 SQL 도 정상 통과 (ROWNUM 래핑으로 정규화될 수 있음)."""
        sql = "SELECT * FROM V_OPD_KPI FETCH FIRST 100 ROWS ONLY"
        ok, safe_sql, _ = validator.validate(sql)
        assert ok is True
        upper = safe_sql.upper()
        assert "FETCH FIRST" in upper or "ROWNUM" in upper

    def test_existing_rownum_not_duplicated(self, validator):
        sql = "SELECT * FROM V_OPD_KPI WHERE ROWNUM <= 50"
        ok, safe_sql, _ = validator.validate(sql)
        assert ok is True


# ── 빈 SQL 처리 ─────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_sql(self, validator):
        ok, _, err = validator.validate("")
        assert ok is False

    def test_whitespace_only(self, validator):
        ok, _, err = validator.validate("   \n  ")
        assert ok is False

    def test_trailing_semicolon_removed(self, validator):
        ok, safe_sql, _ = validator.validate(
            "SELECT * FROM V_OPD_KPI FETCH FIRST 10 ROWS ONLY;"
        )
        assert ok is True
        assert not safe_sql.rstrip().endswith(";")
