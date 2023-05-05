from typing import List
from hashlib import blake2b

from pydantic import Field

from emmet.core.mpid import MPculeID
from emmet.core.qchem.task import TaskDocument
from emmet.core.material import PropertyOrigin
from emmet.core.molecules.molecule_property import PropertyDoc


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"

CHARGES_METHODS = ["nbo", "resp", "critic2", "mulliken"]
SPINS_METHODS = ["nbo", "mulliken"]


class PartialChargesDoc(PropertyDoc):
    """Atomic partial charges of a molecule"""

    property_name = "partial_charges"

    method: str = Field(..., description="Method used to compute atomic partial charges")

    partial_charges: List[float] = Field(..., description="Atomic partial charges for the molecule")

    @classmethod
    def from_task(
        cls,
        task: TaskDocument,
        molecule_id: MPculeID,
        preferred_methods: List[str],
        deprecated: bool = False,
        **kwargs
    ):  # type: ignore[override]
        """
        Determine partial charges from a task document

        :param task: task document from which partial charges can be extracted
        :param molecule_id: MPculeID
        :param preferred_methods: list of methods; by default, NBO7, RESP, Critic2, and Mulliken, in that order
        :param kwargs: to pass to PropertyDoc
        :return:
        """

        charges = None
        method = None

        if task.output.optimized_molecule is not None:
            mol = task.output.optimized_molecule
        else:
            mol = task.output.initial_molecule

        for m in preferred_methods:
            if m == "nbo" and task.output.nbo is not None:
                method = m
                charges = [float(task.output.nbo["natural_populations"][0]["Charge"][str(i)]) for i in range(len(mol))]
                break
            elif m == "resp" and task.output.resp is not None:
                method = m
                charges = [float(i) for i in task.output.resp]
                break
            elif m == "critic2" and task.critic2 is not None:
                method = m
                charges = list([float(i) for i in task.critic2["processed"]["charges"]])
                break
            elif m == "mulliken" and task.output.mulliken is not None:
                method = m
                if isinstance(task.output.mulliken[0], list):
                    charges = [float(mull[0]) for mull in task.output.mulliken]
                else:
                    charges = [float(i) for i in task.output.mulliken]
                break

        id_string = f"partial_charges-{molecule_id}-{task.task_id}-{task.lot_solvent}-{method}"
        h = blake2b()
        h.update(id_string.encode("utf-8"))
        property_id = h.hexdigest()

        if charges is None:
            raise Exception("No valid partial charge information!")

        return super().from_molecule(
            meta_molecule=mol,
            property_id=property_id,
            molecule_id=molecule_id,
            level_of_theory=task.level_of_theory,
            solvent=task.solvent,
            lot_solvent=task.lot_solvent,
            partial_charges=charges,
            method=method,
            origins=[PropertyOrigin(name="partial_charges", task_id=task.task_id)],
            deprecated=deprecated,
            **kwargs
        )


class PartialSpinsDoc(PropertyDoc):
    """Atomic partial charges of a molecule"""

    property_name = "partial_spins"

    method: str = Field(..., description="Method used to compute atomic partial spins")

    partial_spins: List[float] = Field(
        ..., description="Atomic partial spins for the molecule"
    )

    @classmethod
    def from_task(
        cls,
        task: TaskDocument,
        molecule_id: MPculeID,
        preferred_methods: List[str],
        deprecated: bool = False,
        **kwargs
    ):  # type: ignore[override]
        """
        Determine partial spins from a task document

        :param task: task document from which partial spins can be extracted
        :param molecule_id: MPculeID
        :param preferred_methods: list of methods; by default, NBO7 and Mulliken, in that order
        :param kwargs: to pass to PropertyDoc
        :return:
        """

        spins = None
        method = None

        if task.output.optimized_molecule is not None:
            mol = task.output.optimized_molecule
        else:
            mol = task.output.initial_molecule

        if mol.spin_multiplicity == 1:
            raise Exception("Closed-shell molecule has no partial spins!")

        for m in preferred_methods:
            if m == "nbo" and task.output.nbo is not None:
                method = m
                spins = [float(task.output.nbo["natural_populations"][0]["Density"][str(i)]) for i in range(len(mol))]
                break
            elif m == "mulliken" and task.output.mulliken is not None:
                method = m
                spins = [float(mull[1]) for mull in task.output.mulliken]
                break

        id_string = f"partial_spins-{molecule_id}-{task.task_id}-{task.lot_solvent}-{method}"
        h = blake2b()
        h.update(id_string.encode("utf-8"))
        property_id = h.hexdigest()

        if spins is None:
            raise Exception("No valid partial spin information!")

        return super().from_molecule(
            meta_molecule=mol,
            property_id=property_id,
            molecule_id=molecule_id,
            level_of_theory=task.level_of_theory,
            solvent=task.solvent,
            lot_solvent=task.lot_solvent,
            partial_spins=spins,
            method=method,
            origins=[PropertyOrigin(name="partial_spins", task_id=task.task_id)],
            deprecated=deprecated,
            **kwargs
        )
