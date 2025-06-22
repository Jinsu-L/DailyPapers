import yaml
import os
import json
import logging
import argparse
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from src.crawler import ArxivCrawler
from src.classifier import KeywordClassifier, LLMClassifier
from src.pdf_parser import download_and_extract_pdf_text
from src.summarizer import CSPaperSummarizer
from src.reporter import MarkdownReporter

# __file__을 기준으로 스크립트의 절대 경로와 프로젝트 루트 경로를 계산
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = SCRIPT_DIR # 이제 main.py가 루트에 있으므로 SCRIPT_DIR가 ROOT가 됩니다.

def setup_logging(config: dict):
    """로깅 설정 초기화"""
    log_config = config.get('logging', {})
    log_level = log_config.get('level', 'INFO').upper()
    log_file_path = os.path.join(PROJECT_ROOT, log_config.get('file', 'logs/app.log'))

    # 로그 디렉토리 생성
    os.makedirs(os.path.dirname(log_file_path), exist_ok=True)

    # 로거 설정
    logger = logging.getLogger()
    logger.setLevel(log_level)
    
    # 기존 핸들러 제거
    if logger.hasHandlers():
        logger.handlers.clear()

    # 포맷터 설정
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # 콘솔 핸들러
    ch = logging.StreamHandler()
    ch.setLevel(log_level)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # 파일 핸들러
    fh = logging.FileHandler(log_file_path, encoding='utf-8')
    fh.setLevel(log_level)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    logging.info("Logger initialized.")

def load_config(config_path=os.path.join(PROJECT_ROOT, "configs/config.yaml")):
    """YAML 설정 파일을 로드"""
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def save_papers(papers, base_path, filename):
    """크롤링된 논문 목록을 JSON 파일로 저장"""
    # 저장 경로를 프로젝트 루트 기준으로 생성
    path = os.path.join(PROJECT_ROOT, base_path)
    os.makedirs(path, exist_ok=True)
    filepath = os.path.join(path, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(papers, f, ensure_ascii=False, indent=4)
    logging.info(f"Saved {len(papers)} papers to {filepath}")
    return filepath

def _save_scores(papers: list, target_date: datetime.date, config: dict):
    """스코어링된 논문 목록을 JSON 파일로 저장"""
    date_str = target_date.strftime("%Y-%m-%d")
    
    # 설정 파일에서 경로를 읽어옴
    base_path = config.get("storage", {}).get("scored_path", "data/scores")
    path = os.path.join(PROJECT_ROOT, base_path)
    os.makedirs(path, exist_ok=True)
    filepath = os.path.join(path, f"{date_str}-scores.json")
    
    # JSON 직렬화를 위해 datetime 객체를 문자열로 변환
    def convert_datetime(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(papers, f, ensure_ascii=False, indent=4, default=convert_datetime)
        logging.info(f"Saved {len(papers)} scored papers to {filepath}")
    except Exception as e:
        logging.error(f"Failed to save scored papers to {filepath}: {e}", exc_info=True)

def _crawl_papers(config: dict, target_date: datetime.date, days_to_fetch: int, window_based: bool) -> list:
    """
    설정에 따라 논문을 크롤링합니다.
    """
    all_new_papers = []
    if window_based:
        logging.info("Running Arxiv Crawler with time-window logic...")
        arxiv_config = config["arxiv_crawler"]
        crawler = ArxivCrawler()
        try:
            # 워크플로우에서 넘어온 target_date(UTC 어제 날짜)의 요일을 기반으로 분기
            # 이렇게 하면 실행 시점과 무관하게 항상 동일하게 동작
            target_weekday = target_date.weekday() # 월=0, 화=1, ..., 일=6

            # target_date가 일요일(즉, 월요일 아침 KST 실행)
            if target_weekday == 6: 
                days_for_window = 1 # ET 목 14:00 ~ 금 14:00 (1일)
                end_date_for_window = target_date - timedelta(days=2) # 기준(일) -> 금
            # target_date가 월요일(즉, 화요일 아침 KST 실행)
            elif target_weekday == 0:
                days_for_window = 3 # ET 금 14:00 ~ 월 14:00 (3일)
                end_date_for_window = target_date # 기준(월)
            # 그 외 평일 (수,목,금 KST 실행)
            else: 
                days_for_window = 1 # 하루 전 14:00 ~ 당일 14:00 (1일)
                end_date_for_window = target_date - timedelta(days=1)

            papers = crawler.fetch_by_time_window(
                queries=arxiv_config.get("queries", []),
                max_results=arxiv_config.get("max_results", 100),
                end_date_utc=end_date_for_window,
                days=days_for_window
            )
            all_new_papers.extend(papers)
        except Exception as e:
            logging.error(f"Error fetching from Arxiv with time-window: {e}", exc_info=True)
        return all_new_papers

    # --- 기존 날짜 기반 크롤링 로직 ---
    if not target_date and days_to_fetch == 1:
        logging.warning("No date specified, using local sample data.")
        sample_path = os.path.join(PROJECT_ROOT, "configs/sample_papers.json")
        try:
            with open(sample_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logging.error(f"Sample data file not found at {sample_path}. Please create it or set use_sample=False.")
            return []
    
    if config.get("arxiv_crawler", {}).get("enabled", False):
        logging.info("Running Arxiv Crawler...")
        arxiv_config = config["arxiv_crawler"]
        crawler = ArxivCrawler()
        try:
            papers = crawler.fetch(
                queries=arxiv_config.get("queries", []),
                max_results=arxiv_config.get("max_results", 100),
                target_date=target_date,
                days_to_fetch=days_to_fetch
            )
            all_new_papers.extend(papers)
            logging.info(f"Fetched {len(papers)} papers from Arxiv for the last {days_to_fetch} day(s) ending on {target_date}.")
        except Exception as e:
            logging.error(f"Error fetching from Arxiv: {e}", exc_info=True)
    return all_new_papers

def _filter_and_score_papers(papers: list, config: dict) -> list:
    """키워드와 LLM을 사용하여 논문을 필터링하고 점수를 매깁니다."""
    logging.info("--- Step 1: Keyword-based Pre-filtering ---")
    keyword_classifier = KeywordClassifier(config.get("classifier", {}).get("keyword_weights", {}))
    pre_filtered_papers = keyword_classifier.score(papers)

    if not pre_filtered_papers:
        logging.info("No relevant papers after keyword filtering.")
        return []
    logging.info(f"Found {len(pre_filtered_papers)} potentially relevant papers after keyword filtering.")

    llm_scorer_config = config.get("llm_scorer", {})
    if not llm_scorer_config.get("enabled", False):
        logging.info("LLM Scorer is disabled. Using keyword scores.")
        return pre_filtered_papers

    # LLM으로 처리할 논문 수를 결정합니다.
    limit = llm_scorer_config.get("processing_limit", 20)
    if limit <= 0:
        limit = len(pre_filtered_papers)
    
    papers_to_process = pre_filtered_papers[:min(len(pre_filtered_papers), limit)]
    
    if not papers_to_process:
        logging.info("No papers to process with LLM Scorer.")
        return pre_filtered_papers
        
    logging.info(f"Processing top {len(papers_to_process)} papers with LLM Scorer...")

    try:
        logging.info("--- Step 2: LLM-based Scoring ---")
        groq_config = config.get("groq_settings", {})
        llm_classifier = LLMClassifier(config=llm_scorer_config, groq_config=groq_config)
        
        # LLM으로 스코어링 된 논문들 (llm_score, llm_reason 추가됨)
        llm_scored_papers = llm_classifier.score(papers_to_process)
        
        # 결과를 원래 논문 리스트에 다시 반영하기 위한 룩업 테이블 생성
        llm_scored_map = {p["arxiv_id"]: p for p in llm_scored_papers}
        
        # 전체 논문 리스트를 순회하며 LLM 점수 업데이트
        for paper in pre_filtered_papers:
            if paper["arxiv_id"] in llm_scored_map:
                updated_paper = llm_scored_map[paper["arxiv_id"]]
                paper['llm_score'] = updated_paper.get('llm_score')
                paper['llm_reason'] = updated_paper.get('llm_reason')

        return pre_filtered_papers # 이제 모든 논문이 포함된 리스트를 반환

    except ValueError as e:
        logging.error(f"Error initializing LLM Scorer: {e}. Please set GROQ_API_KEY.", exc_info=True)
        logging.warning("Falling back to keyword-based scores.")
        return pre_filtered_papers
    except Exception as e:
        logging.error(f"An unexpected error occurred during LLM scoring: {e}", exc_info=True)
        logging.warning("Falling back to keyword-based scores.")
        return pre_filtered_papers

def _summarize_papers(papers: list, config: dict) -> list:
    """상위 논문들을 T.A.R.G.E.T. 프레임워크로 요약합니다."""
    summarizer_config = config.get("summarizer", {})
    if not summarizer_config.get("enabled", False):
        logging.info("Summarizer is disabled.")
        return papers

    logging.info("--- Step 3: T.A.R.G.E.T. Summarization ---")
    # 다단계 정렬: 1. LLM 점수, 2. 키워드 점수
    papers.sort(key=lambda p: (p.get('llm_score', 0), p.get('score', 0)), reverse=True)
    
    # 리포트에 포함될 top_n 만큼만 요약을 수행
    limit = config.get("reporter", {}).get("top_n", 10)
    if limit <= 0:
        limit = len(papers)
        
    papers_to_summarize = papers[:min(len(papers), limit)]
    final_papers = []
    
    max_len = summarizer_config.get("max_text_length_for_full_summary", 100000)

    for i, paper in enumerate(papers_to_summarize):
        logging.info(f"Summarizing paper {i+1}/{len(papers_to_summarize)}: \"{paper.get('title', '')[:50]}...\"")
        
        content_to_summarize = ""
        source_for_summary = ""

        full_text = download_and_extract_pdf_text(paper.get('pdf_url'))
        
        if not full_text:
            logging.warning(f"Could not retrieve full text for paper '{paper.get('title')}'. Skipping summarization.")
            paper['target_summary'] = None
            final_papers.append(paper)
            continue

        if len(full_text) > max_len:
            logging.info(f"Paper is too long ({len(full_text)} chars). Summarizing abstract only.")
            content_to_summarize = paper.get('abstract', '')
            source_for_summary = "Abstract"
        else:
            logging.info(f"Paper length ({len(full_text)} chars) is within limits. Summarizing full text.")
            content_to_summarize = full_text
            source_for_summary = "Full Text"

        if content_to_summarize:
            try:
                groq_config = config.get("groq_settings", {})
                summarizer = CSPaperSummarizer(
                    document_content=content_to_summarize, 
                    config=summarizer_config,
                    groq_config=groq_config
                )
                summary = summarizer.summarize(show_progress=False)
                if summary:
                    summary['source'] = source_for_summary # 요약 소스 정보 추가
                paper['target_summary'] = summary
            except Exception as e:
                logging.error(f"Error during summarization for paper '{paper.get('title')}': {e}", exc_info=True)
                paper['target_summary'] = None
        else:
            logging.warning(f"No content to summarize for paper '{paper.get('title')}'.")
            paper['target_summary'] = None

        final_papers.append(paper)

    final_papers.extend(papers[len(papers_to_summarize):])
    return final_papers

def _generate_report(papers: list, config: dict, target_date: datetime.date):
    """최종 리포트를 생성합니다."""
    logging.info("--- Step 4: Generating Final Report ---")
    try:
        reporter = MarkdownReporter(config=config)
        # 리포트 생성을 위해 최종적으로 다단계 정렬 수행
        papers.sort(key=lambda p: (p.get('llm_score', 0), p.get('score', 0)), reverse=True)
        reporter.generate_report(papers=papers, project_root=PROJECT_ROOT, target_date=target_date)
    except Exception as e:
        logging.error(f"Failed to generate report: {e}", exc_info=True)

def main():
    """
    DailyPapers 전체 파이프라인 실행 엔트리포인트
    """
    # 0. CLI 인자 파싱
    parser = argparse.ArgumentParser(description="DailyPapers: A CLI tool to fetch, score, and report on research papers.")
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Target end date to fetch papers from, in YYYY-MM-DD format. Defaults to yesterday."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Number of days to fetch papers for, ending on the target date. Defaults to 1."
    )
    parser.add_argument(
        "--window-based-fetch",
        action='store_true',
        help="Enable time-window based fetching for precise scheduling (e.g., for GitHub Actions)."
    )
    parser.add_argument(
        "--crawl-only",
        action='store_true',
        help="Run only the crawling and saving steps, then exit. Useful for debugging the crawler."
    )
    args = parser.parse_args()

    target_date = None
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            logging.error("Invalid date format for --date. Please use YYYY-MM-DD. Exiting.")
            return
    else:
        # 날짜가 지정되지 않으면 어제를 기본값으로 설정
        target_date = datetime.now(timezone.utc).date() - timedelta(days=1)
    
    logging.info(f"Target end date set to: {target_date}")
    logging.info(f"Number of days to fetch: {args.days}")
    
    # 1. 설정 로드 및 로깅 초기화
    config = load_config()
    setup_logging(config)
    
    logging.info("Starting DailyPapers pipeline...")
    
    # 2. 논문 크롤링
    crawled_papers = _crawl_papers(config, target_date, args.days, args.window_based_fetch)
    if not crawled_papers:
        logging.info("No new papers found. Exiting.")
        return

    # 3. 크롤링된 결과 저장
    if args.days > 1:
        filename = f"{target_date}_for_{args.days}_days.json"
    else:
        filename = f"{target_date}.json"
    save_papers(crawled_papers, config['storage']['crawled_path'], filename)

    # --crawl-only 플래그가 있으면 여기서 실행 종료
    if args.crawl_only:
        logging.info("Crawl-only mode enabled. Pipeline will stop after saving crawled papers.")
        return

    # 4. 논문 필터링 및 스코어링
    scored_papers = _filter_and_score_papers(crawled_papers, config)
    
    # LLM 스코어링이 실제 수행된 논문만 필터링
    llm_scored_papers = [p for p in scored_papers if p.get('llm_score') is not None]
    
    if not llm_scored_papers:
        logging.info("No papers were scored by the LLM. Exiting.")
        return
        
    # 스코어링된 결과 저장
    _save_scores(llm_scored_papers, target_date, config)

    # 5. 상위 논문 요약
    final_papers = _summarize_papers(llm_scored_papers, config)

    # 6. 최종 리포트 생성
    _generate_report(final_papers, config, target_date)

    logging.info("DailyPapers pipeline finished.")

if __name__ == "__main__":
    # 경로를 스크립트 기준으로 설정했으므로 chdir 로직은 더 이상 필요 없음
    main()
