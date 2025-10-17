"""Core definition of a Thermo Document"""

from __future__ import annotations

from collections import defaultdict
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field, PlainSerializer
from pymatgen.analysis.phase_diagram import PhaseDiagram
from pymatgen.entries.computed_entries import ComputedEntry, ComputedStructureEntry

from emmet.core.base import EmmetMeta
from emmet.core.material import PropertyOrigin
from emmet.core.material_property import PropertyDoc
from emmet.core.mpid_ext import ThermoID
from emmet.core.types.enums import ThermoType
from emmet.core.types.pymatgen_types.computed_entries_adapter import (
    ComputedStructureEntryType,
)
from emmet.core.types.pymatgen_types.phase_diagram_adapter import PhaseDiagramType
from emmet.core.types.typing import DateTimeType, IdentifierType
from emmet.core.utils import type_override, utcnow
from emmet.core.vasp.calc_types.enums import RunType


class DecompositionProduct(BaseModel):
    """
    Entry metadata for a decomposition process
    """

    material_id: IdentifierType | None = Field(
        None,
        description="The Materials Project ID for the material this decomposition points to.",
    )
    formula: str | None = Field(
        None,
        description="The formula of the decomposed material this material decomposes to.",
    )
    amount: float | None = Field(
        None,
        description="The amount of the decomposed material by formula units this this material decomposes to.",
    )


@type_override({"thermo_type": ThermoType, "thermo_id": str})
class ThermoDoc(PropertyDoc):
    """
    A thermo entry document
    """

    property_name: str = "thermo"

    thermo_type: ThermoType | RunType = Field(
        ...,
        description="Functional types of calculations involved in the energy mixing scheme.",
    )

    thermo_id: Annotated[
        ThermoID,
        Field(
            description="Unique document ID which is composed of the Material ID and thermo data type.",
        ),
        PlainSerializer(str),
        BeforeValidator(ThermoID._deserialize),
    ]

    uncorrected_energy_per_atom: float = Field(
        ..., description="The total DFT energy of this material per atom in eV/atom."
    )

    energy_per_atom: float = Field(
        ...,
        description="The total corrected DFT energy of this material per atom in eV/atom.",
    )

    energy_uncertainy_per_atom: float | None = Field(None, description="")

    formation_energy_per_atom: float | None = Field(
        None, description="The formation energy per atom in eV/atom."
    )

    energy_above_hull: float = Field(
        ..., description="The energy above the hull in eV/Atom."
    )

    is_stable: bool = Field(
        False,
        description="Flag for whether this material is on the hull and therefore stable.",
    )

    equilibrium_reaction_energy_per_atom: float | None = Field(
        None,
        description="The reaction energy of a stable entry from the neighboring equilibrium stable materials in eV."
        " Also known as the inverse distance to hull.",
    )

    decomposes_to: list[DecompositionProduct] | None = Field(
        None,
        description="List of decomposition data for this material. Only valid for metastable or unstable material.",
    )

    decomposition_enthalpy: float | None = Field(
        None,
        description="Decomposition enthalpy as defined by `get_decomp_and_phase_separation_energy` in pymatgen.",
    )

    decomposition_enthalpy_decomposes_to: list[DecompositionProduct] | None = Field(
        None,
        description="List of decomposition data associated with the decomposition_enthalpy quantity.",
    )

    energy_type: str = Field(
        ...,
        description="The type of calculation this energy evaluation comes from.",
    )

    entry_types: list[str] = Field(
        description="List of available energy types computed for this material."
    )
    entries: dict[str, ComputedStructureEntryType] = Field(
        ...,
        description="List of all entries that are valid for this material."
        " The keys for this dictionary are names of various calculation types.",
    )

    @classmethod
    def from_entries(
        cls,
        entries: list[ComputedEntry | ComputedStructureEntry],
        thermo_type: ThermoType | RunType,
        phase_diagram: PhaseDiagram | None = None,
        use_max_chemsys: bool = False,
        **kwargs,
    ):
        """Produce a list of ThermoDocs from a list of Entry objects

        Args:
            entries (list[ComputedEntry| ComputedStructureEntry]): list of Entry objects
            thermo_type (ThermoType | RunType): Thermo type
            phase_diagram (PhaseDiagram | None, optional): Already built phase diagram. Defaults to None.
            use_max_chemsys (bool, optional): Whether to only produce thermo docs for materials
                that match the largest chemsys represented in the list. Defaults to False.

        Returns:
            list[ThermoDoc]: list of built thermo doc objects.
        """

        pd = phase_diagram or cls.construct_phase_diagram(entries)

        chemsys = "-".join(sorted([str(e) for e in pd.elements]))

        docs = []

        entries_by_mpid = defaultdict(list)
        for e in entries:
            entries_by_mpid[e.data["material_id"]].append(e)

        entry_quality_scores = {"GGA": 1, "GGA+U": 2, "SCAN": 3, "r2SCAN": 4}

        def _energy_eval(entry: ComputedStructureEntry | ComputedEntry):
            """
            Helper function to order entries for thermo energy data selection
            - Run type
            - LASPH
            - Energy
            """

            return (
                -1 * entry_quality_scores.get(entry.data["run_type"], 0),
                -1 * int(entry.data.get("aspherical", False)),
                entry.energy,
            )

        for material_id, entry_group in entries_by_mpid.items():
            if (
                use_max_chemsys
                and entry_group[0].composition.chemical_system != chemsys
            ):
                continue

            sorted_entries = sorted(entry_group, key=_energy_eval)

            blessed_entry = sorted_entries[0]

            (decomp, ehull) = pd.get_decomp_and_e_above_hull(blessed_entry)  # type: ignore[arg-type]

            builder_meta = EmmetMeta(license=blessed_entry.data.get("license"))

            d = {
                "thermo_id": "{}_{}".format(material_id, str(thermo_type)),
                "material_id": material_id,
                "thermo_type": thermo_type,
                "uncorrected_energy_per_atom": blessed_entry.uncorrected_energy
                / blessed_entry.composition.num_atoms,
                "energy_per_atom": blessed_entry.energy
                / blessed_entry.composition.num_atoms,
                "formation_energy_per_atom": pd.get_form_energy_per_atom(blessed_entry),  # type: ignore[arg-type]
                "energy_above_hull": ehull,
                "is_stable": blessed_entry in pd.stable_entries,
                "builder_meta": builder_meta.model_dump(),
            }

            # Uncomment to make last_updated line up with materials.
            # if "last_updated" in blessed_entry.data:
            #     d["last_updated"] = blessed_entry.data["last_updated"]

            # Store different info if stable vs decomposes
            if d["is_stable"]:
                d[
                    "equilibrium_reaction_energy_per_atom"
                ] = pd.get_equilibrium_reaction_energy(
                    blessed_entry  # type: ignore[arg-type]
                )
            else:
                d["decomposes_to"] = [
                    {
                        "material_id": de.data["material_id"],  # type: ignore[union-attr]
                        "formula": de.composition.formula,
                        "amount": amt,
                    }
                    for de, amt in decomp.items()  # type: ignore[union-attr]
                ]

            try:
                decomp, energy = pd.get_decomp_and_phase_separation_energy(
                    blessed_entry  # type: ignore[arg-type]
                )
                d["decomposition_enthalpy"] = energy
                d["decomposition_enthalpy_decomposes_to"] = [
                    {
                        "material_id": de.data["material_id"],  # type: ignore[union-attr]
                        "formula": de.composition.formula,
                        "amount": amt,
                    }
                    for de, amt in decomp.items()  # type: ignore[union-attr]
                ]
            except ValueError:
                # try/except so this quantity does not take down the builder if it fails:
                # it includes an optimization step that can be fragile in some instances,
                # most likely failure is ValueError, "invalid value encountered in true_divide"
                d["warnings"] = [
                    "Could not calculate decomposition enthalpy for this entry."
                ]

            d["energy_type"] = blessed_entry.parameters.get("run_type", "Unknown")
            d["entry_types"] = []
            d["entries"] = {}

            # Currently, each entry group contains a single entry due to how the compatibility scheme works
            for entry in entry_group:
                d["entry_types"].append(entry.parameters.get("run_type", "Unknown"))
                d["entries"][entry.parameters.get("run_type", "Unknown")] = entry

            d["origins"] = [
                PropertyOrigin(
                    name="energy",
                    task_id=blessed_entry.data["task_id"],
                    last_updated=d.get("last_updated", utcnow()),
                )
            ]

            docs.append(
                ThermoDoc.from_structure(
                    meta_structure=blessed_entry.structure, **d, **kwargs  # type: ignore[attr-defined]
                )
            )

        return docs

    @staticmethod
    def construct_phase_diagram(entries) -> PhaseDiagram:
        """
        Efficienty construct a phase diagram using only the lowest entries at every composition
        represented in the entry data passed.

        Args:
            entries (list[ComputedStructureEntry]): list of corrected pymatgen entry objects.

        Returns:
            PhaseDiagram: Pymatgen PhaseDiagram object
        """
        entries_by_comp = defaultdict(list)
        for e in entries:
            entries_by_comp[e.composition.reduced_formula].append(e)

        # Only use lowest entry per composition to speed up QHull in Phase Diagram
        reduced_entries = [
            sorted(comp_entries, key=lambda e: e.energy_per_atom)[0]
            for comp_entries in entries_by_comp.values()
        ]
        pd = PhaseDiagram(reduced_entries)

        # Add back all entries, not just those on the hull
        pd_computed_data = pd.computed_data
        pd_computed_data["all_entries"] = entries
        new_pd = PhaseDiagram(
            entries, elements=pd.elements, computed_data=pd_computed_data
        )
        return new_pd


@type_override({"thermo_type": ThermoType})
class PhaseDiagramDoc(BaseModel):
    """
    A phase diagram document
    """

    property_name: str = "phase_diagram"

    phase_diagram_id: str = Field(
        ...,
        description="Phase diagram ID consisting of the chemical system and thermo type",
    )

    chemsys: str = Field(
        ...,
        description="Dash-delimited string of elements in the material",
    )

    thermo_type: ThermoType | RunType = Field(
        ...,
        description="Functional types of calculations involved in the energy mixing scheme.",
    )

    phase_diagram: PhaseDiagramType = Field(
        ...,
        description="Phase diagram for the chemical system.",
    )

    last_updated: DateTimeType = Field(
        description="Timestamp for the most recent calculation update for this property",
    )
