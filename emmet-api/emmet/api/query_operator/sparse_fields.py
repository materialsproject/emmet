from fastapi import Query
from pydantic import BaseModel

from emmet.api.query_operator import QueryOperator
from emmet.api.utils import STORE_PARAMS
from emmet.core.utils import dynamic_import


class SparseFieldsQuery(QueryOperator):

    def __init__(self, model: type[BaseModel], default_fields: list[str] | None = None):
        """
        Args:
            model: PyDantic Model that represents the underlying data source
            default_fields: default fields to return in the API response if no fields are explicitly requested.
        """
        self.model = model

        model_name = self.model.__name__  # type: ignore
        model_fields = list(self.model.__fields__.keys())  # type: ignore

        self.default_fields = (
            model_fields if default_fields is None else list(default_fields)
        )

        def query(
            _fields: str = Query(
                None,
                description=f"Fields to project from {model_name!s} as a list of comma separated strings.\
                    Fields include: `{'` `'.join(model_fields)}`",
            ),
            _all_fields: bool = Query(False, description="Include all fields."),
        ) -> STORE_PARAMS:
            """
            Pagination parameters for the API Endpoint.
            """
            properties = (
                _fields.split(",") if isinstance(_fields, str) else self.default_fields
            )
            if _all_fields:
                properties = model_fields

            return {"properties": properties}

        self.query = query  # type: ignore

    def query(self):
        """Stub query function for abstract class."""

    def meta(self) -> dict:
        """
        Returns metadata for the Sparse field set.
        """
        return {"default_fields": self.default_fields}

    def as_dict(self) -> dict:
        """
        Special as_dict implemented to convert pydantic models into strings.
        """
        d = super().as_dict()  # Ensures sub-classes serialize correctly
        d["model"] = f"{self.model.__module__}.{self.model.__name__}"  # type: ignore
        return d

    @classmethod
    def from_dict(cls, d):
        """
        Special from_dict to autoload the pydantic model from the location string.
        """
        model = d.get("model")
        if isinstance(model, str):
            model = dynamic_import(model)

        assert issubclass(
            model, BaseModel
        ), "The resource model has to be a PyDantic Model"
        d["model"] = model

        return cls(**d)
