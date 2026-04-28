-- =============================================================================
--  가이드봇 대시보드 — Oracle VIEW 전체 DDL
--  스키마  : JAIN_WM
--  작성일  : 2026-04-28
--  대상 DB : Oracle 12c 이상 (Thin Mode 사용)
--
--  [실행 계정]
--    JAIN_WM 또는 DBA 권한 계정으로 실행
--    SELECT 전용 운영 계정(rag_readonly)에는 아래 GRANT 문 별도 실행 필요
--
--  [파일 구성]
--    PART 1. 원무 대시보드 VIEW      (finance_app.py  포트 8503)
--    PART 2. 병동 대시보드 VIEW      (dashboard_app.py 포트 8501)
--    PART 3. 간호 대시보드 VIEW      (nursing_dashboard.py)
--    PART 4. 진료과 분석 VIEW (신규) (ui/panels/dept_analysis.py)
--    PART 5. RAG 접근제어 설정 테이블
--    PART 6. SELECT 권한 GRANT
--
--  [주의사항]
--    · FROM 절의 기본 테이블명·컬럼명은 실제 DB 스키마에 맞게 수정 필요
--    · 컬럼명 주석(-- 원본컬럼: XXX)을 참고하여 매핑
--    · PART 4 신규 VIEW 는 기존 테이블 구조 확인 후 생성
-- =============================================================================


-- =============================================================================
-- PART 1. 원무 대시보드 VIEW
--         finance_app.py (포트 8503) / ui/finance_dashboard.py
-- =============================================================================

------------------------------------------------------------------------
-- 1-01. V_OPD_KPI  —  외래 당일 KPI 단일 행
--   사용처 : 실시간 현황 탭 > 상단 KPI 카드
--   조회  : SELECT * FROM JAIN_WM.V_OPD_KPI WHERE ROWNUM = 1
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_OPD_KPI AS
SELECT
    SUM(CASE WHEN 구분 = '외래' THEN 인원수 ELSE 0 END)   AS 외래환자수,
    SUM(CASE WHEN 구분 = '신환' THEN 인원수 ELSE 0 END)   AS 신환자수,
    SUM(CASE WHEN 구분 = '입원' THEN 인원수 ELSE 0 END)   AS 입원환자수,
    SUM(CASE WHEN 구분 = '퇴원' THEN 인원수 ELSE 0 END)   AS 퇴원환자수,
    SUM(CASE WHEN 구분 = '재원' THEN 인원수 ELSE 0 END)   AS 재원환자수,
    (SELECT NVL(SUM(수납금액),0) FROM 수납원장 WHERE TRUNC(수납일시) = TRUNC(SYSDATE)) AS 수납금액,
    (SELECT NVL(SUM(미수금액),0) FROM 수납원장 WHERE TRUNC(수납일시) = TRUNC(SYSDATE)) AS 미수금
FROM 일별인원현황
WHERE 기준일 = TRUNC(SYSDATE);
-- ※ 기본 테이블명(일별인원현황, 수납원장)은 실제 테이블로 교체 필요


------------------------------------------------------------------------
-- 1-02. V_OPD_DEPT_STATUS  —  진료과별 실시간 대기·진료·완료
--   사용처 : 실시간 현황 탭 > 진료과 대기 현황
--   조회  : SELECT * ... ORDER BY 대기수 DESC
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_OPD_DEPT_STATUS AS
SELECT
    진료과명,
    NVL(SUM(CASE WHEN 상태 = '대기' THEN 1 ELSE 0 END), 0) AS 대기수,
    NVL(SUM(CASE WHEN 상태 = '진료중' THEN 1 ELSE 0 END), 0) AS 진료중,
    NVL(SUM(CASE WHEN 상태 = '완료' THEN 1 ELSE 0 END), 0)  AS 완료,
    NVL(SUM(CASE WHEN 상태 = '부재중' THEN 1 ELSE 0 END), 0) AS 부재중,
    ROUND(AVG(대기시간_분), 1)                              AS 평균대기시간
FROM 외래접수현황
WHERE TRUNC(접수일시) = TRUNC(SYSDATE)
GROUP BY 진료과명;


------------------------------------------------------------------------
-- 1-03. V_KIOSK_STATUS  —  키오스크별 실시간 상태
--   사용처 : 실시간 현황 탭 > 키오스크 현황
--   조회  : SELECT * ... ORDER BY 키오스크ID
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_KIOSK_STATUS AS
SELECT
    K.키오스크ID,
    K.설치위치,
    K.상태,
    NVL(T.거래건수, 0)  AS 거래건수,
    NVL(T.수납금액, 0)  AS 수납금액,
    NVL(T.오류건수, 0)  AS 오류건수,
    K.최종점검일시
FROM 키오스크마스터 K
LEFT JOIN (
    SELECT 키오스크ID, COUNT(*) AS 거래건수,
           SUM(금액) AS 수납금액,
           SUM(CASE WHEN 결과코드 <> '00' THEN 1 ELSE 0 END) AS 오류건수
    FROM 키오스크거래내역
    WHERE TRUNC(거래일시) = TRUNC(SYSDATE)
    GROUP BY 키오스크ID
) T ON K.키오스크ID = T.키오스크ID;


------------------------------------------------------------------------
-- 1-04. V_WARD_ROOM_DETAIL  —  병실별 요약 (병상 수·공실)
--   사용처 : 실시간 현황 탭 > 병실 현황
--   조회  : SELECT * ... ORDER BY 병동명, 병실번호
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_WARD_ROOM_DETAIL AS
SELECT
    병동명,
    병실번호,
    COUNT(*)                                                       AS 총병상수,
    SUM(CASE WHEN 사용여부 = 'Y' THEN 1 ELSE 0 END)                AS 사용중,
    SUM(CASE WHEN 사용여부 = 'N' THEN 1 ELSE 0 END)                AS 공실,
    ROUND(SUM(CASE WHEN 사용여부='Y' THEN 1 ELSE 0 END) / COUNT(*) * 100, 1) AS 점유율
FROM 병상현황
GROUP BY 병동명, 병실번호;


------------------------------------------------------------------------
-- 1-05. V_WARD_BED_DETAIL  —  병상별 세부 현황 (환자 단위)
--   사용처 : 실시간 현황 탭 > 병상 세부
--   조회  : SELECT * ... ORDER BY 병동명
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_WARD_BED_DETAIL AS
SELECT
    B.병동명,
    B.병실번호,
    B.침상번호,
    B.사용여부,
    P.환자ID,
    P.환자명,
    P.진료과명,
    P.입원일자,
    TRUNC(SYSDATE) - TRUNC(P.입원일자)  AS 재원일수,
    P.주진단명
FROM 병상현황 B
LEFT JOIN 입원환자현황 P ON B.병동명 = P.병동명
                       AND B.병실번호 = P.병실번호
                       AND B.침상번호 = P.침상번호
                       AND P.퇴원여부 = 'N';


------------------------------------------------------------------------
-- 1-06. V_DISCHARGE_PIPELINE  —  오늘 퇴원 파이프라인
--   사용처 : 실시간 현황 탭 > 퇴원 파이프라인
--   조회  : SELECT * ... ORDER BY 단계, 병동명
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_DISCHARGE_PIPELINE AS
SELECT
    병동명,
    진료과명,
    환자ID,
    퇴원예정시간,
    CASE
        WHEN 수납완료여부 = 'Y' AND 원무확인여부 = 'Y' THEN '퇴원완료'
        WHEN 수납완료여부 = 'Y'                        THEN '수납완료'
        WHEN 퇴원오더여부 = 'Y'                        THEN '퇴원오더'
        ELSE                                           '퇴원예정'
    END AS 단계,
    퇴원오더여부,
    수납완료여부,
    원무확인여부
FROM 퇴원진행현황
WHERE TRUNC(퇴원예정일) = TRUNC(SYSDATE);


------------------------------------------------------------------------
-- 1-07. V_FINANCE_TODAY  —  오늘 수납 현황 집계
--   사용처 : 실시간 현황 탭 > 수납 KPI
--   조회  : SELECT * ... ORDER BY 금액 DESC
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_FINANCE_TODAY AS
SELECT
    보험유형,
    COUNT(*)          AS 건수,
    SUM(수납금액)      AS 수납금액,
    SUM(미수금액)      AS 미수금액,
    ROUND(SUM(수납금액) / NULLIF(SUM(수납금액 + 미수금액), 0) * 100, 1) AS 수납율
FROM 수납원장
WHERE TRUNC(수납일시) = TRUNC(SYSDATE)
GROUP BY 보험유형;


------------------------------------------------------------------------
-- 1-08. V_FINANCE_TREND  —  30일 수납 추이
--   사용처 : 실시간 현황 탭 > 수납 추이 차트
--   조회  : SELECT * ... ORDER BY 기준일
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_FINANCE_TREND AS
SELECT
    TRUNC(수납일시)           AS 기준일,
    COUNT(*)                  AS 건수,
    SUM(수납금액)              AS 수납금액,
    SUM(미수금액)              AS 미수금액,
    SUM(수납금액 + 미수금액)   AS 청구금액
FROM 수납원장
WHERE 수납일시 >= TRUNC(SYSDATE) - 30
GROUP BY TRUNC(수납일시);


------------------------------------------------------------------------
-- 1-09. V_FINANCE_BY_DEPT  —  진료과별 수납 현황
--   사용처 : 실시간 현황 탭 > 진료과별 수납
--   조회  : SELECT * ... ORDER BY 수납금액 DESC
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_FINANCE_BY_DEPT AS
SELECT
    진료과명,
    COUNT(*)      AS 건수,
    SUM(수납금액) AS 수납금액,
    SUM(미수금액) AS 미수금액
FROM 수납원장
WHERE TRUNC(수납일시) = TRUNC(SYSDATE)
GROUP BY 진료과명;


------------------------------------------------------------------------
-- 1-10. V_OVERDUE_STAT  —  미수금 연령구간 통계
--   사용처 : 실시간 현황 탭 > 미수금 현황
--   조회  : SELECT * ... ORDER BY 연령구분
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_OVERDUE_STAT AS
SELECT
    CASE
        WHEN TRUNC(SYSDATE) - TRUNC(발생일자) <=  30 THEN '30일이내'
        WHEN TRUNC(SYSDATE) - TRUNC(발생일자) <=  90 THEN '31~90일'
        WHEN TRUNC(SYSDATE) - TRUNC(발생일자) <= 180 THEN '91~180일'
        WHEN TRUNC(SYSDATE) - TRUNC(발생일자) <= 365 THEN '181~365일'
        ELSE                                           '365일초과'
    END AS 연령구분,
    COUNT(*)      AS 건수,
    SUM(미수금액) AS 미수금액,
    ROUND(SUM(미수금액) / SUM(SUM(미수금액)) OVER() * 100, 1) AS 비율
FROM 미수금현황
WHERE 미수금액 > 0
GROUP BY
    CASE
        WHEN TRUNC(SYSDATE) - TRUNC(발생일자) <=  30 THEN '30일이내'
        WHEN TRUNC(SYSDATE) - TRUNC(발생일자) <=  90 THEN '31~90일'
        WHEN TRUNC(SYSDATE) - TRUNC(발생일자) <= 180 THEN '91~180일'
        WHEN TRUNC(SYSDATE) - TRUNC(발생일자) <= 365 THEN '181~365일'
        ELSE                                           '365일초과'
    END;


------------------------------------------------------------------------
-- 1-11. V_FINANCE_BY_INS  —  보험유형별 수납 통계
--   사용처 : 병동 대시보드 > 재무 KPI
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_FINANCE_BY_INS AS
SELECT
    보험유형,
    COUNT(*)      AS 건수,
    SUM(수납금액) AS 수납금액,
    ROUND(SUM(수납금액) / SUM(SUM(수납금액)) OVER() * 100, 1) AS 비율
FROM 수납원장
WHERE TRUNC(수납일시) = TRUNC(SYSDATE)
GROUP BY 보험유형;


------------------------------------------------------------------------
-- 1-12. V_OPD_DEPT_TREND  —  7일 외래 추이 (진료과별)
--   사용처 : 주간추이분석 탭 > 외래 히트맵
--   조회  : SELECT * ... ORDER BY 기준일, 외래환자수 DESC
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_OPD_DEPT_TREND AS
SELECT
    TRUNC(접수일시)  AS 기준일,
    진료과명,
    COUNT(*)         AS 외래환자수,
    SUM(CASE WHEN 신환여부 = 'Y' THEN 1 ELSE 0 END) AS 신환자수,
    SUM(CASE WHEN 신환여부 = 'N' THEN 1 ELSE 0 END) AS 구환자수
FROM 외래접수현황
WHERE 접수일시 >= TRUNC(SYSDATE) - 6
GROUP BY TRUNC(접수일시), 진료과명;


------------------------------------------------------------------------
-- 1-13. V_IPD_DEPT_TREND  —  7일 입원 추이 (진료과별)
--   사용처 : 주간추이분석 탭 > 입원 히트맵
--   조회  : SELECT * ... ORDER BY 기준일, 입원환자수 DESC
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_IPD_DEPT_TREND AS
SELECT
    기준일,
    진료과명,
    SUM(CASE WHEN 구분 = '입원' THEN 인원수 ELSE 0 END) AS 입원환자수,
    SUM(CASE WHEN 구분 = '퇴원' THEN 인원수 ELSE 0 END) AS 퇴원환자수,
    SUM(CASE WHEN 구분 = '재원' THEN 인원수 ELSE 0 END) AS 재원환자수
FROM 일별인원현황
WHERE 기준일 >= TRUNC(SYSDATE) - 6
GROUP BY 기준일, 진료과명;


------------------------------------------------------------------------
-- 1-14. V_LOS_DIST_DEPT  —  진료과별 재원일수 분포
--   사용처 : 주간추이분석 탭 > 재원일수 분포 차트
--   조회  : SELECT * ... ORDER BY 진료과명, 구간순서
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_LOS_DIST_DEPT AS
SELECT
    진료과명,
    CASE
        WHEN 재원일수 <=  3 THEN '1~3일'
        WHEN 재원일수 <=  7 THEN '4~7일'
        WHEN 재원일수 <= 14 THEN '8~14일'
        WHEN 재원일수 <= 30 THEN '15~30일'
        ELSE                     '30일초과'
    END AS 재원일수구간,
    CASE
        WHEN 재원일수 <=  3 THEN 1
        WHEN 재원일수 <=  7 THEN 2
        WHEN 재원일수 <= 14 THEN 3
        WHEN 재원일수 <= 30 THEN 4
        ELSE                     5
    END AS 구간순서,
    COUNT(*) AS 환자수
FROM (
    SELECT 진료과명,
           TRUNC(SYSDATE) - TRUNC(입원일자) AS 재원일수
    FROM 입원환자현황
    WHERE 퇴원여부 = 'N'
)
GROUP BY
    진료과명,
    CASE WHEN 재원일수<=3 THEN '1~3일'   WHEN 재원일수<=7  THEN '4~7일'
         WHEN 재원일수<=14 THEN '8~14일' WHEN 재원일수<=30 THEN '15~30일'
         ELSE '30일초과' END,
    CASE WHEN 재원일수<=3 THEN 1 WHEN 재원일수<=7  THEN 2
         WHEN 재원일수<=14 THEN 3 WHEN 재원일수<=30 THEN 4
         ELSE 5 END;


------------------------------------------------------------------------
-- 1-15. V_MONTHLY_OPD_DEPT  —  월별 진료과 외래 지표 (최근 13개월)
--   사용처 : 월간추이분석 탭 / 진료과 분석 탭
--   조회  : SELECT * ... ORDER BY 기준년월 DESC, 진료과명
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_MONTHLY_OPD_DEPT AS
SELECT
    TO_CHAR(TRUNC(접수일시, 'MM'), 'YYYYMM')           AS 기준년월,
    진료과명,
    COUNT(*)                                            AS 외래환자수,
    SUM(CASE WHEN 신환여부='Y' THEN 1 ELSE 0 END)      AS 신환자수,
    SUM(CASE WHEN 신환여부='N' THEN 1 ELSE 0 END)      AS 구환자수,
    ROUND(
        SUM(CASE WHEN 신환여부='Y' THEN 1 ELSE 0 END)
        / NULLIF(COUNT(*), 0) * 100, 1
    )                                                   AS 신환비율
FROM 외래접수현황
WHERE 접수일시 >= ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -12)
GROUP BY TO_CHAR(TRUNC(접수일시,'MM'),'YYYYMM'), 진료과명;


------------------------------------------------------------------------
-- 1-16. V_KIOSK_COUNTER_TREND  —  7일 창구별 시간대 거래 추이
--   사용처 : 실시간 현황 탭 > 창구별 추이
--   조회  : SELECT * ... ORDER BY 기준일
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_KIOSK_COUNTER_TREND AS
SELECT
    TRUNC(거래일시)                    AS 기준일,
    창구번호,
    TO_CHAR(거래일시, 'HH24')          AS 시간대,
    COUNT(*)                           AS 거래건수,
    SUM(금액)                          AS 수납금액
FROM 키오스크거래내역
WHERE 거래일시 >= TRUNC(SYSDATE) - 6
GROUP BY TRUNC(거래일시), 창구번호, TO_CHAR(거래일시, 'HH24');


------------------------------------------------------------------------
-- 1-17. V_KIOSK_BY_DEPT  —  진료과별 키오스크 거래 집계 (당일)
--   사용처 : 실시간 현황 탭 > 진료과별 키오스크
--   조회  : SELECT * ... ORDER BY 진료과 CASE
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_KIOSK_BY_DEPT AS
SELECT
    진료과       AS 진료과,
    COUNT(*)     AS 거래건수,
    SUM(금액)    AS 수납금액
FROM 키오스크거래내역
WHERE TRUNC(거래일시) = TRUNC(SYSDATE)
GROUP BY 진료과;


------------------------------------------------------------------------
-- 1-18. V_DAY_INWEON_3  —  당일 진료과별 일원 현황 (3일치 누적)
--   사용처 : 실시간 현황 탭 > 일원 현황 테이블
--   컬럼  : 일자, 진료과, 외래계, 입원계, 퇴원계, 재원계,
--           예방(독감), 예방(AZ,JS,NV), 예방(MD), 예방(FZ), 예방주사계
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_DAY_INWEON_3 AS
SELECT
    기준일                                                         AS 일자,
    진료과명                                                       AS 진료과,
    SUM(CASE WHEN 구분='외래' THEN 인원수 ELSE 0 END)             AS 외래계,
    SUM(CASE WHEN 구분='입원' THEN 인원수 ELSE 0 END)             AS 입원계,
    SUM(CASE WHEN 구분='퇴원' THEN 인원수 ELSE 0 END)             AS 퇴원계,
    SUM(CASE WHEN 구분='재원' THEN 인원수 ELSE 0 END)             AS 재원계,
    SUM(CASE WHEN 구분='예방_독감'     THEN 인원수 ELSE 0 END)    AS "예방(독감)",
    SUM(CASE WHEN 구분='예방_AZ_JS_NV' THEN 인원수 ELSE 0 END)   AS "예방(AZ,JS,NV)",
    SUM(CASE WHEN 구분='예방_MD'       THEN 인원수 ELSE 0 END)    AS "예방(MD)",
    SUM(CASE WHEN 구분='예방_FZ'       THEN 인원수 ELSE 0 END)    AS "예방(FZ)",
    SUM(CASE WHEN 구분 LIKE '예방%'   THEN 인원수 ELSE 0 END)    AS 예방주사계
FROM 일별인원현황
WHERE 기준일 >= TRUNC(SYSDATE) - 2
GROUP BY 기준일, 진료과명;


------------------------------------------------------------------------
-- 1-19. V_DAILY_DEPT_STAT  —  당일 진료과별 구분(외래/입원/퇴원) 집계
--   사용처 : 실시간 현황 탭 > 세부과 집계표
--   조회  : SELECT * ... ORDER BY 진료과명, 구분
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_DAILY_DEPT_STAT AS
SELECT
    기준일,
    진료과명,
    구분,
    인원수
FROM 일별인원현황
WHERE 기준일 = TRUNC(SYSDATE);


------------------------------------------------------------------------
-- 1-20. V_KIOSK_CARD_APPROVAL  —  키오스크 카드 승인 내역
--   사용처 : 카드 매칭 탭 > 병원 측 승인 내역
--   조회  : (직접 조회 없음 — 카드 매칭 로직에서 내부 사용)
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_KIOSK_CARD_APPROVAL AS
SELECT
    TRUNC(거래일시)                            AS 거래일자,
    승인번호,
    RPAD(SUBSTR(카드번호, 1, 6), LENGTH(카드번호)-4, '*')
        || SUBSTR(카드번호, -4)               AS 카드번호,  -- 마스킹
    금액                                       AS 수납금액,
    카드사명                                   AS 카드사,
    단말기ID,
    설치위치,
    거래일시
FROM 키오스크거래내역
WHERE 결제수단 = '카드';


------------------------------------------------------------------------
-- 1-21. V_REGION_DEPT_MONTHLY  —  월별 진료과×지역 환자수
--   사용처 : 지역별 통계 탭 / 진료과 분석 탭
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_REGION_DEPT_MONTHLY AS
SELECT
    TO_CHAR(TRUNC(접수일시, 'MM'), 'YYYYMM') AS 기준월,
    진료과명,
    시도명 || ' ' || 시군구명                  AS 지역,
    COUNT(*)                                   AS 환자수
FROM 외래접수현황 O
JOIN 환자주소현황  A ON O.환자ID = A.환자ID
WHERE 접수일시 >= ADD_MONTHS(TRUNC(SYSDATE,'MM'), -12)
GROUP BY
    TO_CHAR(TRUNC(접수일시,'MM'),'YYYYMM'),
    진료과명,
    시도명 || ' ' || 시군구명;


------------------------------------------------------------------------
-- 1-22. V_REGION_DEPT_DAILY  (= region_dept_daily)
--        일별 진료과×지역 환자수
--   사용처 : 지역별 통계 탭 > 지도 시각화
--   조회  : SELECT 기준일자, 진료과명, 지역, 환자수 ...
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_REGION_DEPT_DAILY AS
SELECT
    TO_CHAR(접수일시, 'YYYYMMDD')            AS 기준일자,
    진료과명,
    시도명 || ' ' || 시군구명                 AS 지역,
    COUNT(*)                                  AS 환자수
FROM 외래접수현황 O
JOIN 환자주소현황  A ON O.환자ID = A.환자ID
WHERE 접수일시 >= TRUNC(SYSDATE) - 90
GROUP BY
    TO_CHAR(접수일시,'YYYYMMDD'),
    진료과명,
    시도명 || ' ' || 시군구명;
-- ※ 코드 내 테이블명은 소문자 'region_dept_daily' 로 참조됨 — 뷰명 대소문자 확인 필요


-- ─────────────────────────────────────────────────────────────────────
-- 1-A. 날짜 지정 조회용 HIST VIEW (FQ_HIST — 날짜 파라미터 쿼리 대응)
-- ─────────────────────────────────────────────────────────────────────

-- 1-A01. V_DAILY_DEPT_STAT_HIST  —  날짜 지정 진료과 집계
CREATE OR REPLACE VIEW JAIN_WM.V_DAILY_DEPT_STAT_HIST AS
SELECT 기준일, 진료과명, 구분, 인원수
FROM 일별인원현황;
-- WHERE TO_CHAR(기준일,'YYYYMMDD') = :d  ← 앱에서 파라미터로 필터링

-- 1-A02. V_WARD_BED_HIST  —  날짜 지정 병상 현황
CREATE OR REPLACE VIEW JAIN_WM.V_WARD_BED_HIST AS
SELECT B.기준일, B.병동명, B.병실번호, B.침상번호, B.사용여부,
       P.환자ID, P.환자명, P.진료과명, P.입원일자,
       B.기준일 - TRUNC(P.입원일자) AS 재원일수
FROM 병상현황이력 B
LEFT JOIN 입원환자이력 P ON B.기준일 = P.기준일
                        AND B.병동명 = P.병동명
                        AND B.병실번호 = P.병실번호
                        AND B.침상번호 = P.침상번호;

-- 1-A03. V_IPD_DEPT_TREND_HIST  —  날짜 범위 입원 추이
CREATE OR REPLACE VIEW JAIN_WM.V_IPD_DEPT_TREND_HIST AS
SELECT 기준일, 진료과명,
       SUM(CASE WHEN 구분='입원' THEN 인원수 ELSE 0 END) AS 입원환자수,
       SUM(CASE WHEN 구분='퇴원' THEN 인원수 ELSE 0 END) AS 퇴원환자수,
       SUM(CASE WHEN 구분='재원' THEN 인원수 ELSE 0 END) AS 재원환자수
FROM 일별인원현황
GROUP BY 기준일, 진료과명;

-- 1-A04. V_DISCHARGE_PIPELINE_HIST  —  날짜 지정 퇴원 파이프라인
CREATE OR REPLACE VIEW JAIN_WM.V_DISCHARGE_PIPELINE_HIST AS
SELECT TRUNC(퇴원예정일) AS 기준일, 병동명, 진료과명, 환자ID,
       퇴원예정시간, 퇴원오더여부, 수납완료여부, 원무확인여부,
       CASE WHEN 수납완료여부='Y' AND 원무확인여부='Y' THEN '퇴원완료'
            WHEN 수납완료여부='Y'                       THEN '수납완료'
            WHEN 퇴원오더여부='Y'                       THEN '퇴원오더'
            ELSE '퇴원예정' END AS 단계
FROM 퇴원진행현황;

-- 1-A05. V_KIOSK_BY_DEPT_HIST  —  날짜 지정 진료과별 키오스크
CREATE OR REPLACE VIEW JAIN_WM.V_KIOSK_BY_DEPT_HIST AS
SELECT TRUNC(거래일시) AS 기준일, 진료과 AS 진료과,
       COUNT(*) AS 거래건수, SUM(금액) AS 수납금액
FROM 키오스크거래내역
GROUP BY TRUNC(거래일시), 진료과;


-- =============================================================================
-- PART 2. 병동 대시보드 VIEW
--         dashboard_app.py (포트 8501) / ui/hospital_dashboard.py
-- =============================================================================

------------------------------------------------------------------------
-- 2-01. V_WARD_DEPT_STAY  —  병동·진료과별 현재 재원 현황
--   조회  : SELECT * ... ORDER BY 재원수 DESC
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_WARD_DEPT_STAY AS
SELECT
    병동명,
    진료과명,
    COUNT(*)                                                          AS 재원수,
    SUM(CASE WHEN TRUNC(입원일자) = TRUNC(SYSDATE) THEN 1 ELSE 0 END) AS 오늘입원수,
    SUM(CASE WHEN 퇴원예정일    = TRUNC(SYSDATE) THEN 1 ELSE 0 END)  AS 오늘퇴원예정수,
    ROUND(AVG(TRUNC(SYSDATE) - TRUNC(입원일자)), 1)                  AS 평균재원일수
FROM 입원환자현황
WHERE 퇴원여부 = 'N'
GROUP BY 병동명, 진료과명;


------------------------------------------------------------------------
-- 2-02. V_WARD_OP_STAT  —  진료과별 수술 통계 (당일)
--   조회  : SELECT * ... ORDER BY 수술건수 DESC
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_WARD_OP_STAT AS
SELECT
    진료과명,
    SUM(CASE WHEN 수술상태='완료'  THEN 1 ELSE 0 END) AS 수술건수,
    SUM(CASE WHEN 수술상태='취소'  THEN 1 ELSE 0 END) AS 취소건수,
    SUM(CASE WHEN 수술상태='예정'  THEN 1 ELSE 0 END) AS 예정건수,
    SUM(CASE WHEN 수술상태='진행중' THEN 1 ELSE 0 END) AS 진행중건수
FROM 수술일정
WHERE TRUNC(수술일시) = TRUNC(SYSDATE)
GROUP BY 진료과명;


------------------------------------------------------------------------
-- 2-03. V_WARD_KPI_TREND  —  최근 7일 입원 KPI 추이
--   조회  : SELECT * ... ORDER BY 기준일
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_WARD_KPI_TREND AS
SELECT
    기준일,
    SUM(CASE WHEN 구분='재원' THEN 인원수 ELSE 0 END) AS 재원수,
    SUM(CASE WHEN 구분='입원' THEN 인원수 ELSE 0 END) AS 입원수,
    SUM(CASE WHEN 구분='퇴원' THEN 인원수 ELSE 0 END) AS 퇴원수,
    ROUND(
        SUM(CASE WHEN 구분='재원' THEN 인원수 ELSE 0 END)
        / NULLIF((SELECT COUNT(*) FROM 병상현황 WHERE 사용여부 IN ('Y','N')), 0) * 100
    , 1)                                               AS 병상점유율
FROM 일별인원현황
WHERE 기준일 >= TRUNC(SYSDATE) - 6
GROUP BY 기준일;


------------------------------------------------------------------------
-- 2-04. V_WARD_YESTERDAY  —  전일 병동별 인원 현황
--   조회  : SELECT * ... ORDER BY 병동명
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_WARD_YESTERDAY AS
SELECT
    병동명,
    SUM(CASE WHEN 구분='재원' THEN 인원수 ELSE 0 END) AS 재원수,
    SUM(CASE WHEN 구분='입원' THEN 인원수 ELSE 0 END) AS 입원수,
    SUM(CASE WHEN 구분='퇴원' THEN 인원수 ELSE 0 END) AS 퇴원수
FROM 일별인원현황
WHERE 기준일 = TRUNC(SYSDATE) - 1
GROUP BY 병동명;


------------------------------------------------------------------------
-- 2-05. V_WARD_DX_TODAY  —  당일 진단 현황 (상위 진단)
--   조회  : SELECT * ... ORDER BY 기준일 DESC, 환자수 DESC
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_WARD_DX_TODAY AS
SELECT
    TRUNC(SYSDATE)  AS 기준일,
    진단코드,
    진단명,
    COUNT(*)        AS 환자수
FROM 입원환자현황
WHERE 퇴원여부 = 'N'
GROUP BY 진단코드, 진단명;


------------------------------------------------------------------------
-- 2-06. V_WARD_DX_TREND  —  7일 진단 추이
--   조회  : SELECT * ... ORDER BY 기준일, 환자수 DESC
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_WARD_DX_TREND AS
SELECT
    기준일,
    진단코드,
    진단명,
    COUNT(*) AS 환자수
FROM 입원이력
WHERE 기준일 >= TRUNC(SYSDATE) - 6
GROUP BY 기준일, 진단코드, 진단명;


------------------------------------------------------------------------
-- 2-07. V_ADMIT_CANDIDATES  —  입원 대기(예약) 환자 현황
--   조회  : SELECT * ... ORDER BY 진료과명, 성별
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_ADMIT_CANDIDATES AS
SELECT
    진료과명,
    성별,
    COUNT(*)                              AS 환자수,
    ROUND(AVG(대기일수), 1)               AS 평균대기일수,
    MIN(입원예약일자)                      AS 최조기예약일
FROM 입원예약현황
WHERE 입원완료여부 = 'N'
GROUP BY 진료과명, 성별;


------------------------------------------------------------------------
-- 2-08. V_OPD_BY_DEPT  —  당일 진료과별 외래 환자 수
--   조회  : SELECT * ... ORDER BY 환자수 DESC
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_OPD_BY_DEPT AS
SELECT
    진료과명,
    COUNT(*)                                                        AS 환자수,
    SUM(CASE WHEN 신환여부='Y' THEN 1 ELSE 0 END)                  AS 신환자수,
    SUM(CASE WHEN 상태='대기'  THEN 1 ELSE 0 END)                  AS 대기수
FROM 외래접수현황
WHERE TRUNC(접수일시) = TRUNC(SYSDATE)
GROUP BY 진료과명;


------------------------------------------------------------------------
-- 2-09. V_OPD_HOURLY_STAT  —  당일 시간대별 외래 현황
--   조회  : SELECT * ... ORDER BY 시간대
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_OPD_HOURLY_STAT AS
SELECT
    TO_CHAR(접수일시, 'HH24') AS 시간대,
    COUNT(*)                  AS 환자수,
    SUM(CASE WHEN 상태='대기' THEN 1 ELSE 0 END) AS 대기수
FROM 외래접수현황
WHERE TRUNC(접수일시) = TRUNC(SYSDATE)
GROUP BY TO_CHAR(접수일시, 'HH24');


------------------------------------------------------------------------
-- 2-10. V_NOSHOW_STAT  —  당일 노쇼 통계 (단일 행)
--   조회  : SELECT * ... WHERE ROWNUM = 1
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_NOSHOW_STAT AS
SELECT
    SUM(CASE WHEN 내원여부='N' AND 예약일 = TRUNC(SYSDATE) THEN 1 ELSE 0 END) AS 노쇼건수,
    ROUND(
        SUM(CASE WHEN 내원여부='N' AND 예약일=TRUNC(SYSDATE) THEN 1 ELSE 0 END)
        / NULLIF(SUM(CASE WHEN 예약일=TRUNC(SYSDATE) THEN 1 ELSE 0 END), 0) * 100
    , 1)                                                                       AS 노쇼율,
    SUM(CASE WHEN 취소여부='Y' AND 예약일=TRUNC(SYSDATE) THEN 1 ELSE 0 END)   AS 취소건수
FROM 외래예약현황;


-- =============================================================================
-- PART 3. 간호 대시보드 VIEW
--         ui/nursing_dashboard.py
-- =============================================================================

------------------------------------------------------------------------
-- 3-01. V_WARD_HIGH_RISK  —  고위험 환자 현황 (낙상·욕창·감염)
--   조회  : SELECT * ... ORDER BY 합계 DESC
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_WARD_HIGH_RISK AS
SELECT
    병동명,
    SUM(CASE WHEN 위험유형='낙상' THEN 1 ELSE 0 END)  AS 낙상위험,
    SUM(CASE WHEN 위험유형='욕창' THEN 1 ELSE 0 END)  AS 욕창위험,
    SUM(CASE WHEN 위험유형='감염' THEN 1 ELSE 0 END)  AS 감염위험,
    COUNT(*)                                           AS 합계
FROM 고위험환자현황
WHERE 퇴원여부 = 'N'
GROUP BY 병동명;


------------------------------------------------------------------------
-- 3-02. V_WARD_INCIDENT  —  사고·이상 사례 보고
--   조회  : SELECT * ... ORDER BY 발생일시 DESC
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_WARD_INCIDENT AS
SELECT
    발생일시,
    병동명,
    환자ID,
    사고유형,
    심각도,
    처리상태,
    보고자,
    보고일시
FROM 사고보고현황
WHERE 발생일시 >= TRUNC(SYSDATE) - 30;


-- =============================================================================
-- PART 4. 진료과 분석 VIEW (신규)
--         ui/panels/dept_analysis.py  (진료과 분석 탭)
--
--  ★ 아래 3개 VIEW는 기존 PATIENT_VISIT_BASE 또는 동등한 기본 테이블이
--    있어야 합니다. 병원 실제 테이블명으로 교체 후 생성하세요.
-- =============================================================================

------------------------------------------------------------------------
-- 4-01. V_DEPT_GENDER_MONTHLY  —  월별 진료과×성별 환자수
--   사용처 : 진료과 분석 탭 > 성별 파이 차트
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_DEPT_GENDER_MONTHLY AS
SELECT
    TO_CHAR(TRUNC(접수일시, 'MM'), 'YYYYMM') AS 기준월,
    진료과명,
    성별,
    COUNT(*)                                  AS 환자수
FROM 외래접수현황
WHERE 접수일시 >= ADD_MONTHS(TRUNC(SYSDATE,'MM'), -24)
GROUP BY
    TO_CHAR(TRUNC(접수일시,'MM'),'YYYYMM'),
    진료과명,
    성별;
-- ※ PATIENT_VISIT_BASE 테이블 사용 시 아래로 교체:
-- FROM JAIN_WM.PATIENT_VISIT_BASE
-- GROUP BY TO_CHAR(기준일,'YYYYMM'), 진료과명, 성별;


------------------------------------------------------------------------
-- 4-02. V_DEPT_AGE_MONTHLY  —  월별 진료과×연령대(10년 단위) 환자수
--   사용처 : 진료과 분석 탭 > 연령대 막대 차트
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_DEPT_AGE_MONTHLY AS
SELECT
    TO_CHAR(TRUNC(접수일시, 'MM'), 'YYYYMM')             AS 기준월,
    진료과명,
    FLOOR(
        MONTHS_BETWEEN(TRUNC(접수일시), 생년월일) / 120
    ) * 10                                               AS 연령대,
    COUNT(*)                                              AS 환자수
FROM 외래접수현황
WHERE 접수일시 >= ADD_MONTHS(TRUNC(SYSDATE,'MM'), -24)
GROUP BY
    TO_CHAR(TRUNC(접수일시,'MM'),'YYYYMM'),
    진료과명,
    FLOOR(MONTHS_BETWEEN(TRUNC(접수일시), 생년월일) / 120) * 10;
-- ※ PATIENT_VISIT_BASE 테이블 사용 시:
-- SELECT TO_CHAR(기준일,'YYYYMM') AS 기준월, 진료과명,
--        FLOOR(MONTHS_BETWEEN(기준일, 생년월일) / 120) * 10 AS 연령대,
--        COUNT(*) AS 환자수
-- FROM JAIN_WM.PATIENT_VISIT_BASE
-- GROUP BY TO_CHAR(기준일,'YYYYMM'), 진료과명,
--          FLOOR(MONTHS_BETWEEN(기준일, 생년월일) / 120) * 10;


------------------------------------------------------------------------
-- 4-03. V_DEPT_CATEGORY_AGE  —  월별 진료과×구분(외래/입원/응급)×연령대
--   사용처 : 진료과 분석 탭 > 구분별 연령대 누적 막대 차트
------------------------------------------------------------------------
CREATE OR REPLACE VIEW JAIN_WM.V_DEPT_CATEGORY_AGE AS
SELECT
    TO_CHAR(TRUNC(기준일시, 'MM'), 'YYYYMM')              AS 기준월,
    진료과명,
    구분,    -- '외래' / '입원' / '응급' / '기타'
    FLOOR(
        MONTHS_BETWEEN(TRUNC(기준일시), 생년월일) / 120
    ) * 10                                                AS 연령대,
    COUNT(*)                                               AS 환자수
FROM (
    -- 외래
    SELECT 접수일시 AS 기준일시, 진료과명, 생년월일, '외래' AS 구분
    FROM 외래접수현황
    UNION ALL
    -- 입원
    SELECT 입원일자 AS 기준일시, 진료과명, 생년월일, '입원' AS 구분
    FROM 입원환자현황
    UNION ALL
    -- 응급
    SELECT 내원일시 AS 기준일시, 진료과명, 생년월일, '응급' AS 구분
    FROM 응급내원현황
)
WHERE 기준일시 >= ADD_MONTHS(TRUNC(SYSDATE,'MM'), -24)
GROUP BY
    TO_CHAR(TRUNC(기준일시,'MM'),'YYYYMM'),
    진료과명,
    구분,
    FLOOR(MONTHS_BETWEEN(TRUNC(기준일시), 생년월일) / 120) * 10;
-- ※ PATIENT_VISIT_BASE 단일 테이블에 구분 컬럼이 있는 경우:
-- SELECT TO_CHAR(기준일,'YYYYMM') AS 기준월, 진료과명, 구분,
--        FLOOR(MONTHS_BETWEEN(기준일, 생년월일) / 120) * 10 AS 연령대,
--        COUNT(*) AS 환자수
-- FROM JAIN_WM.PATIENT_VISIT_BASE
-- GROUP BY TO_CHAR(기준일,'YYYYMM'), 진료과명, 구분,
--          FLOOR(MONTHS_BETWEEN(기준일, 생년월일) / 120) * 10;


-- =============================================================================
-- PART 5. RAG 접근제어 설정 테이블 (AI SQL 생성 화이트리스트)
--         db/oracle_access_config.py
-- =============================================================================

------------------------------------------------------------------------
-- 5-01. RAG_ACCESS_CONFIG 테이블 생성 (없는 경우)
------------------------------------------------------------------------
CREATE TABLE JAIN_WM.RAG_ACCESS_CONFIG (
    TABLE_NAME    VARCHAR2(100)  NOT NULL,    -- 테이블명 (대문자)
    SCHEMA_NAME   VARCHAR2(50)   DEFAULT 'JAIN_WM',  -- 스키마명
    IS_ACTIVE     NUMBER(1)      DEFAULT 1,   -- 1=활성화, 0=비활성화
    MASK_COLUMNS  VARCHAR2(1000) DEFAULT NULL, -- 마스킹 컬럼 목록 (쉼표 구분)
    ALIAS         VARCHAR2(200)  DEFAULT NULL, -- 한국어 별칭 (예: '병실현황')
    DESCRIPTION   VARCHAR2(500)  DEFAULT NULL, -- 관리자 메모
    TABLE_DESC    VARCHAR2(1000) DEFAULT NULL, -- LLM 프롬프트용 테이블 설명
    COLUMN_DESCS  CLOB           DEFAULT NULL, -- LLM 프롬프트용 컬럼 설명 (JSON)
    CONSTRAINT PK_RAG_ACCESS_CONFIG PRIMARY KEY (TABLE_NAME)
);

COMMENT ON TABLE  JAIN_WM.RAG_ACCESS_CONFIG IS 'AI SQL 생성 허용 테이블 화이트리스트';
COMMENT ON COLUMN JAIN_WM.RAG_ACCESS_CONFIG.TABLE_NAME   IS '테이블명 (대문자, PK)';
COMMENT ON COLUMN JAIN_WM.RAG_ACCESS_CONFIG.IS_ACTIVE    IS '활성화 여부 (1=활성, 0=비활성)';
COMMENT ON COLUMN JAIN_WM.RAG_ACCESS_CONFIG.MASK_COLUMNS IS '마스킹 컬럼 목록 (쉼표 구분, 예: 환자명,주민번호)';
COMMENT ON COLUMN JAIN_WM.RAG_ACCESS_CONFIG.TABLE_DESC   IS 'LLM 프롬프트용 한국어 테이블 설명';
COMMENT ON COLUMN JAIN_WM.RAG_ACCESS_CONFIG.COLUMN_DESCS IS 'LLM 프롬프트용 컬럼 설명 JSON {"컬럼명":"설명"}';


------------------------------------------------------------------------
-- 5-02. RAG_ACCESS_CONFIG 기본 등록 데이터
--       (VIEW 명칭으로 등록하여 AI SQL 생성 허용 범위 지정)
------------------------------------------------------------------------
INSERT INTO JAIN_WM.RAG_ACCESS_CONFIG
    (TABLE_NAME, SCHEMA_NAME, IS_ACTIVE, ALIAS, TABLE_DESC)
VALUES
    ('V_OPD_KPI',           'JAIN_WM', 1, '외래KPI',           '당일 외래 KPI 단일 행 (외래환자수/신환/수납금액/미수금)'),
    ('V_OPD_DEPT_STATUS',   'JAIN_WM', 1, '진료과대기현황',    '당일 진료과별 대기/진료중/완료/평균대기시간'),
    ('V_KIOSK_STATUS',      'JAIN_WM', 1, '키오스크현황',      '당일 키오스크별 상태/거래건수/수납금액'),
    ('V_FINANCE_TODAY',     'JAIN_WM', 1, '당일수납현황',      '당일 보험유형별 수납건수/금액/미수금'),
    ('V_FINANCE_TREND',     'JAIN_WM', 1, '30일수납추이',      '최근 30일 일별 수납금액/미수금 추이'),
    ('V_FINANCE_BY_DEPT',   'JAIN_WM', 1, '진료과별수납',      '당일 진료과별 수납금액/미수금'),
    ('V_OVERDUE_STAT',      'JAIN_WM', 1, '미수금현황',        '미수금 연령구간별 건수/금액/비율'),
    ('V_MONTHLY_OPD_DEPT',  'JAIN_WM', 1, '월별외래현황',      '최근 13개월 진료과별 외래/신환/구환/신환비율'),
    ('V_REGION_DEPT_MONTHLY','JAIN_WM', 1, '지역별월통계',     '월별 진료과×지역 환자수'),
    ('V_REGION_DEPT_DAILY', 'JAIN_WM', 1, '지역별일통계',     '일별 진료과×지역 환자수 (90일)'),
    ('V_WARD_DEPT_STAY',    'JAIN_WM', 1, '병동재원현황',      '현재 병동별/진료과별 재원수/입원수/퇴원수'),
    ('V_WARD_BED_DETAIL',   'JAIN_WM', 1, '병상세부현황',      '현재 병동/병실/침상별 환자 배치'),
    ('V_LOS_DIST_DEPT',     'JAIN_WM', 1, '재원일수분포',      '현재 진료과별 재원일수 구간 분포'),
    ('V_OPD_DEPT_TREND',    'JAIN_WM', 1, '7일외래추이',       '최근 7일 진료과별 외래/신환/구환 추이');

COMMIT;


-- =============================================================================
-- PART 6. SELECT 권한 GRANT
--         운영 계정(rag_readonly)에 조회 권한 부여
-- =============================================================================

-- ── 원무 대시보드 VIEW ────────────────────────────────────────────────
GRANT SELECT ON JAIN_WM.V_OPD_KPI                 TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_OPD_DEPT_STATUS         TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_KIOSK_STATUS             TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_WARD_ROOM_DETAIL         TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_WARD_BED_DETAIL          TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_DISCHARGE_PIPELINE       TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_FINANCE_TODAY            TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_FINANCE_TREND            TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_FINANCE_BY_DEPT          TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_FINANCE_BY_INS           TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_OVERDUE_STAT             TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_OPD_DEPT_TREND           TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_IPD_DEPT_TREND           TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_LOS_DIST_DEPT            TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_MONTHLY_OPD_DEPT         TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_KIOSK_COUNTER_TREND      TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_KIOSK_BY_DEPT            TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_KIOSK_CARD_APPROVAL      TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_DAY_INWEON_3             TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_DAILY_DEPT_STAT          TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_REGION_DEPT_MONTHLY      TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_REGION_DEPT_DAILY        TO rag_readonly;

-- ── 날짜 지정 HIST VIEW ──────────────────────────────────────────────
GRANT SELECT ON JAIN_WM.V_DAILY_DEPT_STAT_HIST     TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_WARD_BED_HIST            TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_IPD_DEPT_TREND_HIST      TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_DISCHARGE_PIPELINE_HIST  TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_KIOSK_BY_DEPT_HIST       TO rag_readonly;

-- ── 병동 대시보드 VIEW ───────────────────────────────────────────────
GRANT SELECT ON JAIN_WM.V_WARD_DEPT_STAY           TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_WARD_OP_STAT             TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_WARD_KPI_TREND           TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_WARD_YESTERDAY           TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_WARD_DX_TODAY            TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_WARD_DX_TREND            TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_ADMIT_CANDIDATES         TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_OPD_BY_DEPT             TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_OPD_HOURLY_STAT         TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_NOSHOW_STAT             TO rag_readonly;

-- ── 간호 대시보드 VIEW ───────────────────────────────────────────────
GRANT SELECT ON JAIN_WM.V_WARD_HIGH_RISK           TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_WARD_INCIDENT            TO rag_readonly;

-- ── 진료과 분석 신규 VIEW ────────────────────────────────────────────
GRANT SELECT ON JAIN_WM.V_DEPT_GENDER_MONTHLY      TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_DEPT_AGE_MONTHLY         TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_DEPT_CATEGORY_AGE        TO rag_readonly;

-- ── RAG 접근제어 테이블 ──────────────────────────────────────────────
GRANT SELECT ON JAIN_WM.RAG_ACCESS_CONFIG          TO rag_readonly;


-- =============================================================================
-- VIEW 생성 확인 쿼리
-- =============================================================================
/*
SELECT VIEW_NAME, STATUS
FROM ALL_VIEWS
WHERE OWNER = 'JAIN_WM'
  AND VIEW_NAME LIKE 'V_%'
ORDER BY VIEW_NAME;

-- 기대 결과: STATUS = 'VALID' (INVALID 이면 기본 테이블명 매핑 오류)
*/

-- END OF FILE
