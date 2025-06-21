import yaml
import os
import json
import logging
import argparse
from datetime import datetime, timezone
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
    print(f"Saved {len(papers)} papers to {filepath}")
    return filepath

def _crawl_papers(config: dict, target_date: datetime.date) -> list:
    """
    설정에 따라 논문을 크롤링합니다.
    """
    # 날짜가 지정된 경우 샘플 데이터 사용 비활성화
    use_sample = (target_date is None)

    if use_sample:
        logging.warning("No date specified, using local sample data.")
        sample_path = os.path.join(PROJECT_ROOT, "configs/sample_papers.json")
        try:
            with open(sample_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logging.error(f"Sample data file not found at {sample_path}. Please create it or set use_sample=False.")
            return []
    
    all_new_papers = []
    if config.get("arxiv_crawler", {}).get("enabled", False):
        logging.info("Running Arxiv Crawler...")
        arxiv_config = config["arxiv_crawler"]
        crawler = ArxivCrawler()
        try:
            papers = crawler.fetch(
                queries=arxiv_config.get("queries", []),
                max_results=arxiv_config.get("max_results", 100),
                target_date=target_date
            )
            all_new_papers.extend(papers)
            logging.info(f"Fetched {len(papers)} papers from Arxiv.")
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

    limit = llm_scorer_config.get("processing_limit", 20)
    if limit <= 0:
        limit = len(pre_filtered_papers)
    
    papers_to_process = pre_filtered_papers[:min(len(pre_filtered_papers), limit)]
    logging.info(f"Processing top {len(papers_to_process)} papers with LLM Scorer...")

    try:
        logging.info("--- Step 2: LLM-based Scoring ---")
        groq_config = config.get("groq_settings", {})
        llm_classifier = LLMClassifier(config=llm_scorer_config, groq_config=groq_config)
        scored_papers = llm_classifier.score(papers_to_process)
        # LLM으로 처리하지 않은 나머지 논문들을 다시 합침
        remaining_papers = pre_filtered_papers[len(papers_to_process):]
        return scored_papers + remaining_papers
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
    papers.sort(key=lambda p: p.get('score', 0), reverse=True)
    
    limit = config.get("llm_scorer", {}).get("processing_limit", 20)
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

def _generate_report(papers: list, config: dict):
    """최종 리포트를 생성합니다."""
    logging.info("--- Step 4: Generating Final Report ---")
    try:
        reporter = MarkdownReporter(config=config)
        # 리포트 생성을 위해 최종적으로 점수 기준 정렬
        papers.sort(key=lambda p: p.get('score', 0), reverse=True)
        reporter.generate_report(papers=papers, project_root=PROJECT_ROOT)
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
        help="Target date to fetch papers from, in YYYY-MM-DD format. Defaults to today."
    )
    args = parser.parse_args()

    target_date = None
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
            logging.info(f"Target date set to: {target_date}")
        except ValueError:
            logging.error("Invalid date format. Please use YYYY-MM-DD. Exiting.")
            return
    else:
        # target_date가 None으로 유지되면, 크롤러는 오늘 날짜를 사용합니다.
        logging.info("No date provided, will default to today for live crawl or use sample data.")

    # 1. 설정 로드 및 로깅 초기화
    config = load_config()
    setup_logging(config)
    
    logging.info("Starting DailyPapers pipeline...")
    
    # 2. 크롤링
    crawled_papers = _crawl_papers(config, target_date=target_date)
    if not crawled_papers:
        logging.info("No new papers found. Exiting.")
        return

    # 크롤링된 논문 저장 (라이브 크롤링 시에만)
    if not args.date is None:
        date_str = target_date.strftime("%Y-%m-%d")
        storage_config = config.get("storage", {})
        save_papers(
            papers=crawled_papers,
            base_path=storage_config.get("crawled_path", "data/crawled"),
            filename=f"{date_str}.json"
        )

    # 3. 필터링 및 스코어링
    scored_papers = _filter_and_score_papers(crawled_papers, config)
    if not scored_papers:
        logging.info("No papers left after scoring. Exiting.")
        return
        
    # 4. 요약
    final_papers = _summarize_papers(scored_papers, config)

    # 5. 최종 리포트 생성
    _generate_report(final_papers, config)

    logging.info("DailyPapers pipeline finished.")

if __name__ == "__main__":
    # 경로를 스크립트 기준으로 설정했으므로 chdir 로직은 더 이상 필요 없음
    main()
