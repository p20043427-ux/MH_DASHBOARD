"""
tests/test_settings.py — config/settings.py 핵심 로직 단위 테스트

실행: pytest tests/test_settings.py -v
"""
import hmac
import os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_SETTINGS_SRC = (_ROOT / "config" / "settings.py").read_text(encoding="utf-8")
_LLM_SRC = (_ROOT / "core" / "llm.py").read_text(encoding="utf-8")


# ── 소스 코드 수준 보안 검증 ─────────────────────────────────────────

class TestSourceCodeSecurity:
    def test_no_hardcoded_moonhwa_default(self):
        """admin_password 기본값 'moonhwa' 하드코딩 제거 확인."""
        assert 'default=SecretStr("moonhwa")' not in _SETTINGS_SRC, (
            "config/settings.py 에 admin_password 기본값 'moonhwa' 가 남아있습니다"
        )
        assert "default=SecretStr('moonhwa')" not in _SETTINGS_SRC, (
            "config/settings.py 에 admin_password 기본값 'moonhwa' 가 남아있습니다"
        )

    def test_admin_password_field_is_required(self):
        """admin_password 필드가 required (기본값 없음) 인지 확인."""
        # admin_password 정의 블록에서 default= 가 없어야 함
        import re
        block = re.search(
            r"admin_password.*?(?=\n    \w|\Z)",
            _SETTINGS_SRC,
            re.DOTALL,
        )
        assert block, "admin_password 필드 정의를 찾을 수 없습니다"
        block_text = block.group(0)
        assert "default=" not in block_text, (
            "admin_password 에 default 가 설정되어 있습니다 — required 필드여야 합니다"
        )

    def test_check_admin_uses_hmac(self):
        """check_admin() 이 timing-safe HMAC 비교를 사용하는지 확인."""
        assert "hmac.compare_digest" in _SETTINGS_SRC, (
            "check_admin() 이 hmac.compare_digest 를 사용해야 합니다 (타이밍 공격 방어)"
        )

    def test_llm_uses_settings_temperature(self):
        """core/llm.py 가 하드코딩 0.1 대신 settings.llm_temperature 를 사용하는지 확인."""
        assert '"temperature": 0.1' not in _LLM_SRC, (
            "core/llm.py 에 temperature 0.1 하드코딩이 남아있습니다"
        )
        assert "settings.llm_temperature" in _LLM_SRC, (
            "core/llm.py 가 settings.llm_temperature 를 사용해야 합니다"
        )


# ── HMAC 비교 로직 직접 검증 ─────────────────────────────────────────

class TestHmacLogic:
    """check_admin() 이 내부적으로 쓰는 hmac.compare_digest 동작 검증."""

    def _compare(self, stored: str, candidate: str) -> bool:
        return hmac.compare_digest(stored.encode(), candidate.encode())

    def test_correct_match(self):
        assert self._compare("SecretPass99!", "SecretPass99!") is True

    def test_wrong_match(self):
        assert self._compare("SecretPass99!", "wrongpass") is False

    def test_empty_candidate(self):
        assert self._compare("SecretPass99!", "") is False

    def test_case_sensitive(self):
        assert self._compare("Pass", "pass") is False


# ── 런타임 설정 값 검증 (실제 settings 싱글턴) ───────────────────────

class TestRuntimeSettings:
    def test_llm_temperature_in_valid_range(self):
        """실제 설정된 llm_temperature 가 유효 범위(0~2)인지 확인."""
        from config.settings import settings
        assert 0.0 <= settings.llm_temperature <= 2.0

    def test_llm_max_output_tokens_positive(self):
        from config.settings import settings
        assert settings.llm_max_output_tokens > 0

    def test_oracle_max_rows_positive(self):
        from config.settings import settings
        assert settings.oracle_max_rows > 0

    def test_admin_password_not_empty(self):
        """실행 환경에서 admin_password 가 빈값이 아닌지 확인."""
        from config.settings import settings
        pw = settings.admin_password.get_secret_value()
        assert pw, "ADMIN_PASSWORD 가 설정되지 않았습니다"

    def test_admin_password_not_moonhwa(self):
        """실행 환경에서 취약 기본값 'moonhwa' 로 운영 중이 아닌지 확인."""
        from config.settings import settings
        pw = settings.admin_password.get_secret_value()
        assert pw != "moonhwa", (
            "ADMIN_PASSWORD 가 취약 기본값 'moonhwa' 로 설정되어 있습니다. "
            ".env 파일에서 강력한 패스워드로 변경하세요."
        )
