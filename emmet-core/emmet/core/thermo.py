""" Core definition of a Thermo Document """
from collections import defaultdict
from typing import Dict, List, Union
from datetime import datetime
from emmet.core.utils import ValueEnum

from pydantic import BaseModel, Field
from pymatgen.analysis.phase_diagram import PhaseDiagram, PatchedPhaseDiagram
from pymatgen.entries.computed_entries import ComputedEntry, ComputedStructureEntry

from emmet.core.material_property import PropertyDoc
from emmet.core.material import PropertyOrigin
from emmet.core.mpid import MPID
from emmet.core.vasp.calc_types.enums import RunType


class DecompositionProduct(BaseModel):
    """
    Entry metadata for a decomposition process
    """

    material_id: MPID = Field(
        None,
        description="The Materials Project ID for the material this decomposition points to.",
    )
    formula: str = Field(
        None,
        description="The formula of the decomposed material this material decomposes to.",
    )
    amount: float = Field(
        None,
        description="The amount of the decomposed material by formula units this this material decomposes to.",
    )


class ThermoType(ValueEnum):
    GGA_GGA_U = "GGA_GGA+U"
    GGA_GGA_U_R2SCAN = "GGA_GGA+U_R2SCAN"
    R2SCAN = "R2SCAN"
    UNKNOWN = "UNKNOWN"


class ThermoDoc(PropertyDoc):
    """
    A thermo entry document
    """

    property_name = "thermo"

    thermo_type: Union[ThermoType, RunType] = Field(
        ...,
        description="Functional types of calculations involved in the energy mixing scheme.",
    )

    thermo_id: str = Field(
        ...,
        description="Unique document ID which is composed of the Material ID and thermo data type.",
    )

    uncorrected_energy_per_atom: float = Field(
        ..., description="The total DFT energy of this material per atom in eV/atom."
    )

    energy_per_atom: float = Field(
        ...,
        description="The total corrected DFT energy of this material per atom in eV/atom.",
    )

    energy_uncertainy_per_atom: float = Field(None, description="")

    formation_energy_per_atom: float = Field(None, description="The formation energy per atom in eV/atom.")

    energy_above_hull: float = Field(..., description="The energy above the hull in eV/Atom.")

    is_stable: bool = Field(
        False,
        description="Flag for whether this material is on the hull and therefore stable.",
    )

    equilibrium_reaction_energy_per_atom: float = Field(
        None,
        description="The reaction energy of a stable entry from the neighboring equilibrium stable materials in eV."
        " Also known as the inverse distance to hull.",
    )

    decomposes_to: List[DecompositionProduct] = Field(
        None,
        description="List of decomposition data for this material. Only valid for metastable or unstable material.",
    )

    decomposition_enthalpy: float = Field(
        None,
        description="Decomposition enthalpy as defined by `get_decomp_and_phase_separation_energy` in pymatgen.",
    )

    decomposition_enthalpy_decomposes_to: List[DecompositionProduct] = Field(
        None,
        description="List of decomposition data associated with the decomposition_enthalpy quantity.",
    )

    energy_type: str = Field(
        ...,
        description="The type of calculation this energy evaluation comes from.",
    )

    entry_types: List[str] = Field(description="List of available energy types computed for this material.")

    entries: Dict[str, Union[ComputedEntry, ComputedStructureEntry]] = Field(
        ...,
        description="List of all entries that are valid for this material."
        " The keys for this dictionary are names of various calculation types.",
    )

    @classmethod
    def from_entries(
        cls,
        entries: List[Union[ComputedEntry, ComputedStructureEntry]],
        thermo_type: Union[ThermoType, RunType],
        **kwargs
    ):
        # Note that PatchedPhaseDiagram construct the hull using only the
        # lowest energy entries.
        patched_pd = PatchedPhaseDiagram(entries, keep_all_spaces=True)

        pd = patched_pd.pds[frozenset(patched_pd.elements)]  # Main PD of parent chemsys

        docs = []

        entries_by_mpid = defaultdict(list)
        for e in entries:
            entries_by_mpid[e.data["material_id"]].append(e)

        entry_quality_scores = {"GGA": 1, "GGA+U": 2, "SCAN": 3, "R2SCAN": 4}

        def _energy_eval(entry: ComputedStructureEntry):
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

            sorted_entries = sorted(entry_group, key=_energy_eval)

            blessed_entry = sorted_entries[0]

            (decomp, ehull) = pd.get_decomp_and_e_above_hull(blessed_entry)

            d = {
                "thermo_id": "{}_{}".format(material_id, str(thermo_type)),
                "material_id": material_id,
                "thermo_type": thermo_type,
                "uncorrected_energy_per_atom": blessed_entry.uncorrected_energy / blessed_entry.composition.num_atoms,
                "energy_per_atom": blessed_entry.energy / blessed_entry.composition.num_atoms,
                "formation_energy_per_atom": pd.get_form_energy_per_atom(blessed_entry),
                "energy_above_hull": ehull,
                "is_stable": blessed_entry in pd.stable_entries,
            }

            if "last_updated" in blessed_entry.data:
                d["last_updated"] = blessed_entry.data["last_updated"]

            # Store different info if stable vs decomposes
            if d["is_stable"]:
                d["equilibrium_reaction_energy_per_atom"] = pd.get_equilibrium_reaction_energy(blessed_entry)
            else:
                d["decomposes_to"] = [
                    {
                        "material_id": de.data["material_id"],
                        "formula": de.composition.formula,
                        "amount": amt,
                    }
                    for de, amt in decomp.items()
                ]

            try:
                decomp, energy = pd.get_decomp_and_phase_separation_energy(blessed_entry)
                d["decomposition_enthalpy"] = energy
                d["decomposition_enthalpy_decomposes_to"] = [
                    {
                        "material_id": de.data["material_id"],
                        "formula": de.composition.formula,
                        "amount": amt,
                    }
                    for de, amt in decomp.items()
                ]
            except ValueError:
                # try/except so this quantity does not take down the builder if it fails:
                # it includes an optimization step that can be fragile in some instances,
                # most likely failure is ValueError, "invalid value encountered in true_divide"
                d["warnings"] = ["Could not calculate decomposition enthalpy for this entry."]

            d["energy_type"] = blessed_entry.parameters.get("run_type", "Unknown")
            d["entry_types"] = []
            d["entries"] = {}

            # Currently, each entry group contains a single entry due to how the compatability scheme works
            for entry in entry_group:

                d["entry_types"].append(entry.parameters.get("run_type", "Unknown"))
                d["entries"][entry.parameters.get("run_type", "Unknown")] = entry

            d["origins"] = [
                PropertyOrigin(
                    name="energy",
                    task_id=blessed_entry.data["task_id"],
                    last_updated=d.get("last_updated", datetime.utcnow()),
                )
            ]

            docs.append(ThermoDoc.from_structure(meta_structure=blessed_entry.structure, **d, **kwargs))

        # Construct new phase diagrams with all of the entries, not just those on the hull
        new_pds = []
        for ele_set, pd in patched_pd.pds.items():
            new_entries = []
            for entry in entries:
                if frozenset(entry.composition.elements).issubset(ele_set):
                    new_entries.append(entry)

            pd_computed_data = pd.computed_data
            pd_computed_data["all_entries"] = new_entries
            new_pd = PhaseDiagram(new_entries, elements=pd.elements, computed_data=pd_computed_data)
            new_pds.append(new_pd)

        return docs, new_pds


class PhaseDiagramDoc(BaseModel):
    """
    A phase diagram document
    """

    property_name = "phase_diagram"

    phase_diagram_id: str = Field(
        ...,
        description="Phase diagram ID consisting of the chemical system and thermo type",
    )

    chemsys: str = Field(
        ...,
        description="Dash-delimited string of elements in the material",
    )

    thermo_type: Union[ThermoType, RunType] = Field(
        ...,
        description="Functional types of calculations involved in the energy mixing scheme.",
    )

    phase_diagram: PhaseDiagram = Field(
        ...,
        description="Phase diagram for the chemical system.",
    )

    last_updated: datetime = Field(
        description="Timestamp for the most recent calculation update for this property",
        default_factory=datetime.utcnow,
    )
