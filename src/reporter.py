import os
import logging
from datetime import datetime
from typing import List, Dict, Any

class MarkdownReporter:
    """
    스코어링된 논문 목록을 받아 마크다운 리포트를 생성
    """
    def __init__(self, config: Dict[str, Any]):
        self.report_path = config.get("reporter", {}).get("report_path", "reports")
        self.top_n = config.get("reporter", {}).get("top_n", 10)

    def generate_report(self, papers: List[Dict[str, Any]], project_root: str):
        """
        Top-N 논문에 대한 마크다운 리포트를 생성하고 저장
        """
        if not papers:
            logging.warning("No relevant papers to report.")
            return

        # 리포트 디렉토리 생성
        report_dir = os.path.join(project_root, self.report_path)
        os.makedirs(report_dir, exist_ok=True)
        
        # 리포트 파일 경로 설정
        today_str = datetime.now().strftime("%Y-%m-%d")
        report_filepath = os.path.join(report_dir, f"{today_str}.md")
        
        # Top-N 논문 선택
        top_papers = papers[:self.top_n]
        
        # 마크다운 내용 생성
        md_content = f"# Daily Papers Report - {today_str}\n\n"
        md_content += f"오늘의 Top {len(top_papers)}개 관련 논문입니다.\n\n"
        
        for i, paper in enumerate(top_papers, 1):
            md_content += f"## {i}. {paper.get('title', 'N/A')}\n\n"
            md_content += f"- **Score**: {paper.get('score', 0)}\n"
            md_content += f"- **Authors**: {', '.join(paper.get('authors', []))}\n"
            md_content += f"- **URL**: <{paper.get('url', '#')}>\n"
            md_content += f"- **Submitted**: {paper.get('submitted', 'N/A')}\n"
            
            # Comment가 있는 경우에만 표시
            if paper.get('comment'):
                md_content += f"- **Comment**: {paper.get('comment')}\n"
            
            # Reasons를 더 잘 표시
            reasons = paper.get('reasons', [])
            if reasons:
                # LLM 기반 이유와 키워드 기반 이유를 구분해서 표시
                if isinstance(reasons[0], str) and reasons[0].startswith("Found"):
                     md_content += f"- **Keyword Reasons**: {'; '.join(reasons)}\n\n"
                else: # LLM의 경우
                    md_content += f"- **Reason**: {reasons[0]}\n\n"
            
            # T.A.R.G.E.T. 요약이 있으면 표시
            if paper.get('target_summary'):
                summary = paper['target_summary']
                source = summary.get('source', 'N/A')
                md_content += f"### T.A.R.G.E.T. Summary (from {source})\n"
                md_content += f"- **Topic**: {summary.get('topic', 'N/A')}\n"
                md_content += f"- **Aim**: {summary.get('aim', 'N/A')}\n"
                md_content += f"- **Rationale**: {summary.get('rationale', 'N/A')}\n"
                md_content += f"- **Ground**: {summary.get('ground', 'N/A')}\n"
                md_content += f"- **Experiment**: {summary.get('experiment', 'N/A')}\n"
                md_content += f"- **Takeaway**: {summary.get('takeaway', 'N/A')}\n\n"

            # 원문 초록을 항상 표시
            md_content += f"### Abstract\n"
            md_content += f"> {paper.get('abstract', 'No abstract available.')}\n\n"

            md_content += "---\n\n"
            
        # 리포트 파일 저장
        with open(report_filepath, 'w', encoding='utf-8') as f:
            f.write(md_content)
            
        logging.info(f"Successfully generated report at: {report_filepath}")
        return report_filepath

if __name__ == '__main__':
    # 예제 사용법
    sample_config = {
        "reporter": {
            "report_path": "reports_test",
            "top_n": 2
        }
    }
    
    # 임시 프로젝트 루트 (실제로는 main.py에서 전달)
    temp_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Basic logging for standalone script execution
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    reporter = MarkdownReporter(config=sample_config)
    reporter.generate_report(papers=sample_papers, project_root=temp_project_root)
    logging.info("Test report generated.") 