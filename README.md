# DailyPapers

DailyPapers는 Arxiv에서 매일 새로운 논문을 수집하고, LLM을 사용하여 관심 분야와의 관련성을 평가하고, T.A.R.G.E.T. 프레임워크에 따라 요약하여 마크다운 리포트를 생성하는 자동화된 시스템입니다.

## 주요 기능

-   **일일 Arxiv 크롤링**: 특정 카테고리(예: `cs.IR`)의 최신 논문을 매일 자동으로 가져옵니다.
-   **2단계 스코어링**:
    1.  **키워드 기반 필터링**: 사용자가 정의한 키워드로 1차 필터링을 수행합니다.
    2.  **LLM 기반 평가**: Groq API를 사용하여 사용자의 관심사와 논문의 관련성을 평가하고 점수를 매깁니다.
-   **LLM 기반 요약**: 점수가 높은 상위 논문에 대해 T.A.R.G.E.T. 프레임워크를 사용한 심층 요약을 생성합니다.
-   **리포트 생성**: 분석 결과를 매일 날짜별 마크다운 파일로 생성합니다.
-   **Docker 및 GitHub Actions**: 전체 프로세스가 Docker 컨테이너 내에서 실행되며, GitHub Actions를 통해 매주 월-금요일에 자동으로 실행되도록 설정되어 있습니다.

## 프로젝트 구조

```
.
├── configs/
│   ├── prompt.json         # LLM에 사용될 프롬프트 템플릿
│   └── sample_papers.json  # 로컬 테스트용 샘플 데이터
├── src/
│   ├── crawler.py          # Arxiv 크롤러
│   ├── classifier.py       # 키워드 및 LLM 기반 분류기
│   ├── summarizer.py       # T.A.R.G.E.T. 요약기
│   ├── reporter.py         # 마크다운 리포트 생성기
│   ├── pdf_parser.py       # PDF 텍스트 추출 유틸리티
│   └── llm_services.py     # LLM 연동 기본 서비스
├── .github/workflows/
│   └── daily_run.yml       # GitHub Actions 워크플로우
├── .gitignore
├── config.yaml             # 전체 시스템 설정 파일
├── Dockerfile              # Docker 이미지 빌드 파일
├── main.py                 # 메인 실행 스크립트
├── requirements.txt        # Python 패키지 의존성
└── README.md
```

## 설정 방법

### 1. 로컬 환경에서 실행

#### 요구사항
-   Python 3.9 이상
-   Git

#### 설정 단계
1.  **리포지터리 클론:**
    ```bash
    git clone <your-repository-url>
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
    이 키는 현재 터미널 세션에서만 유효합니다. 영구적으로 설정하려면 `.zshrc`, `.bash_profile` 등에 추가하세요.

5.  **실행:**
    -   **오늘 날짜의 논문**을 분석하려면:
        ```bash
        python main.py
        ```
    -   **특정 날짜의 논문**을 분석하려면 (`--date` 플래그 사용):
        ```bash
        python main.py --date 2025-06-18
        ```

결과는 `reports/`와 `data/crawled/` 디렉토리에 생성됩니다.

### 2. Docker로 실행

Docker가 설치되어 있어야 합니다.

1.  **Docker 이미지 빌드:**
    ```bash
    docker build -t daily-papers .
    ```

2.  **Docker 컨테이너 실행:**
    `--env` 플래그를 사용하여 Groq API 키를 컨테이너에 전달해야 합니다.
    ```bash
    docker run --rm --env GROQ_API_KEY="your_groq_api_key_here" daily-papers python main.py --date 2025-06-18
    ```
    컨테이너 내에서 실행되므로, 결과 파일은 컨테이너 내부에 생성됩니다. 로컬에 저장하려면 볼륨 마운트를 사용해야 합니다.
    ```bash
    docker run --rm \
      --env GROQ_API_KEY="your_groq_api_key_here" \
      -v $(pwd)/data:/app/data \
      -v $(pwd)/reports:/app/reports \
      -v $(pwd)/logs:/app/logs \
      daily-papers python main.py --date 2025-06-18
    ```

## GitHub Actions를 통한 자동화

이 프로젝트는 `.github/workflows/daily_run.yml` 워크플로우를 통해 자동으로 실행되도록 설정되어 있습니다.

-   **실행 시점**: 매주 월요일부터 금요일까지, 01:00 UTC에 실행됩니다.
-   **수동 실행**: GitHub 리포지터리의 'Actions' 탭에서 `workflow_dispatch` 이벤트를 통해 수동으로 실행할 수도 있습니다.

자동화를 위해 다음 **리포지터리 시크릿**을 설정해야 합니다:
-   `Settings` > `Secrets and variables` > `Actions` 로 이동
-   `New repository secret` 클릭
-   **`GROQ_API_KEY`**: 여기에 Groq API 키를 추가합니다.

(향후 결과 리포지터리로 푸시하는 기능이 추가되면 `RESULTS_REPO_PAT` 등의 시크릿도 필요합니다.) 