""" Utilities to enable stubbing in JSON schema into pydantic for Monty """
from typing import Dict, Any, TypeVar, Union, Optional, Tuple, List, Set, Sequence, Type
from typing import get_type_hints
from numpy import ndarray
from monty.json import MSONable, MontyDecoder
from pydantic import create_model, Field, BaseModel
from pydantic.fields import ModelField, FieldInfo

built_in_primitives = (bool, int, float, complex, range, str, bytes, None)
prim_to_type_hint: Dict[type, Any] = {list: List, tuple: Tuple, dict: Dict, set: Set}

STUBS: Dict[type, type] = {}  # Central location for Pydantic Stub classes


def patch_msonable(monty_cls: type):
    """
    Patch's an MSONable class so it can be used in pydantic models

    monty_cls: A MSONable class
    """

    if not issubclass(monty_cls, MSONable):
        raise ValueError("Must provide an MSONable class to wrap")

    def __get_validators__(cls):
        yield cls.validate_monty

    def validate_monty(cls, v):
        """
        Stub validator for MSONable
        """
        if isinstance(v, cls):
            return v
        elif isinstance(v, dict):
            # Relegate to Monty
            new_obj = MontyDecoder().process_decoded(v)
            if not isinstance(new_obj, cls):
                raise ValueError(f"Wrong dict for {cls.__name__}")
            return new_obj
        else:
            raise ValueError(f"Must provide {cls.__name__} or Dict version")

    setattr(monty_cls, "validate_monty", classmethod(validate_monty))
    setattr(monty_cls, "__get_validators__", classmethod(__get_validators__))
    setattr(monty_cls, "__pydantic_model__", STUBS[monty_cls])


def use_model(monty_cls: type, pydantic_model: type, add_monty: bool = True):
    """
    Use a provided pydantic model to describe a Monty MSONable class
    """

    if add_monty:
        STUBS[monty_cls] = MSONable_to_pydantic(
            monty_cls, pydantic_model=pydantic_model
        )
    else:
        STUBS[monty_cls] = pydantic_model
    patch_msonable(monty_cls)


def __make_pydantic(cls):
    """
    Temporary wrapper function to convert an MSONable class into a PyDantic
    Model for the sake of building schemas
    """

    if any(cls == T for T in built_in_primitives):
        return cls

    if cls in prim_to_type_hint:
        return prim_to_type_hint[cls]

    if cls == Any:
        return Any

    if type(cls) == TypeVar:
        return cls

    if hasattr(cls, "__origin__") and hasattr(cls, "__args__"):

        args = tuple(__make_pydantic(arg) for arg in cls.__args__)
        if cls.__origin__ == Union:
            return Union.__getitem__(args)

        if cls.__origin__ == Optional and len(args) == 1:
            return Optional.__getitem__(args)

        if cls._name == "List":
            return List.__getitem__(args)

        if cls._name == "Tuple":
            return Tuple.__getitem__(args)

        if cls._name == "Set":
            return Set.__getitem__(args)

        if cls._name == "Sequence":
            return Sequence.__getitem__(args)

    if issubclass(cls, MSONable):
        if cls.__name__ not in STUBS:
            STUBS[cls] = MSONable_to_pydantic(cls)
        return STUBS[cls]

    if cls == ndarray:
        return List[Any]

    return cls


def MSONable_to_pydantic(monty_cls: type, pydantic_model=None):
    monty_props = {
        "@class": (
            str,
            Field(
                default=monty_cls.__name__,
                title="MSONable Class",
                description="The formal class name for serialization lookup",
            ),
        ),
        "@module": (
            str,
            Field(
                default=monty_cls.__module__,
                title="Python Module",
                description="The module this class is defined in",
            ),
        ),
    }
    if pydantic_model:
        props = {
            name: (field.type_, field.field_info)
            for name, field in pydantic_model.__fields__.items()
        }
    else:
        _type_hints = get_type_hints(monty_cls.__init__).items()  # type: ignore
        props = {
            field_name: (__make_pydantic(field_type), FieldInfo(...))
            for field_name, field_type in _type_hints
        }

    return create_model(monty_cls.__name__, field_definitions={**monty_props, **props})
