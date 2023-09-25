from typing import Dict, List, Optional, Type, TypeVar, Union
from hashlib import blake2b
from scipy.stats import describe

from pydantic import BaseModel, Field

from pymatgen.core.periodic_table import Species, Element

from emmet.core.mpid import MPculeID
from emmet.core.qchem.molecule import MoleculeDoc
from emmet.core.molecules.molecule_property import PropertyDoc
from emmet.core.molecules.atomic import PartialChargesDoc, PartialSpinsDoc
from emmet.core.molecules.bonds import MoleculeBondingDoc
from emmet.core.molecules.thermo import MoleculeThermoDoc


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"

METAL_BINDING_METHODS = ["nbo", "mulliken-OB-mee"]

T = TypeVar("T", bound="MetalBindingDoc")


class MetalBindingData(BaseModel):
    """
    Metal binding information for one metal or ion in a molecule
    """

    metal_molecule_id: MPculeID = Field(
        ..., description="The MPculeID of the metal atom or ion being bound"
    )

    nometal_molecule_id: MPculeID = Field(
        ..., description="The MPculeID of the molecule with the metal atom/ion removed"
    )

    metal_index: Optional[int] = Field(
        None,
        description="Index of the metal in this Molecule (in case of a molecule with multiple identical "
        "metal atoms/ions)",
    )

    metal_element: Optional[Union[str, Species, Element]] = Field(
        None, description="The metal bound to the molecule"
    )

    metal_partial_charge: Optional[float] = Field(
        None, description="The exact calculated partial charge of the metal"
    )

    metal_partial_spin: Optional[float] = Field(
        None, description="The exact calculated partial spin on the metal"
    )

    metal_assigned_charge: Optional[float] = Field(
        None,
        description="The integral charge assigned to this metal based on partial charge/spin data",
    )

    metal_assigned_spin: Optional[float] = Field(
        None,
        description="The integral spin multiplicity assigned to this metal based on partial spin data",
    )

    number_coordinate_bonds: Optional[int] = Field(
        None,
        description="The number of atoms neighboring the metal atom or ion of interest",
    )

    coordinating_atoms: Optional[List[Union[str, Species]]] = Field(
        None, description="The elements/species coordinating the metal."
    )

    coordinate_bond_lengths: Optional[
        Dict[str, Dict[str, Union[float, List[float]]]]
    ] = Field(
        None,
        description="Bond lengths and statistics broken down by the coordinating atoms",
    )

    binding_energy: Optional[float] = Field(
        None, description="The electronic energy change (∆E) of binding (units: eV)"
    )

    binding_enthalpy: Optional[float] = Field(
        None, description="The enthalpy change (∆H) of binding (units: eV)"
    )

    binding_entropy: Optional[float] = Field(
        None, description="The entropy change (∆S) of binding (units: eV/K)"
    )

    binding_free_energy: Optional[float] = Field(
        None, description="The free energy change (∆G) of binding (units: eV)"
    )

    metal_thermo_property_id: Optional[str] = Field(
        None,
        description="ID of MoleculeThermoDoc used to obtain the thermochemistry of the metal atom/ion",
    )

    nometal_thermo_property_id: Optional[str] = Field(
        None,
        description="ID of MoleculeThermoDoc used to obtain the thermochemistry of of the molecule with the "
        "metal atom/ion removed",
    )

    def get_id_string(self):
        """
        Return a string representation of the binding data for this atom in the molecule
        """
        id_str = f"{self.metal_element}-{self.metal_index}-"
        id_str += f"{self.metal_thermo_property_id}-{self.nometal_thermo_property_id}"
        return id_str


class MetalBindingDoc(PropertyDoc):
    """Metal binding properties of a molecule"""

    property_name: str = "metal_binding"

    method: str = Field(
        ...,
        description="Method used to determine the charge, spin, and coordination environment of a metal",
    )

    binding_partial_charges_property_id: Optional[str] = Field(
        None,
        description="ID of PartialChargesDoc used to estimate metal charge",
    )

    binding_partial_spins_property_id: Optional[str] = Field(
        None,
        description="ID of PartialSpinsDoc used to estimate metal spin",
    )

    binding_partial_charges_lot_solvent: Optional[str] = Field(
        None,
        description="Combination of level of theory and solvent used to calculate atomic partial charges",
    )

    binding_partial_spins_lot_solvent: Optional[str] = Field(
        None,
        description="Combination of level of theory and solvent used to calculate atomic partial spins",
    )

    binding_charge_spin_method: Optional[str] = Field(
        None,
        description="The method used for partial charges and spins (must be the same).",
    )

    binding_bonding_property_id: Optional[str] = Field(
        None,
        description="ID of MoleculeBondingDoc used to detect bonding in this molecule",
    )

    binding_bonding_lot_solvent: Optional[str] = Field(
        None,
        description="Combination of level of theory and solvent used to determine the coordination environment "
        "of the metal atom or ion",
    )

    binding_bonding_method: Optional[str] = Field(
        None, description="The method used for to define bonding."
    )

    binding_thermo_property_id: Optional[str] = Field(
        None,
        description="ID of MoleculeThermoDoc used to obtain this molecule's thermochemistry",
    )

    binding_thermo_lot_solvent: Optional[str] = Field(
        None,
        description="Combination of level of theory and solvent used for uncorrected thermochemistry",
    )

    binding_thermo_correction_lot_solvent: Optional[str] = Field(
        None,
        description="Combination of level of theory and solvent used to correct the electronic energy",
    )

    binding_thermo_combined_lot_solvent: Optional[str] = Field(
        None,
        descrption="Combination of level of theory and solvent used for molecular thermochemistry, combining "
        "both the frequency calculation and (potentially) the single-point energy correction.",
    )

    binding_data: Optional[List[MetalBindingData]] = Field(
        None, description="Binding data for each metal atom or ion in the molecule"
    )

    @classmethod
    def from_docs(
        cls: Type[T],
        method: str,
        metal_indices: List[int],
        base_molecule_doc: MoleculeDoc,
        partial_charges: PartialChargesDoc,
        partial_spins: Optional[PartialSpinsDoc],
        bonding: MoleculeBondingDoc,
        base_thermo: MoleculeThermoDoc,
        metal_thermo: Dict[int, MoleculeThermoDoc],
        nometal_thermo: Dict[int, MoleculeThermoDoc],
        **kwargs,
    ):  # type: ignore[override]
        """
        Construct a document describing the binding energy of a metal atom or ion to
            a molecule from MoleculeThermoDocs (for thermochemistry), PartialChargesDocs
            and PartialSpinsDocs (to assess the oxidation state and spin state of the metal),
            and MoleculeBondingDocs (to assess the coordination environment of the metal).

        :param method: What method was used to construct this document?
        :param metal_indices: List of indices in the Molecule corresponding to metals
        :param base_molecule_doc: MoleculeDoc used for basic ID, species, structure information
        :param partial_charges: PartialChargesDoc used to determine the oxidation state of the
            metal of interest
        :param partial_spins: PartialSpinsDoc used to determine the spin state of the metal of
            interest
        :param bonding: MoleculeBondingDoc used to determine the coordination environment
        :param base_thermo: MoleculeThermoDoc for the molecule of interest.
        :param metal_thermo: Dict[int, MoleculeThermoDoc], where the keys are the indices of the
            metal ions or atoms in this molecule and the values are the MoleculeThermoDocs corresponding
            to the appropriate metal (with the correct charge and spin)
        :param nometal_thermo: Dict[int, MoleculeThermoDoc], where the keys are the indices of the
            metal ions or atoms in this molecule and the values are the MoleculeThermoDocs corresponding
            to the appropriate metal (with the correct charge and spin)

        :param kwargs: To be passed to PropertyDoc
        :return:

        """

        # Sanity checks
        for i, doc in metal_thermo.items():
            if not doc.lot_solvent == base_thermo.lot_solvent:
                raise ValueError(
                    "All MoleculeThermoDocs must use the same lot_solvent!"
                )
        for i, doc in nometal_thermo.items():
            if not doc.lot_solvent == base_thermo.lot_solvent:
                raise ValueError(
                    "All MoleculeThermoDocs must use the same lot_solvent!"
                )

        if partial_spins is not None:
            if not (
                partial_charges.method == partial_spins.method
                and partial_charges.lot_solvent == partial_spins.lot_solvent
            ):
                raise ValueError(
                    "Partial charges and partial spins must use the same method and lot_solvent!"
                )

        if not (
            base_thermo.solvent == partial_charges.solvent
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

        thermo_lot_solvent = base_thermo.lot_solvent
        thermo_correction_lot_solvent = base_thermo.correction_lot_solvent
        thermo_combined_lot_solvent = base_thermo.combined_lot_solvent

        level_of_theory = base_thermo.level_of_theory
        solvent = base_thermo.solvent
        lot_solvent = base_thermo.lot_solvent

        molecule = base_molecule_doc.molecule
        dist_mat = molecule.distance_matrix
        species = base_molecule_doc.species

        binding_data = list()

        for metal_index in metal_indices:
            metal_element = species[metal_index]

            this_metal_thermo = metal_thermo.get(metal_index)
            this_nometal_thermo = nometal_thermo.get(metal_index)

            if this_metal_thermo is None or this_nometal_thermo is None:
                continue

            # Partial charges and spins
            charge = partial_charges.partial_charges[metal_index]

            if partial_spins is not None:
                spin = partial_spins.partial_spins[metal_index]
            else:
                spin = None

            # Coordinate bonding
            relevant_bonds = [b for b in bonding.bonds if metal_index in b]
            number_coordinate_bonds = len(relevant_bonds)
            # Binding is not meaningful if there are no coordinate bonds
            if number_coordinate_bonds == 0:
                return None

            coordinating_atoms = list()
            coordinate_bond_lengths = dict()  # type: ignore
            for bond in relevant_bonds:
                other_ids = [i for i in bond if i != metal_index]
                # Edge case - possible if we (later) account for 3-center bonds or hyperbonds
                if len(other_ids) != 1:
                    continue
                other_index = other_ids[0]

                other_species = str(species[other_index])
                coordinating_atoms.append(other_species)
                if other_species not in coordinate_bond_lengths:
                    coordinate_bond_lengths[other_species] = {
                        "lengths": list(),
                    }
                this_length = dist_mat[metal_index][other_index]
                coordinate_bond_lengths[other_species]["lengths"].append(this_length)

            for s, data in coordinate_bond_lengths.items():
                stats = describe(data["lengths"], nan_policy="omit")
                coordinate_bond_lengths[s]["min"] = stats.minmax[0]
                coordinate_bond_lengths[s]["max"] = stats.minmax[1]
                coordinate_bond_lengths[s]["mean"] = stats.mean
                coordinate_bond_lengths[s]["variance"] = stats.variance

            coordinating_atoms = sorted(coordinating_atoms)

            # Thermo
            binding_e = None
            binding_h = None
            binding_s = None
            binding_g = None

            if this_metal_thermo is not None and this_nometal_thermo is not None:
                thermos = [base_thermo, this_metal_thermo, this_nometal_thermo]

                binding_e = (
                    thermos[1].electronic_energy + thermos[2].electronic_energy
                ) - thermos[0].electronic_energy

                if all([x.total_enthalpy is not None for x in thermos]):
                    binding_h = (
                        thermos[1].total_enthalpy + thermos[2].total_enthalpy
                    ) - thermos[0].total_enthalpy

                if all([x.total_entropy is not None for x in thermos]):
                    binding_s = (
                        thermos[1].total_entropy + thermos[2].total_entropy
                    ) - thermos[0].total_entropy

                if all([x.free_energy is not None for x in thermos]):
                    binding_g = (
                        thermos[1].free_energy + thermos[2].free_energy
                    ) - thermos[0].free_energy

            binding_data.append(
                MetalBindingData(
                    metal_molecule_id=this_metal_thermo.molecule_id,
                    nometal_molecule_id=this_nometal_thermo.molecule_id,
                    metal_index=metal_index,
                    metal_element=metal_element,
                    metal_partial_charge=charge,
                    metal_partial_spin=spin,
                    metal_assigned_charge=this_metal_thermo.charge,
                    metal_assigned_spin=this_metal_thermo.spin_multiplicity,
                    number_coordinate_bonds=number_coordinate_bonds,
                    coordinating_atoms=coordinating_atoms,
                    coordinate_bond_lengths=coordinate_bond_lengths,
                    binding_energy=binding_e,
                    binding_enthalpy=binding_h,
                    binding_entropy=binding_s,
                    binding_free_energy=binding_g,
                    metal_thermo_property_id=this_metal_thermo.property_id,
                    nometal_thermo_property_id=this_nometal_thermo.property_id,
                )
            )

        # Property ID
        id_string = f"binding-{base_molecule_doc.molecule_id}-{lot_solvent}-"
        id_string += f"{partial_charges_property_id}-{partial_spins_property_id}-"
        id_string += f"{bonding.property_id}-"
        id_string += f"{thermo_property_id}"
        for d in binding_data:
            id_string += f"-{d.get_id_string()}"
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
            method=method,
            binding_partial_charges_property_id=partial_charges_property_id,
            binding_partial_spins_property_id=partial_spins_property_id,
            binding_partial_charges_lot_solvent=partial_charges_lot_solvent,
            binding_partial_spins_lot_solvent=partial_spins_lot_solvent,
            binding_charge_spin_method=partial_charges.method,
            binding_bonding_property_id=bonding_property_id,
            binding_bonding_lot_solvent=bonding_lot_solvent,
            binding_bonding_method=bonding.method,
            binding_thermo_property_id=thermo_property_id,
            binding_thermo_lot_solvent=thermo_lot_solvent,
            binding_thermo_correction_lot_solvent=thermo_correction_lot_solvent,
            binding_thermo_combined_lot_solvent=thermo_combined_lot_solvent,
            binding_data=binding_data,
            deprecated=False,
            origins=[],
            **kwargs,
        )
