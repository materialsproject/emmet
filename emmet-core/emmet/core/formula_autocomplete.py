from pydantic import Field, BaseModel
from typing import Optional


class FormulaAutocomplete(BaseModel):
    """
    Class defining formula autocomplete return data
    """

    formula_pretty: Optional[str] = Field(
        None,
        description="Human readable chemical formula.",
    )
