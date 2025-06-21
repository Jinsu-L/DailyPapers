import requests
import pymupdf  # Fitz
import logging
from typing import Optional

def download_and_extract_pdf_text(pdf_url: str, timeout: int = 30) -> Optional[str]:
    """
    PDF URL에서 파일을 다운로드하고 텍스트 내용을 추출합니다.

    :param pdf_url: 다운로드할 PDF의 URL
    :param timeout: 요청 타임아웃 시간 (초)
    :return: 추출된 텍스트 또는 실패 시 None
    """
    if not pdf_url:
        logging.error("PDF URL is missing.")
        return None
        
    logging.info(f"Downloading PDF from: {pdf_url}")
    try:
        response = requests.get(pdf_url, timeout=timeout)
        response.raise_for_status()  # HTTP 오류가 발생하면 예외를 발생시킴
    except requests.exceptions.RequestException as e:
        logging.error(f"Error downloading PDF from {pdf_url}: {e}", exc_info=True)
        return None

    try:
        # 메모리에서 직접 PDF 열기
        with pymupdf.open(stream=response.content, filetype="pdf") as doc:
            text = ""
            for page in doc:
                text += page.get_text()
            
            if not text.strip():
                logging.warning(f"No text could be extracted from {pdf_url}")
                return None
            
            logging.info(f"Successfully extracted text from {pdf_url} ({len(text)} chars)")
            return text
    except Exception as e:
        logging.error(f"Error parsing PDF file from {pdf_url}: {e}", exc_info=True)
        return None

if __name__ == '__main__':
    # 예제 사용법 (실제 Arxiv PDF URL)
    # 주의: 이 URL은 시간이 지나면 유효하지 않을 수 있음
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    sample_pdf_url = "https://arxiv.org/pdf/2401.00010.pdf"
    
    full_text = download_and_extract_pdf_text(sample_pdf_url)
    
    if full_text:
        logging.info("\n--- Extracted Text (first 500 chars) ---")
        logging.info(full_text[:500])
    else:
        logging.error("\nFailed to extract text from the sample PDF.") 