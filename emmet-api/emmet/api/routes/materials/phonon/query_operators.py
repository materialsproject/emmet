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


_PHEASY_FIT_ROUTES = (
    "ASR",
    "ASR + BH",
    "ASR + BH + H",
    "ASR + BH(dipole)",
    "ASR + BH(dipole) + H",
    "ASR + BH(dipole) + H(dipole)",
)
_PHEASY_FIT_ROUTES_SET = frozenset(_PHEASY_FIT_ROUTES)

_NO_NAC_REASONS = (
    "no_dielectric_run",
    "identity_dielectric_tensor",
    "unusable_dielectric_run",
)
_NO_NAC_REASONS_SET = frozenset(_NO_NAC_REASONS)


def _parse_pheasy_fit_routes(values: str) -> list[str]:
    parsed = split_csv(values)
    for v in parsed:
        if v not in _PHEASY_FIT_ROUTES_SET:
            raise ValueError(
                f"Invalid pheasy_fit_route {v!r}. Must be one of: "
                f"{', '.join(_PHEASY_FIT_ROUTES)}."
            )
    return parsed


def _parse_no_nac_reasons(values: str) -> list[str]:
    parsed = split_csv(values)
    for v in parsed:
        if v not in _NO_NAC_REASONS_SET:
            raise ValueError(
                f"Invalid no_nac_reason {v!r}. Must be one of: "
                f"{', '.join(_NO_NAC_REASONS)}."
            )
    return parsed


def _parse_versions(values: str) -> list[str]:
    parsed = split_csv(values)
    if any(not v for v in parsed):
        raise ValueError("Version entries cannot be empty.")
    return parsed


@dataclass
class PheasyFitRouteQuery(InQuery):
    """Generate a query for Pheasy invariance fit routes."""

    field_name: str = "pheasy_fit_route"
    pre_processor: Callable[[str], list[str]] = field(default=_parse_pheasy_fit_routes)

    def query(
        self,
        pheasy_fit_route: str | None = Query(
            None,
            description=(
                "Comma-separated list of Pheasy invariance fit routes to query on "
                f"({', '.join(_PHEASY_FIT_ROUTES)})."
            ),
        ),
    ) -> STORE_PARAMS:
        return self._prepare_query(pheasy_fit_route)


@dataclass
class HasNacQuery(BoolQuery):
    """Generate a query on whether non-analytical correction (NAC) was applied."""

    field_name: str = "has_nac"

    def query(
        self,
        has_nac: bool | None = Query(
            None,
            description=(
                "Whether non-analytical correction (NAC) was applied. False matches "
                "only documents with an explicit False value."
            ),
        ),
    ) -> STORE_PARAMS:
        return self._prepare_query(has_nac)


@dataclass
class NoNacReasonQuery(InQuery):
    """Generate a query for reasons non-analytical correction was not applied."""

    field_name: str = "no_nac_reason"
    pre_processor: Callable[[str], list[str]] = field(default=_parse_no_nac_reasons)

    def query(
        self,
        no_nac_reason: str | None = Query(
            None,
            description=(
                "Comma-separated list of no-NAC reasons to query on "
                f"({', '.join(_NO_NAC_REASONS)})."
            ),
        ),
    ) -> STORE_PARAMS:
        return self._prepare_query(no_nac_reason)


@dataclass
class PhononVersionQuery(InQuery):
    """Generate a query for phonon dataset release versions."""

    field_name: str = "version"
    pre_processor: Callable[[str], list[str]] = field(default=_parse_versions)

    def query(
        self,
        version: str | None = Query(
            None,
            description=(
                "Comma-separated list of phonon dataset versions to query on "
                "(e.g. 'v1.1', 'v1.2')."
            ),
        ),
    ) -> STORE_PARAMS:
        return self._prepare_query(version)
