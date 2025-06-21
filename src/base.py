from abc import ABC, abstractmethod
from typing import List, Dict, Any
from datetime import date

class AbstractCrawler(ABC):
    @abstractmethod
    def fetch(self, queries: List[str], max_results: int, target_date: date) -> List[Dict[str, Any]]:
        """
        Fetches papers based on a list of queries for a specific date.

        :param queries: A list of search queries.
        :param max_results: The maximum number of results to return per query.
        :param target_date: The specific date to filter papers by.
        :return: A list of dictionaries, where each dictionary represents a paper.
        """
        pass

class AbstractClassifier(ABC):
    @abstractmethod
    def score(self, papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Scores and sorts a list of papers.

        :param papers: A list of paper dictionaries to score.
        :return: A list of scored and sorted paper dictionaries.
        """
        pass 