from abc import abstractmethod
from dataclasses import dataclass

from emmet.api.query_operator import QueryOperator
from emmet.api.utils import STORE_PARAMS
from emmet.core.types.typing import CompoundID


@dataclass
class CompoundIDQuery(QueryOperator):
    """Query an identifier field that is a composition of multiple document fields.

    Supports querying one or multiple suffixed IDs.

    Will assume that the name of the input query is
    `field_name`s.

    See emmet.api.routes.materials.thermo.query_operators.MultiThermoIDQuery
    for a concrete implementation.

    Args:
    field_name (str) : Name of the compound identifier field
    identifier_fields (tuple of str) : Names of the fields which
        compose the compound identifier. The first field is
        assumed to be AlphaID-like. The second and any ensuing fields
        are assumened to be Enum-like.
    """

    field_name: str = "identifier"
    identifier_fields: tuple[str, ...] = ("material_id",)

    @staticmethod
    @abstractmethod
    def validate_identifer(idx: str) -> CompoundID:
        """Validate a compound ID consistent with a parent schema."""

    @property
    def num_suffixes(self) -> int:
        return len(self.identifier_fields) - 1

    def query(self, **kwargs) -> STORE_PARAMS:

        identifiers = {
            v.strip() for v in (kwargs.get(f"{self.field_name}s") or "").split(",") if v
        }
        if len(identifiers) == 0:
            return {"criteria": {}}

        identifiers_as_components = [
            self.validate_identifer(idx) for idx in identifiers
        ]

        components = {
            self.identifier_fields[0]: {
                str(component["identifier"]) for component in identifiers_as_components
            },
            **{
                suffix: {
                    component["suffix"][i].value
                    for component in identifiers_as_components
                }
                for i, suffix in enumerate(self.identifier_fields[1:])
            },
        }

        return {"criteria": {k: {"$in": sorted(v)} for k, v in components.items()}}
