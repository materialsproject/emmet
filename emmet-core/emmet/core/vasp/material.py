""" Core definition of a Materials Document """
from datetime import datetime
from functools import partial
from typing import ClassVar, Optional, Union, Sequence, Mapping

from pydantic import BaseModel, Field, create_model

from emmet.core.material import MaterialsDoc as CoreMaterialsDoc
from emmet.core.material import PropertyOrigin as CorePropertyOrigin
from emmet.core.structure import StructureMetadata
from emmet.core.vasp.calc_types import CalcType, RunType, TaskType
from emmet.stubs import Structure, ComputedEntry


class PropertyOrigin(CorePropertyOrigin):
    """
    Provenance document for the origin of properties in a material document from VASP calculations
    """

    calc_type: CalcType = Field(
        ..., description="The original calculation type this propeprty comes from"
    )


class MaterialsDoc(CoreMaterialsDoc, StructureMetadata):

    calc_types: Mapping[str, CalcType] = Field(
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

    origins: Sequence[PropertyOrigin] = Field(
        None, description="Mappingionary for tracking the provenance of properties"
    )

    entries: Mapping[RunType, ComputedEntry] = Field(
        None, description="Dictionary for tracking entries for VASP calculations"
    )
