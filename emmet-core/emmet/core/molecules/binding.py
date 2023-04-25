from typing import Dict, List, Optional, Type, TypeVar
from hashlib import blake2b
from scipy.stats import describe

from pydantic import Field

from pymatgen.core.periodic_table import Species, Element

from emmet.core.mpid import MPculeID
from emmet.core.qchem.molecule import MoleculeDoc
from emmet.core.molecules.molecule_property import PropertyDoc
from emmet.core.molecules.atomic import (
    PartialChargesDoc,
    PartialSpinsDoc
)
from emmet.core.molecules.bonds import MoleculeBondingDoc
from emmet.core.molecules.thermo import MoleculeThermoDoc


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"

T = TypeVar("T", bound="BindingDoc")


class BindingDoc(PropertyDoc):
    """Metal binding properties of a molecule"""

    property_name = "binding"

    metal_molecule_id: MPculeID = Field(
        ..., description="The MPculeID of the metal atom or ion being bound"
    )

    nometal_molecule_id: MPculeID = Field(
        ..., description="The MPculeID of the molecule with the metal atom/ion removed"
    )

    metal_index: int = Field(
        None, description="Index of the metal in this Molecule (in case of a molecule with multiple identical "
                          "metal atoms/ions)"
    )

    metal_element: str | Species | Element = Field(
        None, description="The metal bound to the molecule"
    )

    metal_partial_charge: float = Field(
        None, description="The exact calculated partial charge of the metal"
    )

    metal_partial_spin: float = Field(
        None, description="The exact calculated partial spin on the metal"
    )

    partial_charges_property_id: str = Field(
        None, description="ID of PartialChargesDoc used to estimate metal charge",
    )

    partial_spins_property_id: str = Field(
        None, description="ID of PartialSpinsDoc used to estimate metal spin",
    )

    partial_charges_lot_solvent: str = Field(
        None, description="Combination of level of theory and solvent used to calculate atomic partial charges"
    )

    partial_spins_lot_solvent: str = Field(
        None, description="Combination of level of theory and solvent used to calculate atomic partial spins"
    )

    charge_spin_method: str = Field(
        None, description="The method used for partial charges and spins (must be the same)."
    )

    number_coordinate_bonds: int = Field(
        None, description="The number of atoms neighboring the metal atom or ion of interest"
    )

    coordinating_atoms: List[str | Species] = Field(
        None, description="The elements/species coordinating the metal."
    )

    coordinate_bond_lengths: Dict[str, Dict[str, float]] = Field(
        None, description="Bond lengths and statistics broken down by the coordinating atoms"
    )

    bonding_property_id: str = Field(
        None, description="ID of MoleculeBondingDoc used to detect bonding in this "
    )

    bonding_lot_solvent: str = Field(
        None, description="Combination of level of theory and solvent used to determine the coordination environment "
                          "of the metal atom or ion"
    )

    bonding_method: str = Field(
        None, description="The method used for to define bonding."
    )

    binding_energy: float = Field(
        None, description="The electronic energy change (∆E) of binding (units: eV)"
    )

    binding_enthalpy: float = Field(
        None, description="The enthalpy change (∆H) of binding (units: eV)"
    )

    binding_entropy: float = Field(
        None, description="The entropy change (∆S) of binding (units: eV/K)"
    )

    binding_free_energy: float = Field(
        None, description="The free energy change (∆G) of binding (units: eV)"
    )

    thermo_property_id: str = Field(
        None, description="ID of MoleculeThermoDoc used to obtain this molecule's thermochemistry"
    )

    metal_thermo_property_id: str = Field(
        None, description="ID of MoleculeThermoDoc used to obtain the thermochemistry of the metal atom/ion"
    )

    nometal_thermo_property_id: str = Field(
        None, description="ID of MoleculeThermoDoc used to obtain the thermochemistry of of the molecule with the "
                          "metal atom/ion removed"
    )

    thermo_lot_solvent: str = Field(
        None, description="Combination of level of theory and solvent used for uncorrected thermochemistry"
    )

    thermo_correction_lot_solvent: str = Field(
        None, description="Combination of level of theory and solvent used to correct the electronic energy"
    )

    thermo_combined_lot_solvent: str = Field(
        None, descrption="Combination of level of theory and solvent used for molecular thermochemistry, combining "
                         "both the frequency calculation and (potentially) the single-point energy correction."
    )

    @classmethod
    def from_docs(
        cls: Type[T],
        metal_index: int,
        base_molecule_doc: MoleculeDoc,
        partial_charges: PartialChargesDoc,
        partial_spins: Optional[PartialSpinsDoc],
        bonding: MoleculeBondingDoc,
        base_thermo: MoleculeThermoDoc,
        metal_thermo: MoleculeThermoDoc,
        nometal_thermo: MoleculeThermoDoc
    ):  # type: ignore[override]
        """
        Construct a document describing the binding energy of a metal atom or ion to
            a molecule from MoleculeThermoDocs (for thermochemistry), PartialChargesDocs
            and PartialSpinsDocs (to assess the oxidation state and spin state of the metal),
            and MoleculeBondingDocs (to assess the coordination environment of the metal).

        :param metal_index: index of the metal of interest (in case there are multiple metals
            in the molecule)
        :param partial_charges: PartialChargesDoc used to determine the oxidation state of the
            metal of interest
        :param partial_spins: PartialSpinsDoc used to determine the spin state of the metal of
            interest
        :param bonding: MoleculeBondingDoc used to determine the coordination environment
        :param base_thermo: MoleculeThermoDoc for the molecule of interest.
        :param metal_thermo: MoleculeThermoDoc for the metal atom or ion.
        :param nometal_thermo: MoleculeThermoDoc for the molecule with the metal atom or ion
            removed.

        :param kwargs: To be passed to PropertyDoc
        :return:

        """

        # Sanity checks
        if not (
            base_thermo.lot_solvent == metal_thermo.lot_solvent
            and base_thermo.lot_solvent == nometal_thermo.lot_solvent
        ):
            raise ValueError("All MoleculeThermoDocs must use the same lot_solvent!")

        if partial_charges is not None:
            if not (
                partial_charge.method == partial_spins.method
                and partial_charge.lot_solvent == partial_spins.lot_solvent
            ):
                raise ValueError("Partial charges and partial spins must use the same method and lot_solvent!")

        if not (
            base_thermo.solvent == partial_charge.solvent
            and base_thermo.solvent == bonding.solvent
        ):
            raise ValueError("All documents must use the same solvent!")

        partial_charges_property_id = partial_charges.property_id
        partial_charges_lot_solvent = partial_charges.lot_solvent

        if partial_spins is not None:
            partial_spins_property_id = partial_spins.property_id
            partial_spins_lot_solvent = partial_spins.lot_solvent
        else:
            partial_spins_property_id = None
            partial_spins_lot_solvent = None

        bonding_property_id = bonding.property_id
        bonding_lot_solvent = bonding.lot_solvent

        thermo_property_id = base_thermo.property_id
        metal_thermo_property_id = metal_thermo.property_id
        nometal_thermo_property_id = nometal_thermo.property_id

        thermo_lot_solvent = base_thermo.lot_solvent
        thermo_correction_lot_solvent = base_thermo.correction_lot_solvent
        thermo_combined_lot_solvent = base_thermo.combined_lot_solvent

        level_of_theory = base_thermo.level_of_theory
        solvent = base_thermo.solvent
        lot_solvent = base_thermo.lot_solvent

        molecule = base_molecule_doc.molecule
        dist_mat = molecule.distance_matrix
        species = str(molecule.species)
        metal_element = species[metal_index]

        # Partial charges and spins
        charge = partial_charges.partial_charges[metal_index]

        if partial_spins is not None:
            spin = partial_spins.partial_spins[metal_index]
        else:
            spin = None

        # Coordinate bonding
        relevant_bonds = [b for b in bonding.bonds if metal_index in b]
        number_coordinating_bonds = len(relevant_bonds)
        # Binding is not meaningful if there are no coordinate bonds
        if len(number_coordinating_bonds) == 0:
            return None

        coordinating_atoms = list()
        coordinating_bond_lengths = dict()
        for bond in relevant_bonds:
            other_ids = [i for i in bond if i != metal_index]
            # Edge case - possible if we (later) account for 3-center bonds or hyperbonds
            if len(other_ids) != 1:
                continue 
            other_index = other_ids[0]

            other_species = str(species[other_index])
            coordinating_atoms.append(other_species)
            if other_species not in coordinating_bond_lengths:
                coordinating_bond_lengths[other_species] = {
                    "lengths": list(),
                }
            this_length = dist_mat[metal_index][other_index]
            coordinate_bond_lengths[other_species]["lengths"].append(this_length)

        for species, data in coordinate_bond_lengths.items():
            stats = describe(data["lengths"], nan_policy="omit")
            coordinate_bond_lengths[species]["min"] = stats.minmax[0]
            coordinate_bond_lengths[species]["max"] = stats.minmax[1]
            coordinate_bond_lengths[species]["mean"] = stats.mean
            coordinate_bond_lengths[species]["variance"] = stats.variance

        coordinating_atoms = sorted(coordinating_atoms)

        # Thermo
        thermos = [base_thermo, metal_thermo, nometal_thermo]

        binding_energy = thermos[0].electronic_energy - (thermos[1].electronic_energy + thermos[2].electronic_energy)

        if all([x.total_enthalpy is not None for x in thermos]):
            binding_enthalpy = thermos[0].total_enthalpy - (thermos[1].total_enthalpy + thermos[2].total_enthalpy)
        else:
            binding_enthalpy = None

        if all([x.total_entropy is not None for x in thermos]):
            binding_entropy = thermos[0].total_entropy - (thermos[1].total_entropy + thermos[2].total_entropy)
        else:
            binding_entropy = None

        if all([x.free_energy is not None for x in thermos]):
            binding_free_energy = thermos[0].free_energy - (thermos[1].free_energy + thermos[2].free_energy)
        else:
            binding_free_energy = None

        # Property ID
        id_string = f"binding-{base_molecule_doc.molecule_id}-{lot_solvent}-"
        id_string += f"{thermo_property_id}-{metal_thermo_property_id}-{nometal_thermo_property_id}-"
        id_string += f"{partial_charges_property_id}-{partial_spins_property_id}-"
        id_string += f"{bonding.property_id}"
        h = blake2b()
        h.update(id_string.encode("utf-8"))
        property_id = h.hexdigest()

        return super().from_molecule(
            meta_molecule=base_molecule_doc.molecule,
            property_id=property_id,
            molecule_id=base_molecule_doc.molecule_id,
            level_of_theory=level_of_theory,
            solvent=solvent,
            lot_solvent=lot_solvent,
            metal_molecule_id=metal_thermo.molecule_id,
            nometal_molecule_id=nometal_thermo.molecule_id,
            metal_index=index,
            metal_element=metal_element,
            metal_partial_charge=charge,
            metal_partial_spin=spin,
            partial_charges_property_id=partial_charges_property_id,
            partial_spins_property_id=partial_spins_property_id,
            partial_charges_lot_solvent=partial_charges_lot_solvent,
            partial_spins_lot_solvent=partial_spins_lot_solvent,
            charge_spin_method=partial_charges.method,
            number_coordinate_bonds=number_coordinate_bonds,
            coordinating_atoms=coordinating_atoms,
            coordinate_bond_lengths=coordinate_bond_lengths,
            bonding_property_id=bonding_property_id,
            bonding_lot_solvent=bonding_lot_solvent,
            bonding_method=bonding.method,
            thermo_property_id=thermo_property_id,
            metal_thermo_property_id=metal_thermo_property_id,
            nometal_thermo_property_id=nometal_thermo_property_id,
            binding_energy=binding_energy,
            binding_enthalpy=binding_enthalpy,
            binding_entropy=binding_entropy,
            binding_free_energy=binding_free_energy,
            thermo_lot_solvent=thermo_lot_solvent,
            thermo_correction_lot_solvent=thermo_correction_lot_solvent,
            thermo_combined_lot_solvent=thermo_combined_lot_solvent,
            deprecated=deprecated,
            origins=[],
            **kwargs
        )
