"""Define document models used by the client."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, model_validator, ConfigDict
from uncertainties import ufloat_fromstr

from emmet.core.connectors.analysis import parse_cif
from emmet.core.connectors.icsd.enums import IcsdSubset
from emmet.core.types.pymatgen_types.structure_adapter import StructureType

if TYPE_CHECKING:
    from typing import Any


class UFloat(BaseModel):
    value: float | None = None
    uncertainty: float | None = None

    @model_validator(mode="before")
    @classmethod
    def parse_uncert(cls, config: Any) -> Any:
        if isinstance(config, str):
            if "(" in config:
                parsed = ufloat_fromstr(config)
                config = {"value": parsed.n, "uncertainty": parsed.s}
            else:
                try:
                    config = {"value": float(config)}
                except ValueError:
                    config = {}
        return config


class CellParameters(BaseModel):

    a: UFloat | None = None
    b: UFloat | None = None
    c: UFloat | None = None
    alpha: UFloat | None = None
    beta: UFloat | None = None
    gamma: UFloat | None = None

    @model_validator(mode="before")
    @classmethod
    def from_str(cls, config):
        """Parse space-separated lattice parameters."""
        lps = ["a", "b", "c", "alpha", "beta", "gamma"]
        if isinstance(config, str):
            vals = config.split()
            config = {lp: vals[i] for i, lp in enumerate(lps)}
        return config


class IcsdPropertyDoc(BaseModel):
    """General container for ICSD data."""

    model_config = ConfigDict(use_enum_values=True)

    collection_code: int | None = Field(
        None, description="The ICSD identifier of this entry."
    )

    icsd_internal_id: int | None = Field(
        None,
        description="The internal identifier for the ICSD, not the collection code / ICSD ID.",
    )
    cif: str | None = Field(
        None, description="The CIF file associated with this entry."
    )
    subset: IcsdSubset | None = Field(
        None, description="The subset of the ICSD to which this entry belongs."
    )
    ccdc_no: int | None = Field(None)
    ccdc: int | None = None

    h_m_s: str | None = None
    pearson_symbol: str | None = None
    wyckoff_sequence: str | None = None

    structured_formula: str | None = None
    sum_formula: str | None = None
    a_n_x_formula: str | None = None
    a_b_formula: str | None = None

    structure_type: str | None = None
    title: str | None = None
    authors: list[str] | None = None
    journal: str | None = None
    publication_year: int | None = None
    volume: int | None = None
    page: str | None = None
    reference: str | None = None

    cell_parameter: CellParameters | None = None
    reduced_cell_parameter: CellParameters | None = None
    standardised_cell_parameter: CellParameters | None = None

    cell_volume: UFloat | None = None
    formula_units_per_cell: int | None = None
    formula_weight: float | None = None

    temperature: float | None = None
    pressure: float | None = None
    r_value: float | None = None

    chemical_name: str | None = None
    mineral_name: str | None = None
    mineral_name_ima: str | None = None
    mineral_group: str | None = None
    mineral_series: str | None = None
    mineral_root_group: str | None = None
    mineral_sub_group: str | None = None
    mineral_super_group: str | None = None
    mineral_sub_class: str | None = None
    mineral_class: str | None = None

    calculated_density: UFloat | None = None
    measured_density: UFloat | None = None

    quality: int | None = None
    keywords: str | None = None

    pdf: str | None = None

    structures: list[StructureType] | None = Field(
        None, description="A list of validated `Structure`s parsed from the CIF."
    )
    cif_parsing_errors: list[str] | None = Field(
        None, description="A list of any errors encountered while parsing the CIF."
    )

    @model_validator(mode="before")
    @classmethod
    def deserialize(cls, config: Any) -> Any:
        """Parse ICSD data into a structured format."""
        if isinstance(config.get("authors"), str):
            config["authors"] = config["authors"].split(";")

        for k, v in config.items():
            if isinstance(v, str) and len(v) == 0:
                config[k] = None

        if config.get("cif") and config.get("structures") is None:
            config["structures"], config["cif_parsing_errors"] = parse_cif(
                config["cif"]
            )

        if not config.get("cif_parsing_errors"):
            config.pop("cif_parsing_errors")

        return config
