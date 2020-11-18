""" Core definitions of Molecules-related documents """

from datetime import datetime

from typing import (
    Mapping,
    Sequence,
    TypeVar,
    Type,
    List
)

from pydantic import Field

from pymatgen.analysis.molecule_matcher import MoleculeMatcher

from emmet.stubs import Composition, Molecule
from emmet.core.utils import ID_to_int
from emmet.core.qchem.calc_types import TaskType, LevelOfTheory
from emmet.core.qchem.mol_metadata import MoleculeMetadata
from emmet.core.qchem.task import TaskDocument
from emmet.core.qchem.solvent import SolventData


S = TypeVar("S", bound="MoleculeDoc")


class MoleculeDoc(MoleculeMetadata):
    """
    Definition for a Molecule Document
    """

    molecule_id: str = Field(
        ...,
        description="The ID of this molecule, used as a universal reference across all related Documents."
        "This comes in the form mpmol-*******",
    )

    molecule: Molecule = Field(
        ..., description="The lowest-energy optimized structure for this molecule"
    )

    molecule_solvent_model: SolventData = Field(
        ..., description="Solvent information for chosen structure for this molecule"
    )

    task_ids: Sequence[str] = Field(
        [],
        title="Calculation IDs",
        description="List of Calculations IDs used to make this Molecule Document",
    )

    task_types: Mapping[str, TaskType] = Field(
        None,
        description="Task types for all calculations that make up this molecule",
    )

    lots: Mapping[str, LevelOfTheory] = Field(
        None,
        description="Levels of theory for all calculations that make up this molecule",
    )

    calc_types: Mapping[str, str] = Field(
        None,
        description="Calculation types for all the calculations that make up this molecule",
    )

    last_updated: datetime = Field(
        description="Timestamp for when this molecule document was last updated",
        default_factory=datetime.utcnow,
    )

    initial_molecules: Sequence[Molecule] = Field(
        [],
        description="Initial structures used in the geometry optimizations corresponding to this material",
    )

    created_at: datetime = Field(
        description="Timestamp for when this molecule document was first created",
        default_factory=datetime.utcnow,
    )

    warnings: Sequence[str] = Field(
        [], description="Any warnings related to this molecule"
    )

    @classmethod
    def from_tasks(
            cls: Type[S],
            task_group: List[TaskDocument]
    ) -> S:

        last_updated = max(task.last_updated for task in task_group)
        created_at = min(task.completed_at for task in task_group)
        task_ids = list({task.task_id for task in task_group})

        task_types = {task.task_id: task.task_type for task in task_group}
        lots = {task.task_id: task.level_of_theory for task in task_group}
        calc_types = {task.task_id: task.calc_type for task in task_group}

        geom_opts = [
            task
            for task in task_group
            if task.task_type in [
                TaskType.geometry_optimization,
                TaskType.transition_state_optimization,
                TaskType.frequency_flattening_optimization,
                TaskType.frequency_flattening_transition_state_optimization
            ]
        ]

        single_points = [
            task
            for task in task_group
            if task.task_type == TaskType.single_point
        ]

        possible_mol_ids = [task.task_id for task in geom_opts]
        possible_mol_ids = sorted(possible_mol_ids, key=ID_to_int)

        if len(possible_mol_ids) == 0:
            raise Exception(f"Could not find a molecule ID for {task_ids}")
        else:
            molecule_id = possible_mol_ids[0]

        geom_calcs = geom_opts + single_points
        best_geom_calc = sorted(geom_calcs, key=lambda x: x.output.energy)[0]

        molecule = best_geom_calc.output.molecule
        mol_solvent = best_geom_calc.input.level_of_theory.solvent_data

        initial_molecules = [task.input.molecule for task in task_group]

        mm = MoleculeMatcher(tolerance=0.1)
        initial_molecules = [
            group[0] for group in mm.group_structures(initial_molecules)
        ]

        entries = {}
        all_lots = {lot.as_string for lot in lots.values()}
        for lot in all_lots:
            relevant_calcs = sorted(
                [doc for doc in geom_calcs if doc.lot.as_string == lot],
                key=lambda x: x.output.energy,
            )
            if len(relevant_calcs) > 0:
                best_task_doc = relevant_calcs[0]
                entry = best_task_doc.entry
                entry.data["task_id"] = entry.entry_id
                entry.entry_id = molecule_id
                entries[lot] = entry

        return cls.from_molecule(
            molecule=molecule,
            molecule_id=molecule_id,
            include_molecule=True,
            last_updated=last_updated,
            created_at=created_at,
            task_ids=task_ids,
            calc_types=calc_types,
            lots=lots,
            task_types=task_types,
            initial_molecules=initial_molecules,
            entries=entries,
        )
