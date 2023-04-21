from typing import Any, Dict, List, Optional, Type, TypeVar
from hashlib import blake2b

from pydantic import Field

from pymatgen.core.periodic_table import Species, Element

from emmet.core.mpid import MPculeID
from emmet.core.qchem.task import TaskDocument
from emmet.core.qchem.molecule import MoleculeDoc
from emmet.core.material import PropertyOrigin
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
        partial_spins: PartialSpinsDoc,
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

        base_has_g = base_thermo.free_energy is not None

        partial_charges_property_id = partial_charges.property_id
        partial_charges_lot_solvent = partial_charges.lot_solvent

        partial_spins_property_id = partial_spins.property_id
        partial_spins_lot_solvent = partial_spins.lot_solvent

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
        

        id_string = f"redox-{base_molecule_doc.molecule_id}-{base_thermo_doc.lot_solvent}-" \
                    f"{base_thermo_doc.property_id}"
        origins = list()

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
            metal_element=
            metal_partial_charge=
            metal_partial_spin=
            partial_charges_property_id=partial_charges_property_id,
            partial_spins_property_id=partial_spins_property_id,
            partial_charges_lot_solvent=partial_charges_lot_solvent,
            partial_spins_lot_solvent=partial_spins_lot_solvent,
            charge_spin_method=
            number_coordinate_bonds=
            coordinating_atoms=
            coordinate_bond_lengths=
            bonding_property_id=
            bonding_level_of_theory=
            thermo_property_id=
            metal_thermo_property_id=
            nometal_thermo_property_id=
            binding_energy=
            binding_enthalpy=
            binding_entropy=
            binding_free_energy=
            thermo_level_of_theory=
            deprecated=deprecated,
            origins=origins,
            **kwargs
        )