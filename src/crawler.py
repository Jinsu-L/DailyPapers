import arxiv
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any
from src.base import AbstractCrawler

class ArxivCrawler(AbstractCrawler):
    """
    Arxiv API를 사용하여 논문을 검색하고 크롤링합니다.
    관심 키워드 및 카테고리를 기반으로 최신 논문을 가져옵니다.
    """
    source_name = "arxiv"

    def fetch(self, queries: List[str], max_results: int = 100, target_date: datetime.date = None) -> List[Dict[str, Any]]:
        """
        주어진 쿼리 목록을 사용하여 Arxiv에서 논문을 검색합니다.

        :param queries: 검색할 키워드 또는 카테고리 목록 (예: ["ti:information retrieval", "cat:cs.IR"])
        :param max_results: 가져올 최대 결과 수
        :param target_date: 논문을 필터링할 특정 날짜. None이면 오늘 날짜를 사용합니다.
        :return: 표준화된 논문 정보 딕셔너리 리스트
        """
        search_query = " OR ".join(f"({q})" for q in queries)
        
        if target_date is None:
            target_date = datetime.now(timezone.utc).date()

        # 최신 논문을 가져오기 위해 정렬 기준 설정
        search = arxiv.Search(
            query=search_query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending
        )

        results = []
        logging.info(f"Executing Arxiv search for papers submitted on {target_date} with query: {search_query}")
        
        try:
            for r in search.results():
                submitted_date = r.published.date()

                # Stop once we see older papers.
                if submitted_date < target_date:
                    logging.info(f"Reached papers from before {target_date}. Stopping.")
                    break
                
                # We only want papers published today.
                if submitted_date == target_date:
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
                    results.append(item)

        except Exception as e:
            logging.error(f"Failed to fetch results from Arxiv API: {e}", exc_info=True)
        
        logging.info(f"Found {len(results)} valid papers from Arxiv for {target_date}.")
        return results

if __name__ == "__main__":
    # 사용자가 요청한 검색어 기반으로 쿼리 구성
    # ti: title, au: author, abs: abstract, cat: category
    user_queries = [
        "ti:\"information retrieval\"", 
        "ti:retrieval", 
        "ti:click", 
        "abs:\"commerce domain\" AND abs:ml",
        "cat:cs.IR" # Information Retrieval 카테고리
    ]
    
    # Basic logging for standalone script execution
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    crawler = ArxivCrawler()
    papers = crawler.fetch(queries=user_queries, max_results=50)
    
    logging.info(f"Found {len(papers)} papers.")
    for paper in papers:
        logging.info(f"ID: {paper['arxiv_id']}")
        logging.info(f"Title: {paper['title']}")
        logging.info(f"URL: {paper['url']}")
        logging.info("-" * 20) 