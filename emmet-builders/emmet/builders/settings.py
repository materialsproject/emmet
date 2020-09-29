from typing import Dict, List, Optional
import importlib
from pydantic import Field, validator
from emmet.core.settings import EmmetSettings
from emmet.core.vasp.calc_types import RunType


class EmmetBuilderSettings(EmmetSettings):
    default_input_sets: Dict[str, type] = Field(
        {
            "GGA Structure Optimization": "pymatgen.io.vasp.sets.MPRelaxSet",
            "GGA+U Structure Optimization": "pymatgen.io.vasp.sets.MPRelaxSet",
        },
        description="Default input sets for task validation",
    )

    kpts_tolerance: float = Field(
        0.9, description="Default tolerance for task validation"
    )
    ldau_fields: List[str] = Field(
        ["LDAUU", "LDAUJ", "LDAUL"], description="LDAU fields to validate for tasks"
    )

    vasp_qual_scores: Dict[RunType, int] = Field(
        {"SCAN": 3, "GGA+U": 2, "GGA": 1},
        description="Dictionary Mapping VASP calculation run types to rung level for VASP materials builders",
    )

    tags_to_sandboxes: Optional[Dict[str, List[str]]] = Field(
        None, description="Mapping of calcuation tags to sandboxes. Any calculation without these tags will be kept as core."
    )

    @validator("default_input_sets", pre=True)
    def load_input_sets(cls, values):
        input_sets = {}
        for name, inp_set in values.items():
            if isinstance(inp_set, str):
                _module = ".".join(inp_set.split(".")[:-1])
                _class = inp_set.split(".")[-1]
                input_sets[name] = getattr(importlib.import_module(_module), _class)

        return input_sets
