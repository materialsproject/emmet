from pydantic import Field
from typing import List

from emmet.core.mpid import MPID
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
        cls, task: TaskDocument, molecule_id: MPID, preferred_methods: List, deprecated: bool = False, **kwargs
    ):  # type: ignore[override]
        """
        Determine partial charges from a task document

        :param task: task document from which partial charges can be extracted
        :param molecule_id: mpid
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
                charges = task.output.resp
                break
            elif m == "critic2" and task.critic2 is not None:
                method = m
                charges = list(task.critic2["processed"]["charges"])
                break
            elif m == "mulliken" and task.output.mulliken is not None:
                method = m
                if mol.spin_multiplicity == 1:
                    charges = task.output.mulliken
                else:
                    charges = [mull[0] for mull in task.output.mulliken]
                break

        if charges is None:
            raise Exception("No valid partial charge information!")

        return super().from_molecule(
            meta_molecule=mol,
            molecule_id=molecule_id,
            partial_charges=charges,
            method=method,
            deprecated=deprecated,
            origins=[PropertyOrigin(name="partial_charges", task_id=task.task_id)],
            **kwargs
        )


class PartialSpinsDoc(PropertyDoc):
    """Atomic partial charges of a molecule"""

    property_name = "partial_spins"

    method: str = Field(..., description="Method used to compute atomic partial spins")

    partial_spins: List[float] = Field(..., description="Atomic partial spins for the molecule")

    @classmethod
    def from_task(
        cls, task: TaskDocument, molecule_id: MPID, preferred_methods: List, deprecated: bool = False, **kwargs
    ):  # type: ignore[override]
        """
        Determine partial spins from a task document

        :param task: task document from which partial spins can be extracted
        :param molecule_id: mpid
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
                spins = [mull[1] for mull in task.output.mulliken]
                break

        if spins is None:
            raise Exception("No valid partial spin information!")

        return super().from_molecule(
            meta_molecule=mol,
            deprecated=deprecated,
            molecule_id=molecule_id,
            partial_spins=spins,
            method=method,
            origins=[PropertyOrigin(name="partial_spins", task_id=task.task_id)],
            **kwargs
        )
