import os
import json
import logging
from typing import List, Dict, Any, Optional

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage
from groq import RateLimitError, APIError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, RetryError
from .base import AbstractClassifier
from .llm_services import BaseLLMService

class KeywordClassifier:
    """
    키워드 기반으로 논문의 점수를 매기는 분류기 (1차 필터링용)
    """
    def __init__(self, keyword_weights: Dict[str, int]):
        """
        :param keyword_weights: 점수 계산에 사용할 키워드와 가중치 딕셔너리
                                예: {"retrieval": 2, "commerce": 3}
        """
        if not keyword_weights:
            raise ValueError("keyword_weights must not be empty.")
        self.keyword_weights = {k.lower(): v for k, v in keyword_weights.items()}

    def score(self, papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        논문 목록을 받아 각 논문에 점수를 매기고 정렬하여 반환
        """
        scored_papers = []
        for paper in papers:
            score = 0
            reasons = []
            
            # 검색할 텍스트 필드 (제목과 초록)
            text_to_search = f"{paper.get('title', '').lower()} {paper.get('abstract', '').lower()}"
            
            for keyword, weight in self.keyword_weights.items():
                if keyword in text_to_search:
                    score += weight
                    reasons.append(f"Found '{keyword}' (score: +{weight})")
            
            paper['score'] = score
            paper['keyword_reasons'] = reasons
            scored_papers.append(paper)
            
        # 점수가 0보다 큰 논문만 필터링하고, 점수 기준으로 내림차순 정렬
        filtered_and_sorted = sorted(
            [p for p in scored_papers if p['score'] > 0],
            key=lambda x: x['score'],
            reverse=True
        )
        
        return filtered_and_sorted

class LLMClassifier(AbstractClassifier, BaseLLMService):
    """LLM을 사용하여 논문의 점수를 매기는 분류기"""

    def __init__(self, config: dict, groq_config: dict):
        """
            LLMClassifier를 초기화합니다.

            :param config: llm_scorer에 대한 설정 딕셔너리
            :param groq_config: groq_settings에 대한 공통 설정 딕셔너리
        """
        combined_config = {**groq_config, **config}
        super().__init__(config=combined_config)
        
        self.interests = config.get("interests", "")
        if not self.interests:
            raise ValueError("Interests must be defined in the config for LLMClassifier.")
        
        prompt_path = os.path.join(os.path.dirname(__file__), '..', 'configs', 'prompt.json')
        with open(prompt_path, 'r', encoding='utf-8') as f:
            self.prompt_template = json.load(f)["scoring"]

    def score_paper(self, paper: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """단일 논문에 대해 LLM 기반 스코어링 수행"""
        user_prompt = self.prompt_template["user_prompt"].format(
            interests=self.interests,
            title=paper.get('title', ''),
            abstract=paper.get('abstract', '')
        )
        system_prompt = self.prompt_template["system_prompt"]
        
        try:
            # HumanMessage 대신 딕셔너리 리스트로 메시지 구성
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            response_str = self._invoke_with_fallback(messages, is_json=True)
            
            if response_str is None:
                logging.error(f"LLM scoring failed for paper '{paper.get('title', '')[:20]}...' after trying all fallback models.")
                return None
            return json.loads(response_str)
        except Exception as e:
            logging.error(f"Error processing LLM response for paper '{paper.get('title', '')[:20]}...': {e}", exc_info=True)
            return None

    def score(self, papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """논문 목록을 받아 각 논문에 LLM 기반 점수를 매기고 정렬하여 반환"""
        scored_papers = []
        for i, paper in enumerate(papers):
            logging.info(f"LLM Scoring paper {i+1}/{len(papers)}: \"{paper.get('title', '')[:50]}...\"")
            
            response = self.score_paper(paper)
            
            if response and 'score' in response and 'reasons' in response:
                paper['llm_score'] = response.get('score', 0)
                paper['llm_reason'] = response.get('reasons', 'N/A')
            else:
                paper['llm_score'] = 0
                paper['llm_reason'] = "LLM scoring failed."
            
            scored_papers.append(paper)
            
        filtered_and_sorted = sorted(
            [p for p in scored_papers if p.get('llm_score', 0) > 0],
            key=lambda x: x.get('llm_score', 0),
            reverse=True
        )
        return filtered_and_sorted

if __name__ == '__main__':
    # 예제 사용법은 main.py에서 통합적으로 보여주는 것이 더 적합합니다.
    # 기존 KeywordClassifier의 예제만 남겨둡니다.
    # 예제 사용법
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    sample_papers = [
        {
            "title": "A new approach to Information Retrieval",
            "abstract": "We discuss retrieval models and their impact.",
            "url": "http://example.com/1"
        },
        {
            "title": "Understanding user Clicks in e-commerce",
            "abstract": "This paper analyzes click patterns in online commerce.",
            "url": "http://example.com/2"
        },
        {
            "title": "Machine Learning for Cats",
            "abstract": "A study of feline behavior.",
            "url": "http://example.com/3"
        }
    ]

    # 점수를 매길 키워드와 가중치
    keywords = {
        "retrieval": 2,
        "commerce": 3,
        "click": 2
    }

    classifier = KeywordClassifier(keyword_weights=keywords)
    classified = classifier.score(sample_papers)

    logging.info(f"Found {len(classified)} relevant papers:")
    for paper in classified:
        logging.info(
            f"Score: {paper['score']}, "
            f"Title: {paper['title']}, "
            f"Reasons: {paper['reasons']}"
        ) 