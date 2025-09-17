from __future__ import annotations

from hashlib import blake2b
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from emmet.core.molecules.metal_binding import MetalBindingData
from emmet.core.molecules.molecule_property import PropertyDoc
from emmet.core.mpid import MPID, MPculeID
from emmet.core.qchem.calc_types import CalcType, LevelOfTheory, TaskType
from emmet.core.types.enums import ValueEnum
from emmet.core.types.pymatgen_types.structure_adapter import MoleculeType
from emmet.core.utils import arrow_incompatible

if TYPE_CHECKING:
    from typing import Any

    from typing_extensions import Self

__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


class HasProps(ValueEnum):
    """
    Enum of possible hasprops values.
    """

    molecules = "molecules"
    bonding = "bonding"
    metal_binding = "metal_binding"
    multipole_moments = "multipole_moments"
    orbitals = "orbitals"
    partial_charges = "partial_charges"
    partial_spins = "partial_spins"
    redox = "redox"
    thermo = "thermo"
    vibration = "vibration"


class ThermoComposite(BaseModel):
    """
    Summary information obtained from MoleculeThermoDocs
    """

    property_id: str | None = Field(
        None,
        description="Property ID map for this MoleculeThermoDoc",
    )

    level_of_theory: str | None = Field(
        None,
        description="Level of theory for this MoleculeThermoDoc.",
    )

    electronic_energy: float | None = Field(
        None, description="Electronic energy of the molecule (units: eV)"
    )

    zero_point_energy: float | None = Field(
        None, description="Zero-point energy of the molecule (units: eV)"
    )

    total_enthalpy: float | None = Field(
        None, description="Total enthalpy of the molecule at 298.15K (units: eV)"
    )
    total_entropy: float | None = Field(
        None, description="Total entropy of the molecule at 298.15K (units: eV/K)"
    )

    free_energy: float | None = Field(
        None, description="Gibbs free energy of the molecule at 298.15K (units: eV)"
    )


class VibrationComposite(BaseModel):
    """
    Summary information obtained from VibrationDocs
    """

    property_id: str | None = Field(
        None,
        description="Property ID for this VibrationDoc.",
    )

    level_of_theory: str | None = Field(
        None,
        description="Level of theory for this VibrationDoc.",
    )

    frequencies: list[float] | None = Field(
        None, description="List of molecular vibrational frequencies"
    )


class OrbitalComposite(BaseModel):
    """
    Summary information obtained from OrbitalDocs
    """

    property_id: str | None = Field(
        None,
        description="Property ID for this OrbitalDoc.",
    )

    level_of_theory: str | None = Field(
        None,
        description="Level of theory for this OrbitalDoc.",
    )

    open_shell: bool | None = Field(
        None, description="Is this molecule open-shell (spin multiplicity != 1)?"
    )


class PartialChargesComposite(BaseModel):
    """
    Summary information obtained from PartialChargesDocs
    """

    property_id: str | None = Field(
        None,
        description="Property ID for this PartialChargesDoc.",
    )

    level_of_theory: str | None = Field(
        None,
        description="Level of theory for this PartialChargesDoc.",
    )

    partial_charges: list[float] | None = Field(
        None,
        description="Atomic partial charges for the molecule",
    )


class PartialSpinsComposite(BaseModel):
    """
    Summary information obtained from PartialSpinsDocs
    """

    property_id: str | None = Field(
        None,
        description="Property ID for this PartialSpinsDoc.",
    )

    level_of_theory: str | None = Field(
        None,
        description="Level of theory for this PartialSpinsDoc.",
    )

    partial_spins: list[float] | None = Field(
        None,
        description="Atomic partial spins for the molecule",
    )


class BondingComposite(BaseModel):
    """
    Summary information obtained from MoleculeBondingDocs
    """

    property_id: str | None = Field(
        None,
        description="Property ID for this MoleculeBondingDoc.",
    )

    level_of_theory: str | None = Field(
        None,
        description="Level of theory for this MoleculeBondingDoc.",
    )

    bond_types: dict[str, list[float]] | None = Field(
        None,
        description="Dictionaries of bond types to their length, e.g. C-O to a list of the lengths of C-O bonds in "
        "Angstrom.",
    )

    bonds: list[tuple[int, int]] | None = Field(
        None,
        description="List of bonds. Each bond takes the form (a, b), where a and b are 0-indexed atom indices",
    )

    bonds_nometal: list[tuple[int, int]] | None = Field(
        None,
        description="List of bonds with all metal ions removed. Each bond takes the form in the form (a, b), where a "
        "and b are 0-indexed atom indices.",
    )


class MultipolesComposite(BaseModel):
    """
    Summary information obtained from ElectricMultipoleDocs
    """

    property_id: str | None = Field(
        None,
        description="Property ID for this ElectricMultipoleDoc.",
    )

    level_of_theory: str | None = Field(
        None,
        description="Level of theory for this ElectricMultipoleDoc.",
    )

    total_dipole: float | None = Field(
        None,
        description="Total molecular dipole moment (Debye)",
    )

    resp_total_dipole: float | None = Field(
        None,
        description="Total dipole moment, calculated via restrained electrostatic potential (RESP) (Debye)",
    )


class RedoxComposite(BaseModel):
    """
    Summary information obtained from RedoxDocs
    """

    property_id: str | None = Field(None, description="Property ID for this RedoxDoc.")

    level_of_theory: str | None = Field(
        None,
        description="Level of theory for this RedoxDoc.",
    )

    electron_affinity: float | None = Field(
        None, description="Vertical electron affinity in eV"
    )

    ea_task_id: MPID | None = Field(
        None, description="Molecule ID for electron affinity"
    )

    ionization_energy: float | None = Field(
        None, description="Vertical ionization energy in eV"
    )

    ie_task_id: MPID | None = Field(
        None, description="Molecule ID for ionization energy"
    )

    reduction_free_energy: float | None = Field(
        None, description="Adiabatic free energy of reduction"
    )

    red_molecule_id: MPculeID | None = Field(
        None, description="Molecule ID for adiabatic reduction"
    )

    oxidation_free_energy: float | None = Field(
        None, description="Adiabatic free energy of oxidation"
    )

    ox_molecule_id: MPculeID | None = Field(
        None, description="Molecule ID for adiabatic oxidation"
    )

    reduction_potential: float | None = Field(
        None,
        description="Reduction potential referenced to the standard hydrogen electrode (SHE) (units: V)",
    )

    oxidation_potential: float | None = Field(
        None,
        description="Oxidation potential referenced to the standard hydrogen electrode (SHE) (units: V)",
    )


@arrow_incompatible
class MetalBindingComposite(BaseModel):
    """
    Summary information obtained from MetalBindingDocs
    """

    property_id: str | None = Field(
        None, description="Property ID for this MetalBindingDoc."
    )

    level_of_theory: str | None = Field(
        None,
        description="Level of theory for this MetalBindingDoc.",
    )

    binding_partial_charges_property_id: str | None = Field(
        None,
        description="ID of PartialChargesDoc used to estimate metal charge",
    )

    binding_partial_spins_property_id: str | None = Field(
        None,
        description="ID of PartialSpinsDoc used to estimate metal spin",
    )

    binding_partial_charges_lot_solvent: str | None = Field(
        None,
        description="Combination of level of theory and solvent used to calculate atomic partial charges",
    )

    binding_partial_spins_lot_solvent: str | None = Field(
        None,
        description="Combination of level of theory and solvent used to calculate atomic partial spins",
    )

    binding_charge_spin_method: str | None = Field(
        None,
        description="The method used for partial charges and spins (must be the same).",
    )

    binding_bonding_property_id: str | None = Field(
        None,
        description="ID of MoleculeBondingDoc used to detect bonding in this molecule",
    )

    binding_bonding_lot_solvent: str | None = Field(
        None,
        description="Combination of level of theory and solvent used to determine the coordination environment "
        "of the metal atom or ion",
    )

    binding_bonding_method: str | None = Field(
        None, description="The method used for to define bonding."
    )

    binding_thermo_property_id: str | None = Field(
        None,
        description="ID of MoleculeThermoDoc used to obtain this molecule's thermochemistry",
    )

    binding_thermo_lot_solvent: str | None = Field(
        None,
        description="Combination of level of theory and solvent used for uncorrected thermochemistry",
    )

    binding_thermo_correction_lot_solvent: str | None = Field(
        None,
        description="Combination of level of theory and solvent used to correct the electronic energy",
    )

    binding_thermo_combined_lot_solvent: str | None = Field(
        None,
        description="Combination of level of theory and solvent used for molecular thermochemistry, combining "
        "both the frequency calculation and (potentially) the single-point energy correction.",
    )

    binding_data: list[MetalBindingData] | None = Field(
        None, description="Binding data for each metal atom or ion in the molecule"
    )


@arrow_incompatible
class MoleculeSummaryDoc(PropertyDoc):
    """
    Summary information about molecules and their properties, useful for searching.
    """

    property_name: str = "summary"

    # molecules
    molecules: dict[str, MoleculeType] = Field(
        ...,
        description="The lowest energy optimized structures for this molecule for each solvent.",
    )

    molecule_levels_of_theory: dict[str, str] | None = Field(
        None,
        description="Level of theory used to optimize the best molecular structure for each solvent.",
    )

    species_hash: str | None = Field(
        None,
        description="Weisfeiler Lehman (WL) graph hash using the atom species as the graph "
        "node attribute.",
    )
    coord_hash: str | None = Field(
        None,
        description="Weisfeiler Lehman (WL) graph hash using the atom coordinates as the graph "
        "node attribute.",
    )

    inchi: str | None = Field(
        None, description="International Chemical Identifier (InChI) for this molecule"
    )
    inchi_key: str | None = Field(
        None, description="Standardized hash of the InChI for this molecule"
    )

    task_ids: list[MPID] = Field(
        [],
        title="Calculation IDs",
        description="List of Calculation IDs associated with this molecule.",
    )

    similar_molecules: list[MPculeID] = Field(
        [], description="IDs associated with similar molecules"
    )

    constituent_molecules: list[MPculeID] = Field(
        [],
        description="IDs of associated MoleculeDocs used to construct this molecule.",
    )

    unique_calc_types: list[CalcType] | None = Field(
        None,
        description="Collection of all unique calculation types used for this molecule",
    )

    unique_task_types: list[TaskType] | None = Field(
        None,
        description="Collection of all unique task types used for this molecule",
    )

    unique_levels_of_theory: list[LevelOfTheory] | None = Field(
        None,
        description="Collection of all unique levels of theory used for this molecule",
    )

    unique_solvents: list[str] | None = Field(
        None,
        description="Collection of all unique solvents (solvent parameters) used for this molecule",
    )

    unique_lot_solvents: list[str] | None = Field(
        None,
        description="Collection of all unique combinations of level of theory and solvent used for this molecule",
    )

    # Properties

    thermo: dict[str, ThermoComposite] | None = Field(
        None,
        description="A summary of thermodynamic data available for this molecule, organized by solvent",
    )

    vibration: dict[str, VibrationComposite] | None = Field(
        None,
        description="A summary of the vibrational data available for this molecule, organized by solvent",
    )

    orbitals: dict[str, OrbitalComposite] | None = Field(
        None,
        description="A summary of the orbital (NBO) data available for this molecule, organized by solvent",
    )

    partial_charges: dict[str, dict[str, PartialChargesComposite]] | None = Field(
        None,
        description="A summary of the partial charge data available for this molecule, organized by solvent and by "
        "method",
    )

    partial_spins: dict[str, dict[str, PartialSpinsComposite]] | None = Field(
        None,
        description="A summary of the partial spin data available for this molecule, organized by solvent and by "
        "method",
    )

    bonding: dict[str, dict[str, BondingComposite]] | None = Field(
        None,
        description="A summary of the bonding data available for this molecule, organized by solvent and by method",
    )

    multipole_moments: dict[str, MultipolesComposite] | None = Field(
        None,
        description="A summary of the electric multipole data available for this molecule, organized by solvent",
    )

    redox: dict[str, RedoxComposite] | None = Field(
        None,
        description="A summary of the redox data available for this molecule, organized by solvent",
    )

    metal_binding: dict[str, dict[str, MetalBindingComposite]] | None = Field(
        None,
        description="A summary of the metal binding data available for this molecule, organized by solvent and by "
        "method",
    )

    # has props
    has_props: dict[str, bool] | None = Field(
        None,
        description="Properties available for this molecule",
    )

    @classmethod
    def from_docs(cls, molecule_id: MPculeID, docs: dict[str, Any]) -> Self:
        """Converts a bunch of property docs into a SummaryDoc"""

        doc = _copy_from_docs(**docs)

        if len(doc["has_props"]) == 0:
            raise ValueError("Missing minimal properties!")

        id_string = f"summary-{molecule_id}"
        h = blake2b()
        h.update(id_string.encode("utf-8"))
        property_id = h.hexdigest()
        doc["property_id"] = property_id

        return MoleculeSummaryDoc(molecule_id=molecule_id, **doc)


# Key mapping
summary_fields: dict[str, list] = {
    HasProps(k).value: v
    for k, v in {
        "molecules": [
            "charge",
            "spin_multiplicity",
            "natoms",
            "elements",
            "nelements",
            "composition",
            "composition_reduced",
            "formula_alphabetical",
            "chemsys",
            "symmetry",
            "molecules",
            "deprecated",
            "task_ids",
            "species_hash",
            "coord_hash",
            "inchi",
            "inchi_key",
            "unique_calc_types",
            "unique_task_types",
            "unique_levels_of_theory",
            "unique_solvents",
            "unique_lot_solvents",
            "similar_molecules",
            "constituent_molecules",
            "molecule_levels_of_theory",
        ],
        "thermo": [
            "electronic_energy",
            "zero_point_energy",
            "total_enthalpy",
            "total_entropy",
            "free_energy",
        ],
        "vibration": [
            "frequencies",
        ],
        "orbitals": [
            "open_shell",
        ],
        "partial_charges": ["partial_charges"],
        "partial_spins": ["partial_spins"],
        "bonding": ["bond_types", "bonds", "bonds_nometal"],
        "multipole_moments": [
            "total_dipole",
            "resp_total_dipole",
        ],
        "redox": [
            "electron_affinity",
            "ea_task_id",
            "ionization_energy",
            "ie_task_id",
            "reduction_free_energy",
            "red_molecule_id",
            "oxidation_free_energy",
            "ox_molecule_id",
            "reduction_potential",
            "oxidation_potential",
        ],
        "metal_binding": [
            "binding_partial_charges_property_id",
            "binding_partial_spins_property_id",
            "binding_partial_charges_lot_solvent",
            "binding_partial_spins_lot_solvent",
            "binding_charge_spin_method",
            "binding_bonding_property_id",
            "binding_bonding_lot_solvent",
            "binding_bonding_method",
            "binding_thermo_property_id",
            "binding_thermo_lot_solvent",
            "binding_thermo_correction_lot_solvent",
            "binding_thermo_combined_lot_solvent",
            "binding_data",
        ],
    }.items()
}


def _copy_from_docs(
    molecules: dict[str, Any],
    partial_charges: dict[str, dict[str, dict[str, Any]]] | None = None,
    partial_spins: dict[str, dict[str, dict[str, Any]]] | None = None,
    bonding: dict[str, dict[str, dict[str, Any]]] | None = None,
    metal_binding: dict[str, dict[str, dict[str, Any]]] | None = None,
    multipole_moments: dict[str, dict[str, Any]] | None = None,
    orbitals: dict[str, dict[str, Any]] | None = None,
    redox: dict[str, dict[str, Any]] | None = None,
    thermo: dict[str, dict[str, Any]] | None = None,
    vibration: dict[str, dict[str, Any]] | None = None,
):
    """Helper function to cut down documents to composite models and then combine to create a MoleculeSummaryDoc"""

    has_props: dict[str, bool] = {str(val.value): False for val in HasProps}  # type: ignore[attr-defined]
    d: dict[str, Any] = {"has_props": has_props, "origins": []}

    # Molecules is special because there should only ever be one
    # MoleculeDoc for a given molecule
    # There are not multiple MoleculeDocs for different solvents

    # NB: mypy misfires on enums. Using the following syntax works fine with mypy,
    # but HasProps.molecules.value can raise errors about attributes being defined
    d["has_props"][HasProps("molecules").value] = True
    for copy_key in summary_fields[HasProps("molecules").value]:
        d[copy_key] = molecules[copy_key]

    doc_type_mapping = {
        HasProps(k).value: v
        for k, v in {
            "partial_charges": (partial_charges, PartialChargesComposite),
            "partial_spins": (partial_spins, PartialSpinsComposite),
            "bonding": (bonding, BondingComposite),
            "metal_binding": (metal_binding, MetalBindingComposite),
            "multipole_moments": (multipole_moments, MultipolesComposite),
            "orbitals": (orbitals, OrbitalComposite),
            "redox": (redox, RedoxComposite),
            "thermo": (thermo, ThermoComposite),
            "vibration": (vibration, VibrationComposite),
        }.items()
    }

    by_method = {
        HasProps(k).value
        for k in {
            "partial_charges",
            "partial_spins",
            "bonding",
            "metal_binding",
        }
    }

    # Function to grab the keys and put them in the root doc
    for doc_key in summary_fields:
        sub_docs, target_type = doc_type_mapping.get(doc_key, (None, None))

        # No information for this particular set of properties
        # Shouldn't happen, but can
        if sub_docs is None or target_type is None:
            composite_docs = None
        else:
            composite_docs = dict()  # type: ignore[var-annotated]

            if isinstance(sub_docs, dict) and len(sub_docs) > 0:
                d["has_props"][doc_key] = True

                if doc_key in by_method:
                    for solvent, solv_entries in sub_docs.items():
                        composite_docs[solvent] = dict()
                        for method, entry in solv_entries.items():
                            composite_docs[solvent][method] = dict()
                            for copy_key in summary_fields[doc_key]:
                                composite_docs[solvent][method][copy_key] = entry.get(
                                    copy_key
                                )

                            composite_docs[solvent][method]["property_id"] = entry.get(
                                "property_id"
                            )
                            composite_docs[solvent][method]["level_of_theory"] = (
                                entry.get("level_of_theory")
                            )

                            # Convert to appropriate BaseModel
                            composite_docs[solvent][method] = target_type(
                                **composite_docs[solvent][method]
                            )

                else:
                    for solvent, entry in sub_docs.items():
                        composite_docs[solvent] = dict()
                        for copy_key in summary_fields[doc_key]:
                            composite_docs[solvent][copy_key] = entry.get(copy_key)

                        composite_docs[solvent]["property_id"] = entry.get(
                            "property_id"
                        )
                        composite_docs[solvent]["level_of_theory"] = entry.get(
                            "level_of_theory"
                        )

                        # Convert to appropriate BaseModel
                        composite_docs[solvent] = target_type(**composite_docs[solvent])

            d[doc_key] = composite_docs

    return d
