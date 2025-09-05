import os
import subprocess
import argparse
import tempfile
import shutil
import logging
import re
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def run_command(command, cwd):
    """주어진 디렉토리에서 셸 명령어를 실행하고 결과를 로깅합니다."""
    logging.info(f"Executing command: {' '.join(command)}")
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True, cwd=cwd)
        logging.info(f"Stdout: {result.stdout.strip()}")
        if result.stderr:
            logging.info(f"Stderr: {result.stderr.strip()}")
        return result.stdout
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed with return code {e.returncode}")
        logging.error(f"Stderr: {e.stderr.strip()}")
        raise

def find_report(report_dir: str, report_date: str | None = None) -> tuple[str | None, str | None]:
    """리포트 디렉토리에서 특정 날짜 또는 가장 최신 .md 파일을 찾습니다."""
    if not os.path.exists(report_dir):
        logging.warning(f"Report directory '{report_dir}' not found.")
        return None, None

    if report_date:
        report_filename = f"{report_date}.md"
        report_path = os.path.join(report_dir, report_filename)
        if os.path.exists(report_path):
            logging.info(f"Found specified report: {report_filename}")
            return report_path, report_filename
        else:
            logging.error(f"Specified report file not found: {report_path}")
            return None, None
    else:
        report_files = [f for f in os.listdir(report_dir) if f.endswith('.md')]
        if not report_files:
            logging.info("No markdown report files found.")
            return None, None
        
        latest_report_name = sorted(report_files, reverse=True)[0]
        report_path = os.path.join(report_dir, latest_report_name)
        logging.info(f"Found latest report: {latest_report_name}")
        return report_path, latest_report_name

def find_data_files(data_dir: str, report_date: str) -> tuple[str | None, str | None]:
    """데이터 디렉토리에서 특정 날짜의 크롤링 및 스코어 파일을 찾습니다."""
    crawled_file = f"{report_date}.json"
    scores_file = f"{report_date}-scores.json"

    crawled_path = os.path.join(data_dir, 'crawled', crawled_file)
    scores_path = os.path.join(data_dir, 'scores', scores_file)

    if not os.path.exists(crawled_path):
        logging.warning(f"Crawled data file not found: {crawled_path}")
        crawled_path = None

    if not os.path.exists(scores_path):
        logging.warning(f"Scores data file not found: {scores_path}")
        scores_path = None

    return crawled_path, scores_path

def parse_readme(content: str) -> dict:
    """PAPERS 콘텐츠를 파싱하여 연도/월별 링크 데이터를 담은 딕셔너리로 변환합니다."""
    data = {}
    current_year, current_month = None, None
    for line in content.splitlines():
        year_match = re.match(r"^##\s+(\d{4})", line)
        month_match = re.match(r"^###\s+([A-Za-z]+)", line)
        link_match = re.match(r"^\s*-\s*\[.*\]\(.*\)", line)

        if year_match:
            current_year = year_match.group(1)
            data[current_year] = {}
        elif month_match and current_year:
            current_month = month_match.group(1)
            data[current_year][current_month] = []
        elif link_match and current_year and current_month:
            data[current_year][current_month].append(line)
    return data

def regenerate_readme(data: dict) -> str:
    """파싱된 데이터 딕셔너리를 사용하여 PAPERS 콘텐츠를 다시 생성합니다."""
    content = "# Daily Information Retrieval Papers\n\nA curated list of daily papers related to Information Retrieval.\n"
    sorted_years = sorted(data.keys(), reverse=True)
    
    month_name_to_num = {datetime.strptime(str(i), '%m').strftime('%B'): i for i in range(1, 13)}

    for year in sorted_years:
        content += f"\n## {year}\n"
        sorted_months = sorted(data[year].keys(), key=lambda m: month_name_to_num.get(m, 0), reverse=True)

        for month in sorted_months:
            content += f"\n### {month}\n"
            content += "\n".join(data[year][month])
            content += "\n"
    return content

def main():
    """메인 업로드 로직"""
    parser = argparse.ArgumentParser(description="GitHub 리포지토리에 리포트를 업로드합니다.")
    parser.add_argument("--report-dir", default="reports", help="리포트 파일이 위치한 디렉토리")
    parser.add_argument("--data-dir", default="data", help="데이터 파일이 위치한 디렉토리")
    parser.add_argument("--report-date", default=None, help="업로드할 특정 리포트의 날짜 (YYYY-MM-DD)")
    parser.add_argument("--dest-repo-slug", default="Jinsu-L/DailyIR", help="결과를 푸시할 리포지토리")
    parser.add_argument("--dest-branch", default="main", help="결과를 푸시할 브랜치")
    args = parser.parse_args()

    token = os.environ.get("API_TOKEN_GITHUB")
    actor = os.environ.get("GITHUB_ACTOR")
    if not token or not actor:
        logging.error("API_TOKEN_GITHUB and GITHUB_ACTOR environment variables are required.")
        return

    report_path, report_filename = find_report(args.report_dir, args.report_date)
    if not report_path or not report_filename:
        logging.info("Upload skipped as no report was found to upload.")
        return

    try:
        report_date_str = report_filename.replace('.md', '')
        report_date_obj = datetime.strptime(report_date_str, '%Y-%m-%d')
    except ValueError:
        logging.error(f"Invalid report filename format: {report_filename}. Expected YYYY-MM-DD.md")
        return

    year_str, month_name, month_folder = report_date_obj.strftime('%Y'), report_date_obj.strftime('%B'), report_date_obj.strftime('%Y-%m')

    crawled_data_path, scores_data_path = find_data_files(args.data_dir, report_date_str)

    logging.info(f"Preparing to upload report: {report_filename}")

    with tempfile.TemporaryDirectory() as temp_dir:
        repo_url = f"https://{actor}:{token}@github.com/{args.dest_repo_slug}.git"
        run_command(['git', 'clone', repo_url, '.'], cwd=temp_dir)
        run_command(['git', 'config', 'user.name', actor], cwd=temp_dir)
        run_command(['git', 'config', 'user.email', f'{actor}@users.noreply.github.com'], cwd=temp_dir)

        dest_report_folder_path = os.path.join(temp_dir, 'reports', month_folder)
        os.makedirs(dest_report_folder_path, exist_ok=True)
        shutil.copy(report_path, dest_report_folder_path)

        files_to_add = [os.path.join('reports', month_folder, report_filename)]
        if crawled_data_path:
            dest_crawled_folder_path = os.path.join(temp_dir, 'data', 'crawled')
            os.makedirs(dest_crawled_folder_path, exist_ok=True)
            shutil.copy(crawled_data_path, dest_crawled_folder_path)
            files_to_add.append(os.path.join('data', 'crawled', os.path.basename(crawled_data_path)))

        if scores_data_path:
            dest_scores_folder_path = os.path.join(temp_dir, 'data', 'scores')
            os.makedirs(dest_scores_folder_path, exist_ok=True)
            shutil.copy(scores_data_path, dest_scores_folder_path)
            files_to_add.append(os.path.join('data', 'scores', os.path.basename(scores_data_path)))

        readme_path = os.path.join(temp_dir, 'PAPERS.md')
        readme_content = ""
        if os.path.exists(readme_path):
            with open(readme_path, 'r', encoding='utf-8') as f:
                readme_content = f.read()

        new_link_line = f"- [{report_date_obj.strftime('%Y-%m-%d')}](./reports/{month_folder}/{report_filename})"
        readme_updated = False
        
        if new_link_line not in readme_content:
            readme_updated = True
            data = parse_readme(readme_content)
            data.setdefault(year_str, {}).setdefault(month_name, []).insert(0, new_link_line)
            new_readme_content = regenerate_readme(data)
            with open(readme_path, 'w', encoding='utf-8') as f:
                f.write(new_readme_content)
        else:
            logging.info("Link already exists in PAPERS.md. Skipping PAPERS update.")

        if readme_updated:
            files_to_add.append('PAPERS.md')
        
        run_command(['git', 'add'] + files_to_add, cwd=temp_dir)
        
        status_output = run_command(['git', 'status', '--porcelain'], cwd=temp_dir)
        if not status_output:
            logging.info("No changes to commit. The report is already up-to-date.")
            return

        commit_message = f"Add report and data for {report_date_obj.strftime('%Y-%m-%d')}"
        run_command(['git', 'commit', '-m', commit_message], cwd=temp_dir)
        run_command(['git', 'push', 'origin', f'HEAD:{args.dest_branch}'], cwd=temp_dir)

    logging.info(f"Successfully uploaded {report_filename} to {args.dest_repo_slug}")

if __name__ == "__main__":
    main() 
