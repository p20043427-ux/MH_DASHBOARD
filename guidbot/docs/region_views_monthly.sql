-- =============================================================================
-- V_REGION_DEPT_MONTHLY : 진료과별 월별 지역 고유 환자수 (최근 12개월)
-- 목적  : finance_dashboard.py _tab_region 월별 비교 분석
-- 대상  : JAIN_WM 스키마 DBA 계정으로 실행
--
-- [수정 이유]
--   기존 뷰는 두 가지 결함으로 환자수가 실제보다 N배 과다 계산됨:
--
--   결함 1: WMNAM01_ADDINFO 직접 JOIN
--     → 환자 1명당 주소 이력 N개 → WMNAM03 방문 × 주소이력 수만큼 행 증폭
--     → 해결: JOIN 제거, 우편번호 취득을 서브쿼리로 전환 (ROWNUM=1 보장)
--
--   결함 2: COUNT(*) = 방문 행 수
--     → 같은 환자가 3번 방문 시 3으로 집계 (지역별 고유 환자수 아님)
--     → 해결: COUNT(DISTINCT NM.W01IDNOA) = 고유 환자 수
--
-- [컬럼]
--   기준월  CHAR(6)   YYYYMM
--   진료과명 VARCHAR2  진료과 코드 (W03KWA)
--   지역    VARCHAR2  시도+시구 (예: 부산광역시 부산진구) / 주소 미상시 '지역미상'
--   환자수  NUMBER    월간 고유 환자 수 (COUNT DISTINCT)
-- =============================================================================

CREATE OR REPLACE VIEW JAIN_WM.V_REGION_DEPT_MONTHLY AS
SELECT
    기준월,
    진료과명,
    지역,
    COUNT(DISTINCT 환자ID) AS 환자수   -- 고유 환자 수 (방문 횟수 아님)
FROM (
    SELECT
        SUBSTR(W.W03LWDAT, 1, 6)  AS 기준월,
        W.W03KWA                  AS 진료과명,
        NM.W01IDNOA               AS 환자ID,
        NVL(
            -- WMNAM01_ADDINFO 를 서브쿼리로 접근 → 행 증폭 방지
            (SELECT NVL(P.SIDO || ' ' || P.SIGU, '지역미상')
               FROM JAIN_WM.POSTNO P
              WHERE P.POSTNO = (
                        SELECT TRIM(A.WA01RPSTNO)
                          FROM JAIN_WM.WMNAM01_ADDINFO A
                         WHERE A.WA01IDNOA = NM.W01IDNOA
                           AND ROWNUM = 1     -- 최신/첫번째 주소 1건만
                    )
                AND ROWNUM = 1),
            '지역미상'
        ) AS 지역
    FROM JAIN_WM.WMNAM01 NM
    JOIN JAIN_WM.WMNAM03 W ON NM.W01IDNOA = W.W03IDNOA
    WHERE W.W03LWDAT >= TO_CHAR(ADD_MONTHS(SYSDATE, -12), 'YYYYMMDD')
      AND W.W03LWDAT <= TO_CHAR(SYSDATE, 'YYYYMMDD')
)
GROUP BY 기준월, 진료과명, 지역;


GRANT SELECT ON JAIN_WM.V_REGION_DEPT_MONTHLY TO RAG_READONLY;


-- =============================================================================
-- [검증 쿼리] 뷰 생성 후 아래로 PD 3월 직접 쿼리와 비교
-- 직접 쿼리 결과: 부산진구 1,449명 → 뷰 결과와 비교
-- =============================================================================
--
-- 1. 뷰 결과 (수정 후)
-- SELECT 지역, 환자수
--   FROM JAIN_WM.V_REGION_DEPT_MONTHLY
--  WHERE 기준월 = '202603' AND 진료과명 = 'PD'
--  ORDER BY 환자수 DESC;
--
-- 2. 원본 직접 쿼리 (COUNT DISTINCT — 기준값)
-- SELECT 지역, COUNT(DISTINCT NM.W01IDNOA) AS 환자수
--   FROM JAIN_WM.WMNAM01 NM
--   JOIN JAIN_WM.WMNAM03 W ON NM.W01IDNOA = W.W03IDNOA
--   JOIN (SELECT DISTINCT WA01IDNOA,
--                FIRST_VALUE(TRIM(WA01RPSTNO)) OVER (PARTITION BY WA01IDNOA ORDER BY ROWNUM) AS POSTNO
--           FROM JAIN_WM.WMNAM01_ADDINFO) A ON NM.W01IDNOA = A.WA01IDNOA
--   JOIN JAIN_WM.POSTNO P ON P.POSTNO = A.POSTNO
--  WHERE W.W03LWDAT BETWEEN '20260301' AND '20260331'
--    AND W.W03KWA   = 'PD'
-- GROUP BY P.SIDO || ' ' || P.SIGU
-- ORDER BY 환자수 DESC;
