""" Core definition for Defect property Document """
from datetime import datetime
from typing import ClassVar, Dict, Tuple, Mapping, List

from pymatgen.analysis.defects.core import DefectEntry

from emmet.core.mpid import MPID
from emmet.core.cp2k.task import TaskDocument
from emmet.core.cp2k.material import MaterialsDoc
from emmet.core.cp2k.calc_types.utils import run_type

from pymatgen.core import Structure, Composition
from pymatgen.analysis.defects.defect_compatibility import DefectCompatibility
import numpy as np
from pymatgen.ext.matproj import MPRester
from monty.json import MontyDecoder
from emmet.core.cp2k.calc_types.enums import CalcType, TaskType, RunType
from itertools import groupby
from pydantic import Field, validator
from emmet.builders.cp2k.utils import get_mpid, get_dielectric, matcher

from pymatgen.entries.computed_entries import CompositionEnergyAdjustment
from pymatgen.analysis.defects.thermodynamics import DefectPhaseDiagram, DefectPredominanceDiagram
from pydantic import BaseModel
from pymatgen.entries.compatibility import MaterialsProject2020Compatibility
from pymatgen.core import Element

from emmet.core.polar import Dielectric
from emmet.core.electronic_structure import ElectronicStructureDoc


class DefectDoc(BaseModel):
    """
    A document used to represent a single defect. e.g. a O vacancy with a -2 charge.

    This document can contain an arbitrary number of defect entries, originating from
    pairs (defect and bulk) of calculations. This document provides access to the "best"
    calculation of each run_type.
    """

    # TODO VASP MatDocs dont need this, but I get error requiring arbitrary type
    class Config:
        arbitrary_types_allowed = True

    property_name: ClassVar[str] = "defect"

    material_id: MPID = Field(None, description="Unique material ID for the host material")

    defect_id: MPID = Field(None, description="Unique ID for this defect")

    chemsys: List = Field(None, description="Chemical system of the bulk")

    calc_types: Mapping[str, CalcType] = Field(  # type: ignore
        None,
        description="Calculation types for all the calculations that make up this material",
    )
    task_types: Mapping[str, TaskType] = Field(
        None,
        description="Task types for all the calculations that make up this material",
    )
    run_types: Mapping[str, RunType] = Field(
        None,
        description="Run types for all the calculations that make up this material",
    )

    tasks: Mapping[RunType, Tuple[TaskDocument, TaskDocument]] = Field(
        None, description="Task documents (defect task, bulk task) for the defect entry of RunType"
    )

    task_ids: List[MPID] = Field(
        None, description="All task ids used in creating this defect doc."
    )

    entries: Mapping[RunType, DefectEntry] = Field(
        None, description="Dictionary for tracking entries for CP2K calculations"
    )

    # TODO How can monty serialization incorporate into pydantic? It seems like VASP MatDocs dont need this
    @validator("entries", pre=True)
    def decode(cls, entries):
        for e in entries:
            if isinstance(entries[e], dict):
                entries[e] = MontyDecoder().process_decoded({k: v for k, v in entries[e].items()})
        return entries

    @classmethod
    def from_tasks(cls, tasks: List, query='defect') -> "DefectDoc":
        """
        The standard way to create this document.

        Args:
            tasks: A list of defect,bulk task pairs which will be used to construct a
                series of DefectEntry objects.
            query: How to retrieve the defect object stored in the task.
        """
        task_group = [TaskDocument(**defect_task) for defect_task, bulk_task, dielectric in tasks]

        # Metadata
        last_updated = datetime.now() or max(task.last_updated for task in task_group)
        created_at = datetime.now() or min(task.completed_at for task in task_group)
        task_ids = list({task.task_id for task in task_group})

        deprecated_tasks = list(
            {task.task_id for task in task_group if not task.is_valid}
        )

        run_types = {task.task_id: task.run_type for task in task_group}
        task_types = {task.task_id: task.task_type for task in task_group}
        calc_types = {task.task_id: task.calc_type for task in task_group}

        def _run_type(x):
            return run_type(x[0]['input']['dft']).value

        entries = {}
        final_tasks = {}
        for key, tasks_for_runtype in groupby(sorted(tasks, key=_run_type), key=_run_type):
            entry_and_docs = [
                (
                    cls.get_defect_entry_from_tasks(
                        defect_task=defect_task,
                        bulk_task=bulk_task,
                        dielectric=dielectric,
                        query=query
                    ),
                    TaskDocument(**defect_task), TaskDocument(**bulk_task)
                )
                for defect_task, bulk_task, dielectric in tasks_for_runtype
            ]
            entry_and_docs.sort(key=lambda x: x[1].nsites, reverse=True)  # TODO Turn into kpoint density sorting
            best_entry, best_defect_task, best_bulk_task = entry_and_docs[0]
            entries[best_defect_task.run_type] = best_entry
            final_tasks[best_defect_task.run_type] = (best_defect_task, best_bulk_task)

        data = {
                'entries': entries,
                'run_types': run_types,
                'task_types': task_types,
                'calc_types': calc_types,
                'last_updated': last_updated,
                'created_at': created_at,
                'task_ids': set(task_ids),
                'deprecated_tasks': deprecated_tasks,
                'tasks': final_tasks,
                'material_id': list({v.parameters['material_id'] for v in entries.values()})[0],
                'entry_ids': {rt: entries[rt].entry_id for rt in entries},
                'chemsys': list([v.defect.bulk_structure.composition.elements for v in entries.values()])[0],
        }

        return cls(**{k: v for k, v in data.items()})

    @classmethod
    def get_defect_entry_from_tasks(cls, defect_task, bulk_task, dielectric=None, query='defect'):
        """
        Extract a defect entry from a single pair (defect and bulk) of tasks.

        Args:
            defect_task: task dict for the defect calculation
            bulk_task: task dict for the bulk calculation
            dielectric: Dielectric doc if the defect is charged. If not present, no dielectric
                corrections will be performed, even if the defect is charged.
            query: Mongo-style query to retrieve the defect object from the defect task
        """
        parameters = cls.get_parameters_from_tasks(defect_task=defect_task, bulk_task=bulk_task)
        if dielectric:
            parameters['dielectric'] = dielectric

        defect_entry = DefectEntry(
            cls.get_defect_from_task(query=query, task=defect_task),
            uncorrected_energy=parameters['defect_energy'] - parameters['bulk_energy'],
            parameters=parameters,
            entry_id=parameters['entry_id']
        )
        DefectCompatibility().process_entry(defect_entry, perform_corrections=True)
        defect_entry_as_dict = defect_entry.as_dict()
        defect_entry_as_dict['task_id'] = defect_entry_as_dict['entry_id']  # this seemed necessary for legacy db

        return defect_entry

    @classmethod
    def get_parameters_from_tasks(cls, defect_task, bulk_task):
        """
        Get parameters necessary to create a defect entry from defect and bulk task dicts

        Args:
            defect_task: task dict for the defect calculation
            bulk_task: task dict for the bulk calculation
        """

        def get_init(x):
            if x.get('transformations', {}).get('history'):
                return Structure.from_dict(x['transformations']['history'][0]['input_structure'])
            return Structure.from_dict(x['input']['structure'])

        init_defect_structure = get_init(defect_task)
        init_bulk_structure = get_init(bulk_task)  # use init to avoid site_properties in matching

        final_defect_structure = Structure.from_dict(defect_task['output']['structure'])
        final_bulk_structure = Structure.from_dict(bulk_task['output']['structure'])

        axis_grid = [[float(x) for x in _] for _ in defect_task['output']['v_hartree_grid']]
        bulk_planar_averages = [[float(x) for x in _] for _ in bulk_task['output']['v_hartree']]
        defect_planar_averages = [[float(x) for x in _] for _ in defect_task['output']['v_hartree']]

        dfi, site_matching_indices = matcher(
            init_bulk_structure, init_defect_structure,
            final_bulk_struc=final_bulk_structure, final_defect_struc=final_defect_structure
        )

        mpid = get_mpid(init_bulk_structure)

        parameters = {
            'defect_energy': defect_task['output']['energy'],
            'bulk_energy': bulk_task['output']['energy'],
            'axis_grid': axis_grid,
            'defect_frac_sc_coords': final_defect_structure[dfi].frac_coords,
            'defect_planar_averages': defect_planar_averages,
            'bulk_planar_averages': bulk_planar_averages,
            'site_matching_indices': site_matching_indices,
            'initial_defect_structure': init_defect_structure,
            'final_defect_structure': final_defect_structure,
            'vbm': bulk_task['output']['vbm'],
            'cbm': bulk_task['output']['cbm'],
            'material_id': mpid,
            'entry_id': defect_task.get('task_id')
        }

        # cannot be easily queried for, so check here.
        if 'v_hartree' in final_bulk_structure.site_properties:
            parameters['bulk_atomic_site_averages'] = final_bulk_structure.site_properties['v_hartree']
        if 'v_hartree' in final_defect_structure.site_properties:
            parameters['defect_atomic_site_averages'] = final_defect_structure.site_properties['v_hartree']

        return parameters

    @classmethod
    def get_defect_from_task(cls, query, task):
        """
        Unpack a Mongo-style query and retrieve a defect object from a task.
        """
        defect = unpack(query.split('.'), task)
        needed_keys = ['@module', '@class', 'structure', 'defect_site', 'charge', 'site_name']
        return MontyDecoder().process_decoded({k: v for k, v in defect.items() if k in needed_keys})


class DefectThermoDoc(BaseModel):

    class Config:
        arbitrary_types_allowed = True

    property_name: ClassVar[str] = "Defect Thermo"

    material_id: str = Field(None, description="Unique material ID for the host material")

    task_ids: Dict = Field(
        None, description="All task ids used in creating these phase diagrams"
    )

    defect_predominance_diagrams: Mapping[RunType, DefectPredominanceDiagram] = Field(
        None, description="Defect predominance diagrams"
    )

    # TODO How can monty serialization incorporate into pydantic? It seems like VASP MatDocs dont need this
    @validator("defect_predominance_diagrams", pre=True)
    def decode(cls, defect_predominance_diagrams):
        for e in defect_predominance_diagrams:
            if isinstance(defect_predominance_diagrams[e], dict):
                defect_predominance_diagrams[e] = MontyDecoder().process_decoded(
                    {k: v for k, v in defect_predominance_diagrams[e].items()}
                )
        return defect_predominance_diagrams

    @classmethod
    def from_docs(cls, docs: List[DefectDoc], materials: List[MaterialsDoc], electronic_structure: ElectronicStructureDoc) -> "DefectThermoDoc":

        DEFAULT_RT = RunType('GGA')  # TODO NEED A procedure for getting all GGA or GGA+U keys
        DEFAULT_RT_U = RunType('GGA+U')

        mpid = docs[0].material_id
        cls.get_adjusted_entries(materials=materials, defects=docs)

        defect_entries = {}
        defect_phase_diagram = {}
        vbms = {}
        band_gaps = {}
        defect_predominance_diagrams = {}
        task_ids = {}

        dos = electronic_structure.dos.total

        for m in materials:
            for run_type in m.entries:
                bg = dos.get_gap()
                band_gaps[run_type] = bg

        for d in docs:
            for run_type in d.entries:
                if run_type not in defect_entries:
                    defect_entries[run_type] = []
                if run_type not in task_ids:
                    task_ids[run_type] = set()
                defect_entries[run_type].append(d.entries[run_type])
                vbms[run_type] = d.entries[run_type].parameters['vbm']  # TODO Need to find best vbm
                task_ids[run_type].update(d.task_ids)

        for run_type in defect_entries:
            # TODO MUST FILTER COMPATIBLE AT SOME POINT
            defect_phase_diagram[run_type] = DefectPhaseDiagram(
                entries=defect_entries[run_type],
                vbm=vbms[run_type],
                band_gap=band_gaps[run_type],
                filter_compatible=False
            )
            defect_predominance_diagrams[run_type] = DefectPredominanceDiagram(
                defect_phase_diagram=defect_phase_diagram[run_type],
                bulk_dos=dos,
                entries=[
                    m.entries[run_type]
                    if run_type in m.entries else m.entries[DEFAULT_RT_U]
                    if DEFAULT_RT_U in m.entries else m.entries[DEFAULT_RT]
                    for m in materials
                ]
            )

        data = {
            'material_id': mpid,
            'task_ids': task_ids,
            'defect_predominance_diagrams': defect_predominance_diagrams,
        }

        return cls(**{k: v for k, v in data.items()})

    @classmethod
    def get_adjusted_entries(cls, materials: List[MaterialsDoc], defects: List[DefectDoc]):
        """
        Shift the energy of all entries to formation energy space, i.e. elemental entries to 0eV

        The chemical potentials (elemental energies) are acquired for each run type that is available
        in materials. If a chempot does not exist for a non-standard run type, but does exist for
        a GGA calculation, then this will be used as the fall-back.

        Args:
            materials: list of MaterialsDocs with *ComputedStructureEntries* as the entries

            defects: list of DefectDocs

        returns:
            None
        """

        DEFAULT_RT = RunType('GGA')  # TODO NEED A procedure for getting all GGA or GGA+U keys

        chempots = {
            m.structure.composition.elements[0].element:
                {rt: m.entries[rt].energy_per_atom for rt in m.entries}
            for m in materials if m.structure.composition.is_element
        }

        for m in materials:
            for rt, ent in m.entries.items():
                ent.parameters['software'] = 'cp2k'
                ent.structure.remove_spin()
                ent.structure.remove_oxidation_states()
                MaterialsProject2020Compatibility().process_entry(ent)
                for el, amt in ent.composition.element_composition.items():
                    _rt = DEFAULT_RT if rt not in chempots[Element(el)] else rt
                    adj = CompositionEnergyAdjustment(-chempots[Element(el)][_rt],
                                                      n_atoms=amt,
                                                      name=f"Elemental shift {el} to formation energy space"
                                                      )
                    ent.energy_adjustments.append(adj)

        for d in defects:
            for rt, ent in d.entries.items():
                comp = Composition(ent.defect.defect_composition, allow_negative=True) - \
                       ent.defect.bulk_structure.composition
                for el, amt in comp.items():
                    _rt = DEFAULT_RT if rt not in chempots[Element(el)] else rt
                    ent.corrections[f"Elemental shift {el} to formation energy space"] = -amt*chempots[Element(el)][_rt]


def get_dos(mpid):
    with MPRester() as mp:
        return mp.get_dos_by_material_id(mpid)


def get_entries(chemsys):
    with MPRester() as mp:
        return mp.get_entries_in_chemsys(chemsys)


def unpack(query, d):
    if not query:
        return d
    if isinstance(d, List):
        return unpack(query[1:], d.__getitem__(int(query.pop(0))))
    return unpack(query[1:], d.__getitem__(query.pop(0)))
