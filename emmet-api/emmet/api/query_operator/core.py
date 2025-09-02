from abc import ABC, abstractmethod

from emmet.api.utils import STORE_PARAMS


class QueryOperator(ABC):
    """
    Base Query Operator class for defining powerful query language
    in the Materials API.
    """

    @abstractmethod
    def query(self) -> STORE_PARAMS:
        """
        The query function that does the work for this query operator.
        """

    def meta(self) -> dict:
        """
        Returns meta data to return with the Response.

        Args:
            store: the Maggma Store that the resource uses
            query: the query being executed in this API call
        """
        return {}

    def post_process(self, docs: list[dict], query: dict) -> list[dict]:
        """
        An optional post-processing function for the data.

        Args:
            docs: the document results to post-process
            query: the store query dict to use in post-processing
        """
        return docs
