""" Core definition of a Materials Document """
from typing import List, Dict, ClassVar, Union, Optional
from functools import partial
from datetime import datetime


from pydantic import BaseModel, Field, create_model

from emmet.stubs import Structure
from emmet.core.structure import StructureMetadata
from emmet.core.vasp.calc_types import TaskType, CalcType, RunType

from emmet.core.material import MaterialsDoc as CoreMaterialsDoc
from emmet.core.material import PropertyOrigin as CorePropertyOrigin


class PropertyOrigin(CorePropertyOrigin):
    """
    Provenance document for the origin of properties in a material document from VASP calculations
    """

    task_type: TaskType = Field(
        ..., description="The original calculation type this propeprty comes from"
    )


class MaterialsDoc(CoreMaterialsDoc, StructureMetadata):

    initial_structures: List[Structure] = Field(
        None,
        description="Initial structures used in the DFT optimizations corresponding to this material",
    )

    task_ids: List[str] = Field(
        None,
        title="Calculation IDs",
        description="List of Calculations IDs used to make this Materials Document",
    )

    deprecated_tasks: List[str] = Field(None, title="Deprecated Tasks")

    calc_types: Dict[str, CalcType] = Field(
        None,
        description="Calculation types for all the calculations that make up this material",
    )
    task_types: Dict[str, TaskType] = Field(
        None,
        description="Task types for all the calculations that make up this material",
    )
    run_types: Dict[str, RunType] = Field(
        None,
        description="Run types for all the calculations that make up this material",
    )

    origins: List[PropertyOrigin] = Field(
        None, description="Dictionary for tracking the provenance of properties"
    )
