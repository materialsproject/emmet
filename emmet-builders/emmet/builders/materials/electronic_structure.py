from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from functools import update_wrapper

from pydantic import BaseModel
from pymatgen.analysis.magnetism.analyzer import Ordering

from emmet.builders.utils import try_call
from emmet.core.electronic_structure import ElectronicStructureDoc
from emmet.core.material import PropertyOrigin
from emmet.core.types.electronic_structure import BSShim, DosShim
from emmet.core.types.pymatgen_types.structure_adapter import StructureType
from emmet.core.types.typing import IdentifierType


class InputMeta(BaseModel):
    # structure metadata
    deprecated: bool = False
    material_id: IdentifierType | None = None
    meta_structure: StructureType
    origins: list[PropertyOrigin] = []
    warnings: list[str] = []


class StructureInputs(InputMeta):
    # summary electronic structure data from VASP outputs for task doc
    band_gap: float
    cbm: float | None = None
    vbm: float | None = None
    efermi: float | None = None
    is_gap_direct: bool
    is_metal: bool
    magnetic_ordering: Ordering


class StructuresShim(InputMeta):
    # map of structures with task_ids -> used in post doc build checks
    structures: dict[IdentifierType, StructureType]


class BSInputs(StructuresShim):
    bandstructures: BSShim


class DosInputs(StructuresShim):
    dos: DosShim
    is_gap_direct: bool


class BSDosInputs(DosInputs, BSInputs): ...


class Variant(Enum):
    STRUCTURE = auto()
    BS = auto()
    DOS = auto()
    BS_DOS = auto()


InputData = list[StructureInputs] | list[BSInputs] | list[DosInputs] | list[BSDosInputs]
"""Tagged union for valid input types for build_electronic_structure_docs."""


@dataclass
class ESBuilderInput:
    """
    Container for electronic structure builder inputs that pairs
    a Variant tag with the corresponding input data.

    The variant field determines which construction path
    build_electronic_structure_docs will use to produce
    ElectronicStructureDoc instances.

    The data field holds a list of the appropriate input model
    (StructureInputs, BSInputs, DosInputs, or BSDosInputs) matching
    the chosen variant. Callers are responsible for populating this
    list within their own data pipeline context; helper functions
    such as ``obtain_blessed_dos`` and ``obtain_blessed_bs`` can assist
    in selecting the best candidate calculations for inclusion.
    """

    variant: Variant
    data: InputData


def variant_dispatch(func):
    """
    Slight remix to functools.singledispatch to perform dynamic
    dispatch based on the type of an enum variant for arg, rather
    than arg itself.

    Only usable with objects with a ``variant`` enum attr. See: ESBuilderInput
    """
    registry = {}

    def register(variant_value):
        def decorator(f):
            registry[variant_value] = f
            return f

        return decorator

    def wrapper(inputs):
        variant = inputs.variant
        return registry[variant](inputs)

    wrapper.register = register
    update_wrapper(wrapper, func)
    return wrapper


@variant_dispatch
def build_electronic_structure_docs(inputs: ESBuilderInput):
    """
    Generate electronic structure documents from tagged input data.

    Dispatches on the variant field of the provided ESBuilderInput to
    construct ElectronicStructureDoc instances via the appropriate
    factory method (from_structure, from_bs, from_dos, or from_bsdos).

    Caller is responsible for creating ESBuilderInput instances
    within their data pipeline context.

    Args:
        inputs: An ESBuilderInput whose variant selects the
            construction path and whose data contains the
            corresponding list of input documents to process.

    Returns:
        list[ElectronicStructureDoc]
    """
    ...


@build_electronic_structure_docs.register(Variant.STRUCTURE)
def _(inputs: ESBuilderInput):
    return list(
        filter(
            lambda y: y is not None,
            map(
                lambda x: try_call(
                    ElectronicStructureDoc.from_structure,
                    deprecated=x.deprecated,
                    material_id=x.material_id,
                    meta_structure=x.meta_structure,
                    origins=x.origins,
                    warnings=x.warnings,
                    band_gap=x.band_gap,
                    cbm=x.cbm,
                    vbm=x.vbm,
                    efermi=x.efermi,
                    is_gap_direct=x.is_gap_direct,
                    is_metal=x.is_metal,
                    magnetic_ordering=x.magnetic_ordering,
                ),
                inputs.data,
            ),
        )
    )


@build_electronic_structure_docs.register(Variant.BS)
def _(inputs: ESBuilderInput):
    return list(
        filter(
            lambda y: y is not None,
            map(
                lambda x: try_call(
                    ElectronicStructureDoc.from_bs,
                    bandstructures=x.bandstructures,
                    origins=x.origins,
                    structures=x.structures,
                    # from_structure(...) kwargs
                    deprecated=x.deprecated,
                    material_id=x.material_id,
                    meta_structure=x.meta_structure,
                ),
                inputs.data,
            ),
        )
    )


@build_electronic_structure_docs.register(Variant.DOS)
def _(inputs: ESBuilderInput):
    return list(
        filter(
            lambda y: y is not None,
            map(
                lambda x: try_call(
                    ElectronicStructureDoc.from_dos,
                    dos=x.dos,
                    is_gap_direct=x.is_gap_direct,
                    origins=x.origins,
                    structures=x.structures,
                    # from_structure(...) kwargs
                    deprecated=x.deprecated,
                    meta_structure=x.meta_structure,
                    material_id=x.material_id,
                ),
                inputs.data,
            ),
        )
    )


@build_electronic_structure_docs.register(Variant.BS_DOS)
def _(inputs: ESBuilderInput):
    return list(
        filter(
            lambda y: y is not None,
            map(
                lambda x: try_call(
                    ElectronicStructureDoc.from_bsdos,
                    bandstructures=x.bandstructures,
                    dos=x.dos,
                    origins=x.origins,
                    structures=x.structures,
                    # from_structure(...) kwargs
                    deprecated=x.deprecated,
                    material_id=x.material_id,
                    meta_structure=x.meta_structure,
                ),
                inputs.data,
            ),
        )
    )


# -----------------------------------------------------------------------------
# Helper funcs + types
# -----------------------------------------------------------------------------


class BaseCalcInfo(BaseModel):
    """Basic struct of metadata for use in sorting a list of candidate blessed calculations."""

    task_id: str
    is_hubbard: int
    lmaxmix: int
    nkpoints: int
    last_updated: datetime


class DosCalc(BaseCalcInfo):
    nedos: int


class BSCalc(BaseCalcInfo): ...


def obtain_blessed_dos(dos_calcs: list[DosCalc]) -> DosCalc:
    """
    Yields best dos calc from list of dos calcs.

    Helpful for preparing ``ESBuilderInput`` for ``build_electronic_structure_docs``
    """
    sorted_dos_data = sorted(
        dos_calcs,
        key=lambda entry: (
            entry.is_hubbard,
            entry.nkpoints,
            entry.nedos,
            entry.last_updated,
        ),
        reverse=True,
    )
    return sorted_dos_data[0]


def obtain_blessed_bs(bs_calcs: dict[str, list[BSCalc]]) -> dict[str, BSCalc]:
    """
    Yields map of best bs calc per path convention frommap of lists of
    bs calcs for each path convention.

    Helpful for preparing ``ESBuilderInput`` for ``build_electronic_structure_docs``
    """
    blessed_entries = {}
    bs_types = ["setyawan_curtarolo", "hinuma", "latimer_munro"]
    for bs_type in bs_types:
        if bs_calcs[bs_type]:
            sorted_bs_data = sorted(
                bs_calcs[bs_type],
                key=lambda entry: (
                    entry.is_hubbard,
                    entry.nkpoints,
                    entry.last_updated,
                ),
                reverse=True,
            )

            blessed_entries[bs_type] = sorted_bs_data[0]

    return blessed_entries
