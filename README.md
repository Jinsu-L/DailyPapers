# DailyPapers

[![Daily Run](https://github.com/Jinsu-L/DailyPapers/actions/workflows/daily_run.yml/badge.svg)](https://github.com/Jinsu-L/DailyPapers/actions/workflows/daily_run.yml)

DailyPapers는 Arxiv에서 매일 새로운 논문을 수집하고, LLM을 사용하여 관심 분야와의 관련성을 평가하고, T.A.R.G.E.T. 프레임워크에 따라 요약하여 마크다운 리포트를 생성하는 자동화 시스템입니다.

## 주요 기능

-   **Arxiv 크롤링**: 특정 카테고리(예: `cs.IR`, `cs.CL`)의 최신 논문을 가져옵니다.
-   **2단계 스코어링**:
    1.  **키워드 기반 필터링**: 사용자가 정의한 키워드로 1차 필터링을 수행합니다.
    2.  **LLM 기반 평가**: Groq API를 사용하여 사용자의 관심사와 논문의 관련성을 평가하고 점수를 매깁니다.
-   **LLM 기반 요약**: 점수가 높은 상위 논문에 대해 T.A.R.G.E.T. 프레임워크를 사용한 요약을 생성합니다.
-   **자동화된 리포트**: 분석 결과를 날짜별 마크다운 파일로 생성하고, 별도의 리포지토리(`DailyIR`)에 자동으로 푸시합니다.

## 프로젝트 구조

```
.
├── .github/workflows/
│   └── daily_run.yml       # GitHub Actions 워크플로우
├── configs/
│   ├── config.yaml         # 시스템 전반의 설정 파일
│   ├── prompt.json         # LLM 프롬프트 템플릿
│   └── sample_papers.json  # 로컬 테스트용 샘플 데이터
├── src/
│   ├── crawler.py
│   ├── classifier.py
│   ├── summarizer.py
│   └── ... (기타 소스 코드)
├── data/                   # 크롤링된 데이터 저장
├── logs/                   # 실행 로그 저장
├── reports/                # 생성된 마크다운 리포트 저장
├── .gitignore
├── main.py                 # 메인 실행 스크립트
├── requirements.txt        # Python 패키지 의존성
└── README.md
```

## 로컬 실행 방법

### 요구사항
-   Python 3.9 이상
-   Git

### 설정 단계
1.  **리포지터리 클론:**
    ```bash
    git clone https://github.com/Jinsu-L/DailyPapers.git
    cd DailyPapers
    ```

2.  **가상 환경 생성 및 활성화:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # macOS/Linux
    # venv\Scripts\activate    # Windows
    ```

3.  **의존성 설치:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **환경 변수 설정:**
    LLM(Groq)을 사용하려면 API 키가 필요합니다. 터미널에서 환경 변수를 설정하세요.
    ```bash
    export GROQ_API_KEY="your_groq_api_key_here"
    ```

5.  **실행:**
    -   **어제 날짜의 논문**을 분석하려면 (기본 동작):
        ```bash
        python main.py
        ```
    -   **특정 날짜 기준 1일치 논문**을 분석하려면 (`--date` 플래그 사용):
        ```bash
        python main.py --date 2024-07-15
        ```
    -   **특정 날짜 기준 3일치 논문**을 분석하려면 (`--days` 플래그 사용):
        ```bash
        python main.py --date 2024-07-15 --days 3
        ```

결과는 `reports/`, `data/crawled/`, `logs/` 디렉토리에 생성됩니다.

## 논문 리포트 생성 배치

GitHub Actions를 사용하여 논문을 수집하고 처리합니다.

### ⚙️ Automation Schedule

크롤러 실행은 arXiv의 논문 공개 시간에 맞춰 새 논문을 수집합니다. 모든 시간은 한국 표준시(KST) 기준입니다.

-   **실행 시간**: 월요일-금요일, 오전 10:00 (KST) / 오전 01:00 (UTC)
-   **미실행일**: 주말(토, 일)에는 arXiv에서 새로운 논문이 발표되지 않으므로 실행되지 않습니다.

#### Arxiv 논문 공개 및 크롤링 스케줄

| Submission Period (ET)        | Publication Time (ET) | Publication Time (KST) | Crawler Run Day (KST) | Days to Fetch |
|-------------------------------|-----------------------|------------------------|-------------------------|---------------|
| Thursday 14:00 - Friday 14:00 | Sunday 20:00          | Monday 09:00 AM        | ✅ **Monday Morning**     | 1 day (Fri)   |
| Friday 14:00 - Monday 14:00   | Monday 20:00          | Tuesday 09:00 AM       | ✅ **Tuesday Morning**    | 3 days (weekend)|
| Monday 14:00 - Tuesday 14:00  | Tuesday 20:00         | Wednesday 09:00 AM     | ✅ Wednesday Morning    | 1 day         |
| Tuesday 14:00 - Wednesday 14:00| Wednesday 20:00       | Thursday 09:00 AM      | ✅ Thursday Morning   | 1 day         |
| Wednesday 14:00 - Thursday 14:00| Thursday 20:00        | Friday 09:00 AM        | ✅ Friday Morning     | 1 day         |

> ET(미국 동부 시간)와 KST(한국 표준시) 간의 변환에는 서머타임 적용 여부에 따라 시차가 달라질 수 있습니다 (+13 또는 +14시간). 워크플로우는 이 스케줄을 자동으로 처리합니다.

### 자동화 설정 (포크하여 사용하는 경우)

1.  이 리포지토리를 포크(Fork)합니다.
2.  포크한 리포지토리의 `Settings` > `Secrets and variables` > `Actions`로 이동하여 다음 두 가지 시크릿을 등록합니다.
    -   `GROQ_API_KEY`: Groq API 키.
    -   `PAT`: 리포트 결과물을 `DailyIR` 리포지토리(또는 원하는 다른 리포지토리)에 푸시할 수 있는 권한을 가진 Personal Access Token.