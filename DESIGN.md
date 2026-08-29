# RE:PLAN 설계

## Version 0.3 디자인 및 상호작용

- 브랜드 문구: `RE:PLAN` / “학습 계획을 만들고 디벨롭해주는 나만의 캘린더”
- 참고 이미지의 큰 검정 워드마크, 넓은 여백, 라이트블루 곡면 색상을 제품 화면에 맞게 적용한다.
- 월간은 시험 진행 패널과 나란히, 주간은 7일 요약, 일간은 06:00~24:00 전체를 한 화면에 표시한다.
- 일간 블록 본체를 드래그하면 이동하고 아래 손잡이를 드래그하면 길이가 바뀐다. 서버가 시간 겹침을 최종 거부한다.
- 재계획 후 실제량과 예정량의 차이, 현재 속도 예상 회독, 목표 유지 또는 조정 권고를 표시한다.

## 1. 제품 목표와 비목표

### 목표

사용자가 계획보다 적게 공부했을 때 그 차이를 즉시 감지하고, 시험 전 남은 전체 범위와 가용 시간을 현실적으로 재분배한다. 재계획 결과는 설명 가능하고 같은 입력에 대해 재현 가능해야 한다.

### MVP 비목표

- 자연어 채팅 기반 일정 등록
- 감정·컨디션 기반 복잡한 체크인
- 푸시 알림과 소셜 기능
- LLM이 계산 결과를 임의로 결정하는 방식
- 완벽한 시간표 최적화 및 다중 사용자 협업

## 2. 핵심 사용자 여정

```text
고정 일정 등록
      ↓
시험·범위·목표 회독 등록
      ↓
가용 시간 산출 → 최초 계획 생성 → 캘린더 표시
                              ↓
                완료 / 일부 완료 / 미완료
                              ↓
                  실제 완료 범위 저장
                              ↓
        남은 범위·기간·수행 능력 재산정
                              ↓
                미래 계획 전체 교체
                              ↺
```

## 3. 도메인 모델

### User

- `id`
- `timezone` (MVP 기본값: `Asia/Seoul`)
- `defaultDailyStudyMinutes`

### CalendarEvent

- `id`, `userId`
- `title`
- `type`: `CLASS | WORK | APPOINTMENT | EXAM | OTHER`
- `startsAt`, `endsAt`
- `recurrenceRule` (선택)
- `blocksStudyTime`: 고정 일정이면 `true`

### Exam

- `id`, `userId`
- `subject`, `examAt`
- `targetPasses`
- `status`: `ACTIVE | COMPLETED | ARCHIVED`
- `strategy`: `FULL_PASSES | FULL_PLUS_PRIORITY_REVIEW`

### StudyScope

범위 단위의 차이를 흡수하기 위해 시작·끝 값을 숫자로 정규화하고 표시용 단위를 보존한다.

- `id`, `examId`
- `label`: 예) `Ch.1~8`, `1~240p`
- `unit`: `PAGE | CHAPTER | ITEM | CUSTOM`
- `startValue`, `endValue`
- `priority`: `NORMAL | HIGH`

MVP에서는 한 시험에 하나의 연속 범위를 우선 지원한다. 챕터처럼 각 단위의 분량이 크게 다르면 사용자가 단위별 예상 학습 시간을 추가하는 확장 구조를 둔다.

### StudyPlanVersion

재계획 전후를 시연하고 추적하기 위한 버전이다. 과거 계획을 덮어쓰지 않는다.

- `id`, `examId`, `version`
- `reason`: `INITIAL | PARTIAL | MISSED | SCHEDULE_CHANGED | MANUAL`
- `createdAt`
- `assumptionsJson`
- `isActive`

### StudyTask

- `id`, `planVersionId`, `examId`
- `date`, `plannedMinutes`
- `passNumber`
- `scopeStart`, `scopeEnd`, `unit`
- `status`: `PLANNED | COMPLETED | PARTIAL | MISSED | SUPERSEDED`

### StudyLog

- `id`, `studyTaskId`, `userId`
- `result`: `COMPLETED | PARTIAL | MISSED`
- `actualScopeStart`, `actualScopeEnd`
- `actualMinutes` (선택이지만 권장)
- `recordedAt`

`PARTIAL`은 실제 종료 지점이 필수이고 `MISSED`는 완료량 0으로 저장한다. 확정된 과거 로그는 재계획 시 변경하지 않는다.

### PerformanceProfile

- `userId`
- `sampleCount`
- `effectiveUnitsPerHour`
- `completionRatio`
- `busyDayMultiplier`, `freeDayMultiplier`
- `updatedAt`

표본이 적을 때는 기본값과 실제 데이터의 가중 평균을 사용해 극단적인 계획 변화를 막는다.

## 4. 재계획 엔진

### 설계 원칙

핵심 배분은 OpenAI Responses API가 생성한다. 시험·진도·고정 일정을 입력으로 제공하고 JSON Schema Structured Outputs로 날짜, 회독, 범위, 추천 시작·종료 시간을 받는다. 백엔드는 날짜·범위·총량·시간 순서를 다시 검증한 결과만 저장한다.

### 입력

- 현재 시각과 시험 시각
- 완료된 실제 범위와 회독별 남은 범위
- 남은 날짜의 고정 일정
- 날짜별 학습 가능 시간
- 목표 회독 수
- 수행 프로필(실제 단위/시간, 완료율, 바쁜 날 보정치)
- 우선 범위(선택)

### 계산 단계

1. 체크인 로그를 반영해 회독별 완료 구간을 확정한다.
2. 시험 전까지 날짜별 가용 시간을 계산한다.
3. `가용 시간 × 실제 처리 속도 × 일정 밀도 보정치`로 날짜별 현실적 수용량을 구한다.
4. 남은 목표량과 총 수용량을 비교해 목표 달성 가능성을 산출한다.
5. 달성 가능하면 회독 순서를 지키며 날짜별 수용량 비율로 범위를 배분한다.
6. 불가능하면 `전체 1회독 우선 → 중요 범위 추가 복습` 전략으로 전환 후보를 만든다.
7. 오늘 이전의 확정 로그는 보존하고 미래의 활성 작업만 새 계획 버전으로 교체한다.
8. 재계획 전후 요약과 변경 이유를 저장한다.

### 기본식

```text
availableMinutes(day) = studyWindow - blockingEvents - buffer
estimatedCapacity(day) = availableMinutes / 60
                       × effectiveUnitsPerHour
                       × dayTypeMultiplier
                       × conservativeFactor

currentPasses = totalCompletedUnitsAcrossPasses / totalScopeUnits
forecastPasses = currentPasses
               + sum(estimatedCapacityUntilExam) / totalScopeUnits
```

`conservativeFactor`는 초기에는 0.8처럼 보수적으로 두고 데이터가 쌓이면 사용자의 최근 완료율로 갱신한다. 최근 기록에는 더 높은 가중치를 주되, 한 번의 실패가 계획 전체를 과도하게 흔들지 않도록 상·하한을 둔다.

### 불변조건

- 시험 시각 이후에 공부 작업을 만들지 않는다.
- 고정 일정과 겹치는 시간량을 배정하지 않는다.
- 동일 회독의 범위를 중복하거나 빠뜨리지 않는다.
- 완료로 확정된 실제 범위를 미래 계획에 다시 배정하지 않는다.
- 미래 계획 총량은 남은 목표량과 일치한다. 단, 불가능한 경우에는 축소 전략과 부족량을 명시한다.
- 최소·최대 일일 학습량과 휴식 버퍼를 지킨다.

### 부분 완료 예시

```text
기존: 9/10 1~40p, 9/11 41~80p, 9/12 81~120p
실제: 9/10 1~25p 완료

처리:
- 1~25p를 확정 완료
- 26~120p를 남은 1회독 범위로 계산
- 9/11 이후 가용 시간과 갱신된 실제 속도로 전체 재배분
- 새 버전의 작업을 생성하고 기존 미래 작업은 SUPERSEDED 처리
```

## 5. 목표 달성 가능성과 전략 전환

표시 지표는 `현재 회독`, `목표 회독`, `현재 속도 기준 예상 회독`, `부족 예상량`이다.

- `forecast >= target`: 목표 유지
- `forecast < target`: 경고 및 현실적 계획 제시
- 전체 목표가 불가능한 경우: 전체 범위 1회독을 먼저 보장하고 `HIGH` 범위에 남는 수용량을 배정

사용자의 명시적 동의 없이 목표 자체를 조용히 낮추지 않는다. 엔진은 추천 전략과 예상 결과를 보여주며, MVP에서는 사용자가 적용을 확인하도록 한다.

## 6. 화면 설계

### 대시보드 / 캘린더

- 월간 캘린더에 일정을 한 줄로 표시하고 날짜 선택 시 06:00~24:00 일간 타임테이블로 전환
- 오늘의 공부 카드에서 즉시 수행 체크
- 활성 시험별 D-day, 현재/예상/목표 회독 표시

### 시험 등록

- 과목명, 시험 일시, 범위 단위, 시작·끝, 목표 회독
- 계획 생성 전 가용 시간과 예상 달성 가능성 미리보기

### 수행 체크인

- `완료`, `일부 완료`, `미완료`
- 일부 완료 시 실제 종료 지점 필수
- 실제 학습 시간은 선택 입력

### 재계획 결과

- 변경 이유
- 이전 계획과 새 계획의 요약 비교
- 예상 회독 변화
- 불가능한 목표일 경우 대안 전략

## 7. API 초안

- `POST /api/calendar-events`
- `GET /api/calendar-events?from=&to=`
- `POST /api/exams`
- `POST /api/exams/:examId/plans` — 최초 계획 생성
- `GET /api/exams/:examId/plan`
- `POST /api/study-tasks/:taskId/check-ins` — 수행 저장 후 재계획 트리거
- `POST /api/exams/:examId/replan` — 일정 변경 또는 수동 재계획
- `GET /api/exams/:examId/progress`
- `GET /api/performance-profile`

체크인 저장과 새 계획 버전 활성화는 하나의 트랜잭션으로 처리해 중간 상태 노출을 막는다. 동일 요청의 중복 제출을 막기 위한 idempotency key를 둔다.

## 8. 기술 구성 제안

확정된 MVP 기술 구성:

- 프런트엔드: React + TypeScript + Vite
- UI: 접근 가능한 컴포넌트 라이브러리 + 캘린더 라이브러리
- 백엔드: Python + FastAPI
- 데이터베이스: SQLite
- ORM / 마이그레이션: SQLAlchemy + Alembic
- 테스트: Vitest + pytest + 핵심 흐름 E2E 1개
- 패키지 관리: npm + pip
- 기본 시간대: `Asia/Seoul`

재계획 엔진은 UI·DB와 분리된 순수 함수 모듈로 작성해 예제 입력으로 결과를 즉시 검증할 수 있게 한다.

## 9. AI 활용 설계

AI는 핵심 로직을 감추는 장식이 아니라 입력과 설명의 품질을 높이는 역할을 맡는다.

- `Ch.1~8`, `1~240p` 같은 자연어 범위를 구조화한 뒤 사용자 확인
- 재계획 이유와 목표 달성 위험을 쉬운 문장으로 설명
- 목표가 불가능할 때 우선 범위를 이용한 대안 전략 설명
- 개발 단계에서는 재계획 규칙의 경계 사례와 테스트 데이터 생성에 활용

AI 출력은 JSON Schema와 Pydantic 검증을 통과해야 한다. 백엔드는 시험 기간, 범위, 총 학습량, 시간 순서를 추가 검증한다. OpenAI 키가 없거나 호출이 실패하면 기존 계획을 임의로 변경하지 않고 사용자에게 설정 또는 재시도 오류를 보여준다.

## 10. 검증 기준

### 필수 단위 테스트

- 고정 일정이 많은 날에 적은 양이 배정된다.
- 일부 완료 범위가 다시 배정되지 않는다.
- 미완료 후 미래 계획 전체가 새 버전으로 변경된다.
- 시험일 이후 작업이 생성되지 않는다.
- 목표량이 수용량보다 클 때 축소 전략과 부족량이 반환된다.
- 여러 번 재계획해도 범위 중복·누락이 없다.

### 핵심 E2E 수용 기준

고정 일정과 시험을 등록해 계획을 만든 뒤 오늘 작업을 일부 완료 처리하면, 실제 완료 범위가 저장되고 미래 작업의 범위 또는 분량이 변경되며 현재·예상 회독률과 계획 버전이 함께 갱신되어야 한다.

## 11. 주요 위험과 대응

- 범위 단위가 제각각임: MVP는 연속 숫자 범위를 우선하고 단위를 보존한다.
- 실제 학습 시간을 입력하지 않음: 완료 단위와 배정 시간으로 추정하되 신뢰도를 낮춘다.
- 초기 데이터 부족: 보수적 기본값과 사용자 입력값을 혼합하고 표본 수를 표시한다.
- 과도한 재계획으로 혼란: 하루 체크인 후 한 번 재계획하고 변경 요약을 제공한다.
- 계획이 불가능한데 양을 밀어 넣음: 수용량 상한을 지키고 부족량과 대안을 명시한다.
