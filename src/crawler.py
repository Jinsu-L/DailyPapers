import arxiv
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from src.base import AbstractCrawler
from pytz import timezone as pytz_timezone
import argparse

class ArxivCrawler(AbstractCrawler):
    """
    Arxiv API를 사용하여 논문을 검색하고 크롤링합니다.
    관심 키워드 및 카테고리를 기반으로 최신 논문을 가져옵니다.
    """
    source_name = "arxiv"

    def fetch_by_time_window(self, queries: List[str], max_results: int = 100, end_date_utc: datetime.date = None, days: int = 1, end_hour_et: int = 14) -> List[Dict[str, Any]]:
        """
        ET 기준 특정 시간 윈도우에 제출된 논문을 검색합니다.
        예: 월요일 KST 실행 -> ET 일요일 20시 공개분 -> ET 목 14:00 ~ 금 14:00 제출분
        """
        search_query = " OR ".join(f"({q})" for q in queries)
        
        if end_date_utc is None:
            end_date_utc = datetime.now(timezone.utc).date()

        et_tz = pytz_timezone('US/Eastern')
        
        # ET 기준 종료 시각 설정
        end_dt_et_naive = datetime.combine(end_date_utc, datetime.min.time()).replace(hour=end_hour_et)
        end_dt_et = et_tz.localize(end_dt_et_naive)
        
        # UTC로 변환
        end_dt_utc = end_dt_et.astimezone(timezone.utc)
        
        # UTC 기준 시작 시각 설정
        start_dt_utc = end_dt_utc - timedelta(days=days)

        logging.info(f"Executing Arxiv search for papers submitted between {start_dt_utc.strftime('%Y-%m-%d %H:%M:%S UTC')} and {end_dt_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        
        client = arxiv.Client()
        search = arxiv.Search(
            query=search_query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending
        )

        results = []
        try:
            for r in client.results(search):
                # r.published는 이미 UTC 시간대로 가정 (arxiv 라이브러리 특성)
                submitted_dt_utc = r.published

                if submitted_dt_utc < start_dt_utc:
                    logging.info(f"Reached papers from before {start_dt_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}. Stopping.")
                    break
                
                if start_dt_utc <= submitted_dt_utc < end_dt_utc:
                    item = {
                        "title": r.title,
                        "abstract": r.summary.replace('\\n', ' '),
                        "url": r.entry_id,
                        "pdf_url": r.pdf_url,
                        "arxiv_id": r.entry_id.split('/')[-1],
                        "authors": [author.name for author in r.authors],
                        "submitted": r.published.strftime("%Y-%m-%d %H:%M:%S"),
                        "source": self.source_name,
                        "comment": r.comment,
                    }
                    if item not in results:
                        results.append(item)
        except arxiv.UnexpectedEmptyPageError:
            logging.info("Reached the end of available results from Arxiv API.")
        except Exception as e:
            logging.error(f"Failed to fetch results from Arxiv API: {e}", exc_info=True)
        
        logging.info(f"Found {len(results)} valid papers from Arxiv for the specified time window.")
        return results

    def fetch(self, queries: List[str], max_results: int = 100, target_date: datetime.date = None, days_to_fetch: int = 1) -> List[Dict[str, Any]]:
        """
        주어진 쿼리 목록을 사용하여 Arxiv에서 논문을 검색합니다.

        :param queries: 검색할 키워드 또는 카테고리 목록 (예: ["ti:information retrieval", "cat:cs.IR"])
        :param max_results: 가져올 최대 결과 수
        :param target_date: 논문을 필터링할 기준 종료 날짜.
        :param days_to_fetch: target_date를 포함하여 며칠 전까지의 논문을 가져올지 결정.
        :return: 표준화된 논문 정보 딕셔너리 리스트
        """
        search_query_parts = []
        for q in queries:
            if ":" in q:
                search_query_parts.append(f"({q})")
            else:
                search_query_parts.append(f"(ti:{q} OR abs:{q})")

        query = ' OR '.join(search_query_parts)

        if target_date is None:
            target_date = datetime.now(timezone.utc).date()

        from_date = target_date - timedelta(days=days_to_fetch - 1)
        to_date = target_date

        if from_date and to_date:
            from_date_str = from_date.strftime('%Y%m%d')
            to_date_str = to_date.strftime('%Y%m%d')
            # Ensure from_date and to_date are the same for a single day fetch
            if from_date_str == to_date_str:
                query += f" AND submittedDate:[{from_date_str}000000 TO {to_date_str}235959]"
            else:
                query += f" AND submittedDate:[{from_date_str}000000 TO {to_date_str}235959]"

        logging.info(f"Executing Arxiv search with query: {query}")

        client = arxiv.Client()
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending
        )

        results = []
        
        try:
            for r in client.results(search):
                # The date filtering is now part of the query, but we can double-check
                published_date = r.published.date()
                if from_date and to_date:
                    if not (from_date <= published_date <= to_date):
                        continue

                item = {
                    "title": r.title,
                    "abstract": r.summary.replace('\n', ' '),
                    "url": r.entry_id,
                    "pdf_url": r.pdf_url,
                    "arxiv_id": r.entry_id.split('/')[-1],
                    "authors": [author.name for author in r.authors],
                    "submitted": r.published.strftime("%Y-%m-%d %H:%M:%S"),
                    "source": self.source_name,
                    "comment": r.comment,
                }
                # 중복 추가 방지
                if item not in results:
                    results.append(item)

        except arxiv.UnexpectedEmptyPageError:
            logging.info("Reached the end of available results from Arxiv API.")
        except Exception as e:
            logging.error(f"Failed to fetch results from Arxiv API: {e}", exc_info=True)
        
        logging.info(f"Found {len(results)} valid papers from Arxiv for the period {from_date} to {to_date}.")
        return results

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Standalone Arxiv Crawler for debugging.")
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
        "--window",
        action='store_true',
        help="Use the time-window based fetch method (fetch_by_time_window)."
    )
    args = parser.parse_args()

    target_date_obj = None
    if args.date:
        try:
            target_date_obj = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            print("Invalid date format for --date. Please use YYYY-MM-DD.")
            exit(1)
    else:
        target_date_obj = datetime.now(timezone.utc).date() - timedelta(days=1)
    
    user_queries = [
        "cat:cs.IR", # Information Retrieval
        "cat:cs.CL", # Computation and Language
    ]
    
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    crawler = ArxivCrawler()

    if args.window:
        logging.info(f"Fetching papers using time window of {args.days} day(s) ending on {target_date_obj.strftime('%Y-%m-%d')} at 14:00 ET")
        papers = crawler.fetch_by_time_window(
            queries=user_queries,
            max_results=3000,
            end_date_utc=target_date_obj,
            days=args.days
        )
    else:
        logging.info(f"Fetching papers for {args.days} day(s) ending on {target_date_obj.strftime('%Y-%m-%d')}")
        papers = crawler.fetch(
            queries=user_queries, 
            max_results=3000, 
            target_date=target_date_obj,
            days_to_fetch=args.days
        )
    
    if papers:
        logging.info(f"Found {len(papers)} papers.")
        for i, paper in enumerate(papers):
            logging.info(f"--- Paper {i+1} ---")
            logging.info(f"  ID: {paper['arxiv_id']}")
            logging.info(f"  Title: {paper['title']}")
            logging.info(f"  Submitted: {paper['submitted']}")
    else:
        logging.info("No papers found for the specified criteria.") 