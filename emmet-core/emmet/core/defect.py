""" Core definition for Defect property Document """
from datetime import datetime
from typing import ClassVar, Dict, Tuple, Mapping, List
from monty.json import MontyDecoder
from itertools import groupby
from pydantic import Field, validator, BaseModel

from pymatgen.core import Structure, Composition, Element
from pymatgen.analysis.defects.core import DefectEntry
from pymatgen.analysis.defects.defect_compatibility import DefectCompatibility
from pymatgen.analysis.defects.thermodynamics import DefectPhaseDiagram, DefectPredominanceDiagram
from pymatgen.electronic_structure.dos import CompleteDos
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from pymatgen.entries.computed_entries import CompositionEnergyAdjustment
from pymatgen.entries.compatibility import MaterialsProject2020Compatibility
from pymatgen.ext.matproj import MPRester

from emmet.core.structure import StructureMetadata
from emmet.core.mpid import MPID
from emmet.core.cp2k.task import TaskDocument
from emmet.core.cp2k.calc_types.enums import CalcType, TaskType, RunType
from emmet.core.cp2k.material import MaterialsDoc
from emmet.core.cp2k.calc_types.utils import run_type
from emmet.builders.cp2k.utils import get_mpid, matcher


# TODO Update DefectDoc on defect entry level so you don't re-do uncessary corrections
class DefectDoc(StructureMetadata):
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

    name: str = Field(None, description="Name of this defect")

    charge: int = Field(None, description="Charge of this defect")

    material_id: MPID = Field(None, description="Unique material ID for the bulk material")

    task_ids: List[int] = Field(
        None, description="All task ids used in creating this defect doc."
    )

    calc_types: Mapping[int, CalcType] = Field(  # type: ignore
        None,
        description="Calculation types for all the calculations that make up this material",
    )
    task_types: Mapping[int, TaskType] = Field(
        None,
        description="Task types for all the calculations that make up this material",
    )
    run_types: Mapping[int, RunType] = Field(
        None,
        description="Run types for all the calculations that make up this material",
    )

    tasks: Mapping[RunType, Tuple[TaskDocument, TaskDocument]] = Field(
        None, description="Task documents (defect task, bulk task) for the defect entry of RunType"
    )

    entries: Mapping[RunType, DefectEntry] = Field(
        None, description="Dictionary for tracking entries for CP2K calculations"
    )

    last_updated: datetime = Field(
        description="Timestamp for when this document was last updated",
        default_factory=datetime.utcnow,
    )

    created_at: datetime = Field(
        description="Timestamp for when this material document was first created",
        default_factory=datetime.utcnow,
    )

    # TODO How can monty serialization incorporate into pydantic? It seems like VASP MatDocs dont need this
    @validator("entries", pre=True)
    def decode(cls, entries):
        for e in entries:
            if isinstance(entries[e], dict):
                entries[e] = MontyDecoder().process_decoded({k: v for k, v in entries[e].items()})
        return entries

    def update(self, defect_task, bulk_task, dielectric, query='defect'):

        defect_task_doc = TaskDocument(**defect_task)
        bulk_task_doc = TaskDocument(**bulk_task)

        rt = defect_task_doc.run_type
        tt = defect_task_doc.task_type
        ct = defect_task_doc.calc_type

        # Metadata
        last_updated = max(dtsk.last_updated for dtsk, btsk in self.tasks.values()) if self.tasks else datetime.now()
        created_at = min(dtsk.last_updated for dtsk, btsk in self.tasks.values()) if self.tasks else datetime.now()

        if defect_task_doc.task_id in self.task_ids:
            return
        else:
            self.last_updated = last_updated
            self.created_at = created_at
            self.task_ids.append(defect_task_doc.task_id)
            #self['deprecated_tasks'].update(defect_task.task_id)

            def _run_type(x):
                return run_type(x[0]['input']['dft']).value

            def _compare(new, old):
                # TODO return kpoint density
                return new['nsites'] > old['nsites']

            if defect_task_doc.run_type not in self.tasks or _compare(defect_task, self.tasks[rt]):
                self.run_types.update({defect_task_doc.task_id: rt})
                self.task_types.update({defect_task_doc.task_id: tt})
                self.calc_types.update({defect_task_doc.task_id: ct})
                entry = self.get_defect_entry_from_tasks(
                            defect_task=defect_task,
                            bulk_task=bulk_task,
                            dielectric=dielectric,
                            query=query
                        )
                self.entries[rt] = entry
                self.tasks[rt] = (defect_task_doc, bulk_task_doc)

    def update_all(self, tasks, query='defect'):
        for defect_task, bulk_task, dielectric in tasks:
            self.update(defect_task=defect_task, bulk_task=bulk_task, dielectric=dielectric, query=query)

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
        task_ids = {task.task_id for task in task_group}

        deprecated_tasks = list(
            {task.task_id for task in task_group if not task.is_valid}
        )

        run_types = {task.task_id: task.run_type for task in task_group}
        task_types = {task.task_id: task.task_type for task in task_group}
        calc_types = {task.task_id: task.calc_type for task in task_group}

        def _run_type(x):
            return run_type(x[0]['input']['dft']).value

        def _sort(x):
            # TODO return kpoint density, currently just does supercell size
            return x[1].nsites

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
            entry_and_docs.sort(key=_sort, reverse=True)
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
                'task_ids': task_ids,
                'deprecated_tasks': deprecated_tasks,
                'tasks': final_tasks,
                'material_id': best_entry.parameters['material_id'],
                'entry_ids': {rt: entries[rt].entry_id for rt in entries},
                'name': best_entry.defect.name,
                'charge': best_entry.defect.charge,
        }
        prim = SpacegroupAnalyzer(best_entry.defect.bulk_structure).get_primitive_standard_structure()
        data.update(StructureMetadata.from_structure(prim).dict())
        return cls(**data)

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
    def get_defect_from_task(cls, query, task):
        """
        Unpack a Mongo-style query and retrieve a defect object from a task.
        """
        defect = unpack(query.split('.'), task)
        needed_keys = ['@module', '@class', 'structure', 'defect_site', 'charge', 'site_name']
        return MontyDecoder().process_decoded({k: v for k, v in defect.items() if k in needed_keys})

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
    def from_docs(cls, defects: List[DefectDoc], materials: List[MaterialsDoc], electronic_structure: CompleteDos) -> "DefectThermoDoc":

        DEFAULT_RT = RunType('GGA')  # TODO NEED A procedure for getting all GGA or GGA+U keys
        DEFAULT_RT_U = RunType('GGA+U')

        mpid = defects[0].material_id

        chempots = {
            m.structure.composition.elements[0]:
                {rt: m.entries[rt].energy_per_atom for rt in m.entries}
            for m in materials if m.structure.composition.is_element
        }

        defect_entries = {}
        defect_phase_diagram = {}
        vbms = {}
        band_gaps = {}
        defect_predominance_diagrams = {}
        task_ids = {}

        dos = CompleteDos.from_dict(electronic_structure)
        bg = dos.get_gap()

        for m in materials:
            for rt, ent in m.entries.items():
                # Chempot shift
                for el, amt in ent.composition.element_composition.items():
                    _rt = DEFAULT_RT if rt not in chempots[Element(el)] else rt
                    adj = CompositionEnergyAdjustment(-chempots[Element(el)][_rt],
                                                      n_atoms=amt,
                                                      name=f"Elemental shift {el} to formation energy space"
                                                      )
                    ent.energy_adjustments.append(adj)

                # Other stuff
                band_gaps[rt] = bg
                ent.parameters['software'] = 'cp2k'
                ent.structure.remove_spin()
                ent.structure.remove_oxidation_states()
                MaterialsProject2020Compatibility().process_entry(ent)

        for d in defects:
            for rt, ent in d.entries.items():
                # Chempot shift
                __found_chempots__ = True
                comp = Composition(ent.defect.defect_composition, allow_negative=True) - \
                       ent.defect.bulk_structure.composition
                for el, amt in comp.items():
                    if Element(el) not in chempots:
                        __found_chempots__ = False
                        break
                    _rt = DEFAULT_RT if rt not in chempots[Element(el)] else rt
                    ent.corrections[f"Elemental shift {el} to formation energy space"] = -amt * chempots[Element(el)][
                        _rt]

                if not __found_chempots__:
                    continue

                # Other stuff
                if rt not in defect_entries:
                    defect_entries[rt] = []
                if rt not in task_ids:
                    task_ids[rt] = set()
                defect_entries[rt].append(d.entries[rt])
                vbms[rt] = d.entries[rt].parameters['vbm']  # TODO Need to find best vbm
                task_ids[rt].update(d.task_ids)

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
