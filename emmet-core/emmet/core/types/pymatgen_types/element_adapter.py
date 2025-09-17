from typing import Annotated, TypeVar

from pydantic.functional_serializers import WrapSerializer
from pydantic.functional_validators import BeforeValidator
from pymatgen.core import Element

ElementTypeVar = TypeVar("ElementTypeVar", Element, str)

ElementType = Annotated[
    ElementTypeVar,
    BeforeValidator(lambda x: Element(x) if isinstance(x, str) else x),
    WrapSerializer(lambda x, nxt, info: str(x), return_type=str),
]
