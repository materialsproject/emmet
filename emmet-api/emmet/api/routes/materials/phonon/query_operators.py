from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial

from fastapi import Query

from emmet.api.query_operator import BoolQuery, InQuery, QueryOperator
from emmet.api.utils import STORE_PARAMS, process_identifiers, split_csv
from emmet.core.phonon import PhononStabilityClass


@dataclass
class MultiPhononIDQuery(InQuery):
    """Generate a query for different phonon ids."""

    field_name: str = "identifier"
    pre_processor: Callable[[str], list[str]] = field(
        default=partial(process_identifiers, use_prefix=False)
    )

    def query(
        self,
        identifiers: str | None = Query(
            None, description="Comma-separated list of phonon_ids to query on"
        ),
    ) -> STORE_PARAMS:
        return self._prepare_query(identifiers)


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


_STABILITY_CLASSES = ", ".join(c.value for c in PhononStabilityClass)


def _parse_stability_classes(values: str) -> list[str]:
    return [PhononStabilityClass(v).value for v in split_csv(values)]


@dataclass
class PhononStabilityClassQuery(InQuery):
    """Generate a query for phonon stability classes."""

    field_name: str = "phonon_stability_class"
    pre_processor: Callable[[str], list[str]] = field(default=_parse_stability_classes)

    def query(
        self,
        phonon_stability_class: str | None = Query(
            None,
            description=(
                "Comma-separated list of phonon stability classes to query on "
                f"({_STABILITY_CLASSES})."
            ),
        ),
    ) -> STORE_PARAMS:
        return self._prepare_query(phonon_stability_class)


@dataclass
class EnlargedSupercellQuery(BoolQuery):
    """Generate a query on whether an enlarged supercell was used."""

    field_name: str = "enlarged_supercell_used"

    def query(
        self,
        enlarged_supercell_used: bool | None = Query(
            None,
            description=(
                "Whether an enlarged supercell was used. False matches only "
                "documents with an explicit False value."
            ),
        ),
    ) -> STORE_PARAMS:
        return self._prepare_query(enlarged_supercell_used)
