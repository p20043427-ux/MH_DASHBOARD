# Oracle VIEW 목록 — 가이드봇 대시보드
> 스키마: `JAIN_WM` / 마지막 갱신: 2026-04-28

---

## 목차
1. [원무 현황 대시보드 (finance_dashboard.py)](#1-원무-현황-대시보드)
2. [병동 대시보드 (hospital_dashboard.py)](#2-병동-대시보드)
3. [간호 대시보드 (nursing_dashboard.py)](#3-간호-대시보드)
4. [공통 패널 (_shared.py)](#4-공통-패널)
5. [신규 VIEW 생성 SQL (DBA 요청용)](#5-신규-view-생성-sql)

---

## 1. 원무 현황 대시보드
파일: `ui/finance_dashboard.py` + `ui/panels/dept_analysis.py`

### 실시간 현황 탭

| VIEW 이름 | 주요 컬럼 | 용도 |
|-----------|-----------|------|
| `V_OPD_KPI` | 외래환자수, 신환자수, 수납금액, 미수금 | 상단 KPI 카드 |
| `V_OPD_DEPT_STATUS` | 진료과명, 대기수, 진료중, 완료 | 진료과별 대기 현황 |
| `V_KIOSK_STATUS` | 키오스크ID, 상태, 거래건수, 금액 | 키오스크 현황 |
| `V_DISCHARGE_PIPELINE` | 환자ID, 진료과, 퇴원예정시간, 단계 | 퇴원 파이프라인 |
| `V_WARD_BED_DETAIL` | 병동, 병실, 병상번호, 환자ID, 재원일수 | 병상 세부 현황 |
| `V_WARD_ROOM_DETAIL` | 병동, 병실, 총병상, 사용중, 공실 | 병실 요약 |
| `V_KIOSK_BY_DEPT` | 진료과명, 거래건수, 수납금액 | 진료과별 키오스크 |
| `V_KIOSK_COUNTER_TREND` | 기준일, 시간대, 창구번호, 거래건수 | 창구별 시간대 추이 |
| `V_DAILY_DEPT_STAT` | 기준일, 진료과명, 외래수, 입원수, 퇴원수 | 일별 진료과 집계 |
| `V_DAY_INWEON_3` | 기준일, 구분, 인원수 | 일별 재원/입원/퇴원 3일 |

### 수납 현황 (실시간 현황 탭 내)

| VIEW 이름 | 주요 컬럼 | 용도 |
|-----------|-----------|------|
| `V_FINANCE_TODAY` | 수납건수, 수납금액, 미수금, 카드수납 | 오늘 수납 KPI |
| `V_FINANCE_TREND` | 기준일, 수납금액, 미수금, 건수 | 수납 추이 라인차트 |
| `V_FINANCE_BY_DEPT` | 진료과명, 수납금액, 미수금, 건수 | 진료과별 수납 |
| `V_OVERDUE_STAT` | 미수구간, 건수, 금액, 비율 | 미수금 구간별 통계 |

### 주간추이분석 탭

| VIEW 이름 | 주요 컬럼 | 용도 |
|-----------|-----------|------|
| `V_OPD_DEPT_TREND` | 기준일, 진료과명, 외래환자수, 신환자수 | 7일 외래 추이 히트맵 |
| `V_IPD_DEPT_TREND` | 기준일, 진료과명, 입원수, 퇴원수, 재원수 | 7일 입원 추이 히트맵 |
| `V_LOS_DIST_DEPT` | 진료과명, 재원일수구간, 구간순서, 환자수 | 진료과별 재원일수 분포 |

### 월간추이분석 탭

| VIEW 이름 | 주요 컬럼 | 용도 |
|-----------|-----------|------|
| `V_MONTHLY_OPD_DEPT` | 기준년월(YYYYMM), 진료과명, 외래환자수, 신환자수, 구환자수, 신환비율 | 월별 외래 비교 차트 |

### 지역별 통계 탭

| VIEW 이름 | 주요 컬럼 | 용도 |
|-----------|-----------|------|
| `V_REGION_DEPT_MONTHLY` | 기준월(YYYYMM), 진료과명, 지역, 환자수 | 월별 지역×진료과 환자수 |
| `V_REGION_DEPT_DAILY` | 기준일, 진료과명, 지역, 환자수 | 일별 지역×진료과 환자수 (지도용) |

### 진료과 분석 탭 (신규 — `ui/panels/dept_analysis.py`)

| VIEW 이름 | 주요 컬럼 | 상태 | 용도 |
|-----------|-----------|------|------|
| `V_REGION_DEPT_MONTHLY` | 기준월, 진료과명, 지역, 환자수 | ✅ 기존 | 구군별 유입 차트 |
| `V_MONTHLY_OPD_DEPT` | 기준년월, 진료과명, 외래환자수, 신환자수, 구환자수, 신환비율 | ✅ 기존 | 월별 추세 라인 |
| `V_DEPT_GENDER_MONTHLY` | 기준월, 진료과명, 성별, 환자수 | 🆕 신규 필요 | 성별 파이차트 |
| `V_DEPT_AGE_MONTHLY` | 기준월, 진료과명, 연령대(10년), 환자수 | 🆕 신규 필요 | 연령대 막대차트 |
| `V_DEPT_CATEGORY_AGE` | 기준월, 진료과명, 구분(외래/입원), 연령대, 환자수 | 🆕 신규 필요 | 구분별 연령대 누적막대 |

### 카드 매칭 탭

| VIEW 이름 | 주요 컬럼 | 용도 |
|-----------|-----------|------|
| `V_KIOSK_CARD_APPROVAL` | 거래일자, 승인번호, 카드번호(마스킹), 금액, 카드사, 단말기ID, 설치위치 | 병원 카드 승인 내역 (xlsx 대조) |

---

## 2. 병동 대시보드
파일: `ui/hospital_dashboard.py`

| VIEW 이름 | 주요 컬럼 | 용도 |
|-----------|-----------|------|
| `V_BED_SUMMARY` | 병동코드, 병동명, 총병상, 재원, 공실, 점유율 | 병동별 병상 요약 KPI |
| `V_PATIENT_LIST` | 병동, 병실, 환자ID, 환자명, 진단코드, 입원일, 재원일수 | 환자 목록 |
| `V_DISCHARGE_TODAY` | 환자ID, 병동, 퇴원예정, 퇴원완료여부 | 오늘 퇴원 예정/완료 |
| `V_ADMISSION_TODAY` | 환자ID, 병동, 입원일시, 진료과 | 오늘 신규 입원 |
| `V_WARD_ALERT` | 병동, 알림유형, 환자ID, 발생시각 | 병동 알림 (낙상·욕창 등) |
| `V_VITAL_LATEST` | 환자ID, 측정시각, 체온, 혈압(수축/이완), 맥박, 산소포화도 | 최근 활력징후 |
| `V_DIET_STATUS` | 병동, 식이코드, 환자수 | 식이 현황 |
| `V_NURSING_TASK` | 병동, 간호업무구분, 미완료건수, 완료건수 | 간호업무 현황 |

---

## 3. 간호 대시보드
파일: `ui/nursing_dashboard.py`

| VIEW 이름 | 주요 컬럼 | 용도 |
|-----------|-----------|------|
| `V_NURSING_SHIFT` | 날짜, 근무조, 병동, 간호사수, 담당환자수 | 근무조별 인력 현황 |
| `V_HANDOVER_LOG` | 환자ID, 인계시각, 인계자, 인수자, 특이사항 | 인계 기록 |
| `V_FALL_RISK` | 환자ID, 병동, 낙상위험점수, 평가일시 | 낙상 위험도 |
| `V_PRESSURE_ULCER` | 환자ID, 병동, 욕창부위, 욕창단계, 최근처치일 | 욕창 현황 |
| `V_MEDICATION_ADMIN` | 환자ID, 약품코드, 투약시각, 투약량, 투약경로, 담당간호사 | 투약 기록 |
| `V_CALL_BELL` | 병동, 병실, 호출시각, 응대시각, 대기시간_초 | 호출벨 응대 현황 |

---

## 4. 공통 패널
파일: `ui/panels/_shared.py`

| VIEW 이름 | 주요 컬럼 | 용도 |
|-----------|-----------|------|
| `V_OPD_KPI` | (원무와 동일) | 공통 KPI 조회 래퍼 |
| `V_BED_SUMMARY` | (병동과 동일) | 공통 병상 요약 |

---

## 5. 신규 VIEW 생성 SQL
> 아래 SQL을 DBA에게 전달하여 진료과 분석 탭 활성화

```sql
-- ① V_DEPT_GENDER_MONTHLY
--    월별 진료과×성별 환자수
CREATE OR REPLACE VIEW JAIN_WM.V_DEPT_GENDER_MONTHLY AS
SELECT
    TO_CHAR(기준일, 'YYYYMM')  AS 기준월,
    진료과명,
    성별,
    COUNT(*)                   AS 환자수
FROM JAIN_WM.PATIENT_VISIT_BASE
GROUP BY
    TO_CHAR(기준일, 'YYYYMM'),
    진료과명,
    성별;


-- ② V_DEPT_AGE_MONTHLY
--    월별 진료과×연령대(10년단위) 환자수
CREATE OR REPLACE VIEW JAIN_WM.V_DEPT_AGE_MONTHLY AS
SELECT
    TO_CHAR(기준일, 'YYYYMM')                                    AS 기준월,
    진료과명,
    FLOOR(MONTHS_BETWEEN(기준일, 생년월일) / 120) * 10           AS 연령대,
    COUNT(*)                                                      AS 환자수
FROM JAIN_WM.PATIENT_VISIT_BASE
GROUP BY
    TO_CHAR(기준일, 'YYYYMM'),
    진료과명,
    FLOOR(MONTHS_BETWEEN(기준일, 생년월일) / 120) * 10;


-- ③ V_DEPT_CATEGORY_AGE
--    월별 진료과×구분(외래/입원/응급)×연령대 환자수
CREATE OR REPLACE VIEW JAIN_WM.V_DEPT_CATEGORY_AGE AS
SELECT
    TO_CHAR(기준일, 'YYYYMM')                                    AS 기준월,
    진료과명,
    구분,
    FLOOR(MONTHS_BETWEEN(기준일, 생년월일) / 120) * 10           AS 연령대,
    COUNT(*)                                                      AS 환자수
FROM JAIN_WM.PATIENT_VISIT_BASE
GROUP BY
    TO_CHAR(기준일, 'YYYYMM'),
    진료과명,
    구분,
    FLOOR(MONTHS_BETWEEN(기준일, 생년월일) / 120) * 10;
```

> **참고**: `PATIENT_VISIT_BASE` 테이블명 및 컬럼명은 실제 DB 스키마에 맞게 수정 필요.
> 각 VIEW의 상세 CREATE SQL은 `ui/panels/dept_analysis.py` 파일 상단 docstring에도 기재됨.

---

## VIEW 존재 여부 확인 쿼리

```sql
-- JAIN_WM 스키마의 전체 VIEW 목록 조회
SELECT VIEW_NAME, READ_ONLY
FROM ALL_VIEWS
WHERE OWNER = 'JAIN_WM'
ORDER BY VIEW_NAME;
```

---

*본 문서는 코드 기반으로 자동 정리됨. VIEW 스키마 변경 시 이 파일도 함께 수정하세요.*
