from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial

from fastapi import Query

from emmet.api.query_operator import InQuery, QueryOperator
from emmet.api.utils import STORE_PARAMS, process_identifiers


@dataclass
class MultiPhononIDQuery(InQuery):
    """Generate a query for different phonon ids."""

    field_name: str = "identifier"
    pre_processor: Callable[[str], list[str]] = field(
        default=partial(process_identifiers, use_prefix=False)
    )

    def query(
        self,
        phonon_ids: str | None = Query(
            None, description="Comma-separated list of phonon_ids to query on"
        ),
    ) -> STORE_PARAMS:
        return self._prepare_query(phonon_ids)


class PhononMethodQuery(QueryOperator):
    """
    Method to query phonon method
    """

    def query(
        self,
        phonon_method: str = Query(
            None,
            description="Phonon Method to search for",
        ),
    ) -> STORE_PARAMS:
        crit = {}
        if phonon_method in {"dfpt", "phonopy", "pheasy"}:
            crit = {"phonon_method": phonon_method}

        return {"criteria": crit}
