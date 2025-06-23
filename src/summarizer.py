import os
import json
import logging
import time
from typing import Dict, Any, Optional, List
from groq import RateLimitError, APIError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, RetryError
from .llm_services import BaseLLMService

def split_text(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    """간단한 텍스트 분할 함수"""
    if chunk_size <= chunk_overlap:
        raise ValueError("chunk_size must be greater than chunk_overlap")
    
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start += chunk_size - chunk_overlap
    return chunks

class CSPaperSummarizer:
    """
    T.A.R.G.E.T 프레임워크를 사용하여 CS 논문을 요약하는 클래스.
    Map-Reduce 방식을 사용하여 긴 논문도 처리합니다.
    """
    def __init__(self, document_content: str, config: dict, groq_config: dict):
        """
        CSPaperSummarizer를 초기화합니다.

        :param document_content: 요약할 논문의 전체 텍스트
        :param config: summarizer에 대한 설정 딕셔너리
        :param groq_config: groq_settings에 대한 공통 설정 딕셔너리
        """
        self.document_content = document_content
        self.config = config
        # PAYLOAD_LIMIT을 config에서 읽어와 인스턴스 변수로 저장
        self.payload_limit = self.config.get("payload_limit", 12000)
        
        # Map과 Reduce를 위한 LLM 서비스를 각각, 별도의 폴백 리스트와 함께 초기화
        map_config = {
            **groq_config,
            "model": config.get("map_model"),
            "model_fallback_list": config.get("map_fallback_list", [])
        }
        reduce_config = {
            **groq_config,
            "model": config.get("reduce_model"),
            "model_fallback_list": config.get("reduce_fallback_list", [])
        }
        
        self.map_llm_service = BaseLLMService(config=map_config)
        self.reduce_llm_service = BaseLLMService(config=reduce_config)

        prompt_path = os.path.join(os.path.dirname(__file__), '..', 'configs', 'prompt.json')
        with open(prompt_path, 'r', encoding='utf-8') as f:
            self.prompts = json.load(f)["summarize_target_map_reduce"]

        # Use the local split_text function for chunking
        chunk_size = self.config.get("chunk_size", 4000)
        chunk_overlap = self.config.get("chunk_overlap", 400)
        self.docs = split_text(self.document_content, chunk_size, chunk_overlap)
        logging.info(f"The document was split into {len(self.docs)} chunks.")

    def summarize(self, show_progress=True) -> Optional[Dict[str, str]]:
        # 1. Map step
        logging.info(f"  > Step 3a: Mapping {len(self.docs)} chunks into summaries...")
        chunk_summaries = []
        
        # tqdm is removed, so we directly iterate over self.docs
        iterator = self.docs
        if show_progress:
            try:
                from tqdm import tqdm
                iterator = tqdm(self.docs, desc="    Summarizing chunks", leave=False, dynamic_ncols=True)
            except ImportError:
                logging.warning("tqdm not found. Progress bar will not be shown. Please install it with 'pip install tqdm'.")
        
        map_prompt_template = self.prompts["map_prompt"]
        
        for i, chunk in enumerate(iterator):
            try:
                prompt = map_prompt_template.format(input=chunk)
                messages = [{"role": "user", "content": prompt}]
                summary = self.map_llm_service._invoke_with_fallback(messages, is_json=False)
                if summary:
                    chunk_summaries.append(summary)
                else:
                    logging.error(f"    Fallback failed for chunk {i+1}/{len(self.docs)}. Skipping chunk.")
                    chunk_summaries.append("")
            except Exception as e:
                logging.error(f"    An unexpected error occurred while summarizing chunk {i+1}/{len(self.docs)}: {e}", exc_info=True)
                chunk_summaries.append("")
            
            # TPM(Tokens Per Minute) 한도를 준수하기 위해 API 호출 사이에 지연 추가
            time.sleep(8)

        # 2. Iterative Reduce step
        logging.info(f"  > Step 3b: Reducing {len(chunk_summaries)} summaries into a final T.A.R.G.E.T. summary...")

        intermediate_prompt = self.prompts["intermediate_reduce_prompt"]
        final_prompt = self.prompts["reduce_prompt"]

        current_summaries = [s for s in chunk_summaries if s]

        if not current_summaries:
            logging.error("  > Error: No chunks were successfully summarized. Cannot proceed.")
            return None

        while len(current_summaries) > 1:
            logging.info(f"    > Reducing {len(current_summaries)} summaries in batches...")
            next_level_summaries = []
            
            current_batch = []
            current_batch_length = 0
            for summary in current_summaries:
                # 현재 요약문을 추가하면 페이로드 한계를 넘는지 확인 (그리고 배치가 비어있지 않은지)
                if current_batch_length + len(summary) > self.payload_limit and current_batch:
                    # 현재 배치를 처리
                    prompt = intermediate_prompt.format(chunk_summaries="\\n---\\n".join(current_batch))
                    messages = [{"role": "user", "content": prompt}]
                    reduced_summary = self.reduce_llm_service._invoke_with_fallback(messages, is_json=False)
                    if reduced_summary:
                        next_level_summaries.append(reduced_summary)
                    # 배치 초기화
                    current_batch, current_batch_length = [], 0
                
                current_batch.append(summary)
                current_batch_length += len(summary)

            # 마지막 남은 배치를 처리
            if current_batch:
                prompt = intermediate_prompt.format(chunk_summaries="\\n---\\n".join(current_batch))
                messages = [{"role": "user", "content": prompt}]
                reduced_summary = self.reduce_llm_service._invoke_with_fallback(messages, is_json=False)
                if reduced_summary:
                    next_level_summaries.append(reduced_summary)
                # 여기에도 지연을 추가하여 reduce 단계의 연속 호출 방지
                time.sleep(8)
            
            current_summaries = next_level_summaries
            if not current_summaries:
                logging.error("  > Error: Reduction process resulted in no summaries.")
                return None

        # 최종 요약 (T.A.R.G.E.T. 형식)
        if len(current_summaries) == 1:
            logging.info("    > Performing final reduction to T.A.R.G.E.T. format...")
            final_reduce_prompt = final_prompt.format(chunk_summaries=current_summaries[0])
            try:
                messages = [{"role": "user", "content": final_reduce_prompt}]
                final_summary_str = self.reduce_llm_service._invoke_with_fallback(messages, is_json=True)
                if final_summary_str:
                    return json.loads(final_summary_str)
                else:
                    logging.error("  > Final reduction step failed.")
                    return None
            except (json.JSONDecodeError, TypeError) as e:
                logging.error(f"  > Error parsing final summary JSON: {e}", exc_info=True)
                return None
        else:
            logging.error("  > Error: No summary was produced after reduction.")
            return None

if __name__ == "__main__":
    # This main block is for demonstration.
    # The actual execution will be orchestrated by main.py
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logging.info("This script is intended to be run from main.py.")
    logging.info("To test, ensure GROQ_API_KEY is set and required packages are installed.")
    # from langchain_community.document_loaders import ArxivLoader
    # loader = ArxivLoader(query="2305.15334", load_max_docs=1) # Example paper on retrieval
    # docs = loader.load()
    # document_content = docs[0].page_content
    
    # test_config = {
    #     "model": "llama3-70b-8192",
    #     "temperature": 0.2,
    #     "chunk_size": 4000,
    #     "chunk_overlap": 200
    # }
    
    # summarizer = CSPaperSummarizer(document_content, config=test_config)
    # summary = summarizer.summarize()
    # print(json.dumps(summary, indent=2))
