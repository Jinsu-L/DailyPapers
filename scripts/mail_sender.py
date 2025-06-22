import os
import smtplib
import argparse
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

def create_summary_and_link(report_path: str, github_repo_slug: str) -> str:
    """
    리포트 파일에서 Top-N 요약 섹션을 추출하고 GitHub 링크를 추가합니다.
    """
    if not os.path.exists(report_path):
        return "생성된 리포트 파일을 찾을 수 없습니다."

    with open(report_path, 'r', encoding='utf-8') as f:
        full_content = f.read()

    # 정규표현식을 사용하여 "Top N" 요약 섹션만 추출합니다.
    match = re.search(r"(## 🌟 Top.*?)(?=## 📝 Other Noteworthy Papers|\Z)", full_content, re.DOTALL)
    
    summary_section = "리포트에서 Top-N 요약 섹션을 찾지 못했습니다."
    if match:
        summary_section = match.group(1).strip()

    # GitHub의 전체 리포트 링크를 생성합니다.
    report_filename = os.path.basename(report_path)
    try:
        # 'YYYY-MM-DD.md' 형식의 파일 이름에서 날짜를 파싱하여 'YYYY-MM' 폴더 경로를 만듭니다.
        report_date = datetime.strptime(report_filename, '%Y-%m-%d.md')
        month_folder = report_date.strftime('%Y-%m')
    except ValueError:
        # 예외 발생 시를 대비한 기본값
        month_folder = "latest"

    github_link = f"https://github.com/{github_repo_slug}/blob/main/reports/{month_folder}/{report_filename}"

    # 최종 이메일 본문을 구성합니다.
    email_body = f"""{summary_section}

---

전체 리포트는 아래 GitHub 링크에서 확인하실 수 있습니다.
{github_link}
"""
    return email_body.strip()


def send_email(email_body: str, report_date_str: str, recipients: list, gmail_user: str, gmail_app_password: str):
    """
    구성된 이메일 본문을 지정된 수신자 목록에게 전송합니다.
    """
    subject = f"📰 Daily IR Papers Report - {report_date_str}"

    msg = MIMEMultipart()
    # 보내는 사람의 '이름'과 '이메일 주소'를 함께 설정합니다.
    msg['From'] = f'"DailyIR" <{gmail_user}>'
    msg['To'] = ", ".join(recipients)  # 헤더에는 콤마로 구분된 문자열로 표시
    msg['Subject'] = subject

    msg.attach(MIMEText(email_body, 'plain'))

    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.ehlo()
        server.login(gmail_user, gmail_app_password)
        # sendmail의 수신자 인자는 실제 리스트를 받습니다.
        server.sendmail(gmail_user, recipients, msg.as_string())
        server.close()
        print(f"Successfully sent email to: {', '.join(recipients)}")
    except Exception as e:
        print(f"Failed to send email: {e}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Send daily report summary via email.")
    parser.add_argument("--report-path", required=True, help="Path to the markdown report file.")
    parser.add_argument("--repo-slug", required=True, help="GitHub repository slug for the link (e.g., Jinsu-L/DailyIR).")
    args = parser.parse_args()

    # 환경 변수에서 민감한 정보를 로드합니다.
    recipients_str = os.environ.get("MAIL_RECIPIENTS")
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_app_password = os.environ.get("GMAIL_APP_PASSWORD")

    if not all([recipients_str, gmail_user, gmail_app_password]):
        raise ValueError("Missing required environment variables: MAIL_RECIPIENTS, GMAIL_USER, GMAIL_APP_PASSWORD")

    # 콤마, 세미콜론, 공백 등으로 구분된 이메일 주소 문자열을 파싱하여 리스트로 만듭니다.
    recipient_list = [email.strip() for email in re.split(r'[,;\s]+', recipients_str) if email.strip()]
    if not recipient_list:
        raise ValueError("MAIL_RECIPIENTS environment variable is empty or invalid.")

    # 이메일 본문을 생성합니다.
    email_content = create_summary_and_link(args.report_path, args.repo_slug)

    # 리포트 날짜를 파일 이름에서 추출합니다.
    report_date = os.path.basename(args.report_path).replace('.md', '')
    
    # 이메일을 전송합니다.
    send_email(email_content, report_date, recipient_list, gmail_user, gmail_app_password) 