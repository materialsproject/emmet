""" Core definition of a Thermo Document """
from collections import defaultdict
from typing import ClassVar, Dict, List, Union

from pydantic import BaseModel, Field
from pymatgen.analysis.phase_diagram import PhaseDiagram
from pymatgen.entries.computed_entries import ComputedEntry, ComputedStructureEntry

from emmet.core.material_property import PropertyDoc
from emmet.core.mpid import MPID


class DecompositionProduct(BaseModel):
    """
    Entry metadata for a decomposition process
    """

    material_id: MPID = Field(
        None, description="The material this decomposition points to"
    )
    formula: str = Field(
        None,
        description="The formula of the decomposed material this material decomposes to",
    )
    amount: float = Field(
        None,
        description="The amount of the decomposed material by formula units this this material decomposes to",
    )


class ThermoDoc(PropertyDoc):
    """
    A thermo entry document
    """

    property_name: ClassVar[str] = Field(
        "thermo", description="The subfield name for this property"
    )

    uncorrected_energy_per_atom: float = Field(
        ..., description="The total DFT energy of this material per atom in eV/atom"
    )

    energy_per_atom: float = Field(
        ...,
        description="The total corrected DFT energy of this material per atom in eV/atom",
    )

    energy_uncertainy_per_atom: float = Field(None, description="")

    formation_energy_per_atom: float = Field(
        None, description="The formation energy per atom in eV/atom"
    )

    energy_above_hull: float = Field(
        ..., description="The energy above the hull in eV/Atom"
    )

    is_stable: bool = Field(
        False,
        description="Flag for whether this material is on the hull and therefore stable",
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

    energy_type: str = Field(
        ...,
        description="The type of calculation this energy evaluation comes from. TODO: Convert to enum?",
    )

    entry_types: List[str] = Field(
        description="List of available energy types computed for this material"
    )

    entries: Dict[str, Union[ComputedEntry, ComputedStructureEntry]] = Field(
        ...,
        description="List of all entries that are valid for this material."
        " The keys for this dictionary are names of various calculation types",
    )

    @classmethod
    def from_entries(cls, entries: List[Union[ComputedEntry, ComputedStructureEntry]]):

        entries_by_comp = defaultdict(list)
        for e in entries:
            entries_by_comp[e.composition.reduced_formula].append(e)

        # Only use lowest entry per composition to speed up QHull in Phase Diagram
        reduced_entries = [
            sorted(comp_entries, key=lambda e: e.energy_per_atom)[0]
            for comp_entries in entries_by_comp.values()
        ]

        pd = PhaseDiagram(reduced_entries)

        docs = []

        for e in entries:
            (decomp, ehull) = pd.get_decomp_and_e_above_hull(e)

            d = {
                "material_id": e.entry_id,
                "uncorrected_energy_per_atom": e.uncorrected_energy
                / e.composition.num_atoms,
                "energy_per_atom": e.uncorrected_energy / e.composition.num_atoms,
                "formation_energy_per_atom": pd.get_form_energy_per_atom(e),
                "energy_above_hull": ehull,
                "is_stable": e in pd.stable_entries,
            }

            if "last_updated" in e.data:
                d["last_updated"] = e.data["last_updated"]

            # Store different info if stable vs decomposes
            if d["is_stable"]:
                d[
                    "equilibrium_reaction_energy_per_atom"
                ] = pd.get_equilibrium_reaction_energy(e)
            else:
                d["decomposes_to"] = [
                    {
                        "material_id": de.entry_id,
                        "formula": de.composition.formula,
                        "amount": amt,
                    }
                    for de, amt in decomp.items()
                ]

            d["energy_type"] = e.parameters.get("run_type", "Unknown")
            d["entry_types"] = [e.parameters.get("run_type", "Unknown")]
            d["entries"] = {e.parameters.get("run_type", ""): e}

            for k in ["last_updated"]:
                if k in e.parameters:
                    d[k] = e.parameters[k]
                elif k in e.data:
                    d[k] = e.data[k]

            docs.append(ThermoDoc.from_structure(structure=e.structure, **d))

        return docs
