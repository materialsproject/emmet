"""Define schemas for pymatgen entry-like objects."""

from __future__ import annotations

from importlib import import_module
from pydantic import BaseModel, Field, field_validator, field_serializer

from typing import Literal, TYPE_CHECKING

from emmet.core.atoms.base import Compound
from emmet.core.atoms.periodic import Material
from emmet.core.mpid_ext import ThermoID
from emmet.core.types.enums import IgnoreCaseEnum
from emmet.core.types.mson import MSONType
from emmet.core.types.typing import DateTimeType, IdentifierType, JsonDictType
from emmet.core.vasp.calc_types.enums import RunType
from emmet.core.vasp.calculation import PotcarSpec

if TYPE_CHECKING:
    from typing_extensions import Self
    from pymatgen.entries.computed_entries import ComputedEntry, ComputedStructureEntry

CORRECTION_NAME = {
    "MP GGA(+U)/r2SCAN mixing adjustment",
    "MP2020 GGA/GGA+U mixing correction (Co)",
    "MP2020 GGA/GGA+U mixing correction (Cr)",
    "MP2020 GGA/GGA+U mixing correction (Fe)",
    "MP2020 GGA/GGA+U mixing correction (Mn)",
    "MP2020 GGA/GGA+U mixing correction (Mo)",
    "MP2020 GGA/GGA+U mixing correction (Ni)",
    "MP2020 GGA/GGA+U mixing correction (V)",
    "MP2020 GGA/GGA+U mixing correction (W)",
    "MP2020 anion correction (Br)",
    "MP2020 anion correction (Cl)",
    "MP2020 anion correction (F)",
    "MP2020 anion correction (H)",
    "MP2020 anion correction (I)",
    "MP2020 anion correction (N)",
    "MP2020 anion correction (S)",
    "MP2020 anion correction (Sb)",
    "MP2020 anion correction (Se)",
    "MP2020 anion correction (Si)",
    "MP2020 anion correction (Te)",
    "MP2020 anion correction (oxide)",
    "MP2020 anion correction (ozonide)",
    "MP2020 anion correction (peroxide)",
    "MP2020 anion correction (superoxide)",
}
"""These are all the valid correction names that exist in our DB."""


class OxideType(IgnoreCaseEnum):
    """Define oxide types used in corrections schemes."""

    HYDROXIDE = "hydroxide"
    PEROXIDE = "peroxide"
    SUPEROXIDE = "superoxide"
    OXIDE = "oxide"
    OZONIDE = "ozonide"
    NONE = None

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str) and value == "None":
            # pymatgen uses a str "None" instead of null
            return cls.NONE
        super(cls)._missing_(value)


class EntryParameters(BaseModel):
    """Schematize entry parameters."""

    run_type: RunType | None = None
    is_hubbard: bool = False
    hubbards: JsonDictType = None
    potcar_spec: list[PotcarSpec] | None = None


class EntryData(BaseModel):
    """Schematize entry run data."""

    oxide_type: OxideType = OxideType.NONE
    aspherical: bool = False
    last_updated: DateTimeType
    task_id: IdentifierType = None
    material_id: IdentifierType = None
    oxidation_states: JsonDictType = None
    license: Literal["BY-C", "BY-NC"] = "BY-C"
    run_type: RunType | None = None


class EnergyAdjustment(BaseModel):
    """Schematize energy adjustment/correction from pymatgen."""

    value: float | None = None
    adj_per_atom: float | None = None
    n_atoms: int | None = None
    uncertainty_per_atom: float | None = None
    name: Literal[*CORRECTION_NAME] = None
    description: str | None = None
    klass: MSONType | None = Field(None, validation_alias="cls")

    @property
    def correction(self) -> float | None:
        """Get the actual value of the correction."""
        if self.value is not None:
            return self.value
        elif self.adj_per_atom is not None and self.n_atoms is not None:
            return self.adj_per_atom * self.n_atoms
        return None


class Entry(BaseModel):
    """Schematize pymatgen ComputedEntry."""

    composition: Compound

    energy: float | None = None
    correction: float | None = None
    entry_id: ThermoID | None = None

    energy_adjustments: list[EnergyAdjustment] = Field([])
    parameters: EntryParameters | None = None
    data: EntryData | None = None

    @field_validator("entry_id", mode="before")
    def _deser_thermo_id(cls, v) -> ThermoID | None:
        return ThermoID._deserialize(v) if v is not None else None

    @field_serializer("entry_id")
    def _ser_thermo_id(self, v: ThermoID) -> str:
        return str(v)

    def to_pmg(self) -> ComputedEntry | ComputedStructureEntry:
        data = self.model_dump()
        pmg_cls = "ComputedEntry"
        if data.get("structure"):
            data["structure"] = Material(data["structure"]).to_pmg()
            pmg_cls = "ComputedStructureEntry"

        pmg_entries = import_module("pymatgen.entries.computed_entries")
        return getattr(pmg_entries, pmg_cls).from_dict(data)

    @classmethod
    def from_pmg(cls, entry: ComputedEntry | ComputedStructureEntry) -> Self:
        config = entry.as_dict()
        config["composition"] = Compound.from_dict(config["composition"])
        if config.get("structure"):
            config["structure"] = Material.from_pmg(entry.structure)
        return cls(**config)


class StructureEntry(Entry):
    """Schematize pymatgen ComputedStructureEntry."""

    structure: Material
