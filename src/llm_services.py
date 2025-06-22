import os
import logging
from typing import List, Dict, Any, Optional
from groq import Groq, RateLimitError, APIError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, RetryError

class BaseLLMService:
    """
    Groq LLM 서비스를 직접 사용하기 위한 기본 클래스.
    API 키 로딩, LLM 객체 초기화, 폴백 및 재시도 로직을 포함
    """
    def __init__(self, config: dict):
        self.config = config
        self.model_name = config.get("model")
        if not self.model_name:
            raise ValueError("A 'model' must be specified in the LLM service config.")

        api_key = os.environ.get(config.get("api_key_env", "GROQ_API_KEY"))
        if not api_key:
            raise ValueError(f"API key not found. Please set the {config.get('api_key_env', 'GROQ_API_KEY')} environment variable.")

        self.client = Groq(api_key=api_key)

        self.model_fallback_list = config.get("model_fallback_list", [])
        if self.model_name in self.model_fallback_list:
            self.model_fallback_list.remove(self.model_name)
        self.model_fallback_list.insert(0, self.model_name)

    def _invoke_with_fallback(self, messages: List[Dict[str, str]], is_json: bool = False) -> Optional[str]:
        """모델 폴백 및 재시도 로직으로 LLM을 호출"""
        for model in self.model_fallback_list:
            try:
                logging.info(f"Attempting to use model: {model}")

                @retry(
                    wait=wait_exponential(multiplier=1, min=2, max=60),
                    stop=stop_after_attempt(3),
                    retry=retry_if_exception_type((RateLimitError, APIError)),
                    before_sleep=lambda rs: logging.warning(
                        f"Rate limit/API error on model {model}. "
                        f"Retrying in {int(rs.next_action.sleep)}s... (Attempt {rs.attempt_number})"
                    )
                )
                def invoke_with_single_model():
                    request_params = {
                        "messages": messages,
                        "model": model,
                        "temperature": self.config.get("temperature", 0.2),
                    }
                    if is_json:
                        request_params["response_format"] = {"type": "json_object"}
                    
                    chat_completion = self.client.chat.completions.create(**request_params)
                    return chat_completion.choices[0].message.content

                return invoke_with_single_model()

            except (RateLimitError, RetryError) as e:
                logging.warning(f"Rate limit retries failed for model '{model}'. Trying next model. Error: {e}")
                continue
        
        logging.error("All models in fallback list failed due to rate limits.")
        return None 