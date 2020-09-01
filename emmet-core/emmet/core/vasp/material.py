""" Core definition of a Materials Document """
from datetime import datetime
from functools import partial
from typing import ClassVar, Dict, List, Optional, Union

from pydantic import BaseModel, Field, create_model

from emmet.core.material import MaterialsDoc as CoreMaterialsDoc
from emmet.core.material import PropertyOrigin as CorePropertyOrigin
from emmet.core.structure import StructureMetadata
from emmet.core.vasp.calc_types import CalcType, RunType, TaskType
from emmet.stubs import Structure


class PropertyOrigin(CorePropertyOrigin):
    """
    Provenance document for the origin of properties in a material document from VASP calculations
    """

    task_type: TaskType = Field(
        ..., description="The original calculation type this propeprty comes from"
    )


class MaterialsDoc(CoreMaterialsDoc, StructureMetadata):

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
