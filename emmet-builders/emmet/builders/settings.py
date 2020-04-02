from typing import Dict, List
from pydantic import Field, validator
from emmet.core.settings import EmmetSettings
from atomate.utils.utils import load_class


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

    @validator("default_input_sets", pre=True)
    def load_input_sets(cls, values):
        input_sets = {}
        for name, inp_set in values.items():
            if isinstance(inp_set, str):
                _module = ".".join(inp_set.split(".")[:-1])
                _class = inp_set.split(".")[-1]
                input_sets[name] = load_class(_module, _class)

        return input_sets
