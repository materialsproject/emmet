from dataclasses import dataclass

from emmet.api.query_operator import QueryOperator
from emmet.api.utils import STORE_PARAMS, process_identifiers


@dataclass
class CompoundIDQuery(QueryOperator):
    """Query an identifier field that is a composition of multiple document fields.

    Supports querying one or multiple suffixed IDs.

    Will assume that the name of the input query is
    `field_name`s.

    See emmet.api.routes.materials.thermo.query_operators.MultiThermoIDQuery
    for a concrete implementation.
    """

    field_name: str = "identifier"
    identifier_fields: tuple[str, ...] = ("material_id",)
    separator: str = "-"

    @property
    def num_suffixes(self) -> int:
        return len(self.identifier_fields) - 1

    @staticmethod
    def process_base_identifier(identifier: str) -> str:
        """Optionally validate identifier."""
        return process_identifiers(identifier)[0]

    def query(self, **kwargs) -> STORE_PARAMS:

        identifiers = {
            v.strip() for v in (kwargs.get(f"{self.field_name}s") or "").split(",") if v
        }
        if len(identifiers) == 0:
            return {"criteria": {}}

        identifiers_as_components = [
            idx.rsplit(self.separator, self.num_suffixes) for idx in identifiers
        ]
        for i, split_idx in enumerate(identifiers_as_components):
            identifiers_as_components[i][0] = self.process_base_identifier(split_idx[0])
        self.identifiers = [
            self.separator.join(split_idx) for split_idx in identifiers_as_components
        ]

        components = [
            sorted(set(component_subset))
            for component_subset in zip(*identifiers_as_components)
        ]

        # Always do an $in here because the insertion electrodes only have a `material_ids` field
        # and we need to check if >= 1 material_id exists in that list
        crit = {
            f"{field}": {"$in": components[i]}
            for i, field in enumerate(self.identifier_fields)
        }

        return {"criteria": crit}

    def post_process(self, docs: list[dict], query: dict) -> list[dict]:
        """Remove false positive matches.

        Args:
            docs: the document results to post-process
            query: the store query dict to use in post-processing
        """
        return [
            doc
            for doc in docs
            if self.separator.join(doc.get(k, "") for k in self.identifier_fields)
            in self.identifiers
        ]
