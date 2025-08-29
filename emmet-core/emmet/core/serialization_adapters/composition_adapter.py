from typing import Annotated, TypeVar

from pydantic import BeforeValidator, WrapSerializer
from pymatgen.core import Composition

CompositionTypeVar = TypeVar("CompositionTypeVar", Composition, dict[str, float])

AnnotatedComposition = Annotated[
    CompositionTypeVar,
    BeforeValidator(lambda x: Composition.from_dict(x) if isinstance(x, dict) else x),
    WrapSerializer(lambda x, nxt, info: x.as_dict(), return_type=dict[str, float]),
]
