"""Core definition of an Electronic Structure"""

from __future__ import annotations

from collections import defaultdict
from math import isnan
from typing import TYPE_CHECKING, Annotated, Literal, TypeVar

import numpy as np
from pydantic import BaseModel, BeforeValidator, Field, WrapSerializer
from pymatgen.analysis.magnetism.analyzer import (
    CollinearMagneticStructureAnalyzer,
    Ordering,
)
from pymatgen.electronic_structure.bandstructure import BandStructureSymmLine
from pymatgen.electronic_structure.core import OrbitalType, Spin
from pymatgen.io.vasp.sets import MPStaticSet
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

from emmet.core.material import PropertyOrigin
from emmet.core.material_property import PropertyDoc
from emmet.core.settings import EmmetSettings
from emmet.core.types.enums import ValueEnum
from emmet.core.types.pymatgen_types.bandstructure_symm_line_adapter import (
    BandStructureSymmLineType,
    TypedBandDict,
)
from emmet.core.types.pymatgen_types.dos_adapter import CompleteDosType
from emmet.core.types.pymatgen_types.element_adapter import ElementType
from emmet.core.types.typing import DateTimeType, IdentifierType

if TYPE_CHECKING:
    from typing import Any

    from pymatgen.core import Structure
    from typing_extensions import Self

    from emmet.core.types.electronic_structure import BSShim, DosShim

SETTINGS = EmmetSettings()

OrderingType = Annotated[
    Ordering,
    BeforeValidator(lambda x: Ordering(x) if isinstance(x, str) else x),
    WrapSerializer(lambda x, nxt, info: x.value, return_type=str),
]


class DOSProjectionType(ValueEnum):
    total = "total"
    elemental = "elemental"
    orbital = "orbital"


class BSObjectDoc(BaseModel):
    """
    Band object document.
    """

    task_id: IdentifierType | None = Field(
        None,
        description="The source calculation (task) ID that this band structure comes from. "
        "This has the same form as a Materials Project ID.",
    )

    last_updated: DateTimeType = Field(
        description="The timestamp when this calculation was last updated",
    )

    data: BandStructureSymmLineType | None = Field(
        None, description="The band structure object for the given calculation ID"
    )


class DOSObjectDoc(BaseModel):
    """
    DOS object document.
    """

    task_id: IdentifierType | None = Field(
        None,
        description="The source calculation (task) ID that this density of states comes from. "
        "This has the same form as a Materials Project ID.",
    )

    last_updated: DateTimeType = Field(
        description="The timestamp when this calculation was last updated.",
    )

    data: CompleteDosType | None = Field(
        None, description="The density of states object for the given calculation ID."
    )


class ElectronicStructureBaseData(BaseModel):
    band_gap: float = Field(..., description="Band gap energy in eV.")
    cbm: float | None = Field(None, description="Conduction band minimum data.")
    vbm: float | None = Field(None, description="Valence band maximum data.")
    efermi: float | None = Field(None, description="Fermi energy in eV.")


class ElectronicStructureSummary(ElectronicStructureBaseData):
    is_gap_direct: bool = Field(..., description="Whether the band gap is direct.")
    is_metal: bool = Field(..., description="Whether the material is a metal.")
    magnetic_ordering: OrderingType = Field(
        ..., description="Magnetic ordering of the calculation."
    )


def _deser_cbm_vbm(band: Any) -> TypedBandDict:
    """Validate annotated CBM and VBM dicts."""
    if (
        isinstance(band, dict)
        and isinstance(band.get("kpoint"), dict)
        and "label" not in band["kpoint"]
    ):
        band["kpoint"]["label"] = None
    return band


class BandStructureSummaryData(ElectronicStructureSummary):
    """Schematize high-level band structure data for the API."""

    task_id: IdentifierType | None = Field(
        None,
        description="The source calculation (task) ID that this band structure comes from.",
    )
    nbands: float = Field(..., description="Number of bands.")
    direct_gap: float = Field(..., description="Direct gap energy in eV.")
    cbm: Annotated[TypedBandDict | None, BeforeValidator(_deser_cbm_vbm)] | None = (
        Field(None, description="Conduction band minimum data.")
    )
    vbm: Annotated[TypedBandDict | None, BeforeValidator(_deser_cbm_vbm)] | None = (
        Field(None, description="Valence band maximum data.")
    )


class DosSummaryData(ElectronicStructureBaseData):
    """Schematize high-level DOS data for the API."""

    spin_polarization: float | None = Field(
        None, description="Spin polarization at the fermi level."
    )


class BandstructureData(BaseModel):
    setyawan_curtarolo: BandStructureSummaryData | None = Field(
        None,
        description="Band structure summary data using the Setyawan-Curtarolo path convention.",
    )

    hinuma: BandStructureSummaryData | None = Field(
        None,
        description="Band structure summary data using the Hinuma et al. path convention.",
    )

    latimer_munro: BandStructureSummaryData | None = Field(
        None,
        description="Band structure summary data using the Latimer-Munro path convention.",
    )


SpinTypeVar = TypeVar("SpinTypeVar", Spin, Literal["1", "-1"])

SpinType = Annotated[
    SpinTypeVar,
    BeforeValidator(lambda x: Spin(int(x)) if isinstance(x, str) else x),
    WrapSerializer(lambda x, nxt, info: str(x), return_type=str),
]


def _deser_elemental(
    elemental: dict,
) -> dict[str, dict[str, dict[str, DosSummaryData]]]:
    """Validate DosData.elemental field."""
    if isinstance(next(iter(elemental.values())), list):
        elemental = {
            element: {
                oribital_type: {
                    spin: summary_data for spin, summary_data in spin_summary_pairs
                }
                for oribital_type, spin_summary_pairs in orbital
            }
            for element, orbital in elemental.items()
        }

    return elemental


def _deser_orbital(orbital):
    """Validate DosData.orbital field."""
    if isinstance(next(iter(orbital.values())), list):
        orbital = {
            oribital_type: {
                spin: summary_data for spin, summary_data in spin_summary_pairs
            }
            for oribital_type, spin_summary_pairs in orbital.items()
        }

    return orbital


class DosData(BaseModel):
    task_id: IdentifierType | None = Field(
        None,
        description="The source calculation (task) ID that this density of states comes from.",
    )
    total: dict[SpinType, DosSummaryData] | None = Field(
        None, description="Total DOS summary data."
    )

    elemental: Annotated[
        dict[
            ElementType,
            dict[Literal["s", "p", "d", "f", "total"], dict[SpinType, DosSummaryData]],
        ]
        | None,
        BeforeValidator(_deser_elemental),
    ] = Field(
        None,
        description="Band structure summary data using the Hinuma et al. path convention.",
    )

    orbital: Annotated[
        dict[Literal["s", "p", "d", "f", "total"], dict[SpinType, DosSummaryData]]
        | None,
        BeforeValidator(_deser_orbital),
    ] = Field(
        None,
        description="Band structure summary data using the Latimer-Munro path convention.",
    )

    magnetic_ordering: OrderingType | None = Field(
        None, description="Magnetic ordering of the calculation."
    )


class ElectronicStructureDoc(PropertyDoc, ElectronicStructureSummary):
    """
    Definition for a core Electronic Structure Document
    """

    property_name: str = "electronic_structure"

    bandstructure: BandstructureData | None = Field(
        None, description="Band structure data for the material."
    )

    dos: DosData | None = Field(
        None, description="Density of states data for the material."
    )

    @classmethod
    def from_bs(
        cls,
        bandstructures: BSShim,
        origins: list[PropertyOrigin],
        structures: dict[IdentifierType, Structure],
        **kwargs,
    ) -> Self:
        """
        Builds an electronic structure document using band structure data.

        Args:
            bandstructures (BSShim): Struct of bandstructures with identifiers.
            origins (list[PropertyOrigin]): Optional origins information for final doc.
            structures (dict[AlphaID or MPID, Structure]) = Dictionary mapping a calculation (task) ID to the
                structures used as inputs. This is to ensures correct magnetic moment information is included.
            material_id (AlphaID or MPID): A material ID.

        """
        bs_data = _generate_bs_data(bandstructures, origins, structures)
        origins = [origin for origin in origins] + [bs_data["es_origins_from_bs"]]

        return bs_checks(
            cls.from_structure(
                band_gap=bs_data["band_gap"],
                cbm=bs_data["cbm"],
                vbm=bs_data["vbm"],
                efermi=bs_data["efermi"],
                is_gap_direct=bs_data["is_gap_direct"],
                is_metal=bs_data["is_metal"],
                magnetic_ordering=bs_data["bs_magnetic_ordering"],
                bandstructure=bs_data["bandstructure"],
                origins=origins,
                **kwargs,
            ),
            structures,
            bandstructures,
        )

    @classmethod
    def from_dos(
        cls,
        dos: DosShim,
        is_gap_direct: bool,
        origins: list[PropertyOrigin],
        structures: dict[IdentifierType, Structure],
        **kwargs,
    ) -> Self:
        """
        Builds an electronic structure document using density of states data.

        Args:
            dos (DosShim): Struct with a CompleteDos and identifier.
            is_gap_direct (bool): Direct gap indicator included at root level of document, result of VASP outputs.
            origins (list[PropertyOrigin]): Origins information for final doc.
            structures (dict[AlphaID or MPID, Structure]) = Dictionary mapping a calculation (task) ID to the
                structures used as inputs. This is to ensures correct magnetic moment information is included.
            material_id (AlphaID or MPID): A material ID.

        """
        dos_data = _generate_dos_data(dos, origins, structures)
        origins = [origin for origin in origins] + [dos_data["es_origins_from_dos"]]

        return dos_checks(
            cls.from_structure(
                band_gap=dos_data["band_gap"],
                cbm=dos_data["cbm"],
                vbm=dos_data["vbm"],
                efermi=dos_data["efermi"],
                is_gap_direct=is_gap_direct,
                is_metal=dos_data["is_metal"],
                magnetic_ordering=dos_data["dos_magnetic_ordering"],
                dos=dos_data["dos_entry"],
                origins=origins,
                **kwargs,
            ),
            structures,
            dos,
        )

    @classmethod
    def from_bsdos(
        cls,
        bandstructures: BSShim,
        dos: DosShim,
        origins: list[PropertyOrigin],
        structures: dict[IdentifierType, Structure],
        **kwargs,
    ) -> Self:
        """
        Builds an electronic structure document using band structure and density of states data.

        Args:
            bandstructures (BSShim): Struct of bandstructures with identifiers.
            dos (DosShim): Struct with a CompleteDos and identifier.
            origins (list[PropertyOrigin]): Origins information for final doc.
            structures (dict[AlphaID or MPID, Structure]) = Dictionary mapping a calculation (task) ID to the
                structures used as inputs. This is to ensures correct magnetic moment information is included.
            material_id (AlphaID or MPID): A material ID.

        """
        bs_data = _generate_bs_data(bandstructures, origins, structures)
        dos_data = _generate_dos_data(dos, origins, structures)

        # TODO: add ability to add blessed structure from material into ranking
        #       for es origins, i.e., r2SCAN static/relax > GGA NSCF line > ...
        origins = [origin for origin in origins] + [bs_data["es_origins_from_bs"]]
        magnetic_ordering = bs_data["bs_magnetic_ordering"]

        return bsdos_checks(
            cls.from_structure(
                band_gap=bs_data["band_gap"],
                cbm=bs_data["cbm"],
                vbm=bs_data["vbm"],
                efermi=bs_data["efermi"],
                is_gap_direct=bs_data["is_gap_direct"],
                is_metal=bs_data["is_metal"],
                magnetic_ordering=magnetic_ordering,
                bandstructure=bs_data["bandstructure"],
                dos=dos_data["dos_entry"],
                origins=origins,
                **kwargs,
            ),
            structures,
            bandstructures,
            dos,
        )


def _generate_bs_data(
    bandstructures: BSShim,
    origins: list[PropertyOrigin],
    structures: dict[IdentifierType, Structure],
) -> dict:
    bs_data = {  # type: ignore
        "setyawan_curtarolo": bandstructures.setyawan_curtarolo,
        "hinuma": bandstructures.hinuma,
        "latimer_munro": bandstructures.latimer_munro,
    }

    bs_type: str
    bs_input: tuple[IdentifierType, BandStructureSymmLine, int]
    bs_task_id: IdentifierType
    bs: BandStructureSymmLine

    for bs_type, bs_input in bs_data.items():
        if bs_input is not None:
            bs_task_id, bs, _ = bs_input
            bs_mag_ordering = CollinearMagneticStructureAnalyzer(
                structures[bs_task_id]
            ).ordering

            gap_dict = bs.get_band_gap()
            is_metal = bs.is_metal()
            direct_gap = bs.get_direct_band_gap()

            if is_metal:
                band_gap = 0.0
                cbm = None  # type: ignore[assignment]
                vbm = None  # type: ignore[assignment]
                is_gap_direct = False
            else:
                band_gap = gap_dict["energy"]
                cbm = bs.get_cbm()  # type: ignore[assignment]
                vbm = bs.get_vbm()  # type: ignore[assignment]
                is_gap_direct = gap_dict["direct"]

                # coerce type here, mixture of str and int types in bs objects
                cbm["kpoint_index"] = [int(x) for x in cbm["kpoint_index"]]  # type: ignore[index]
                vbm["kpoint_index"] = [int(x) for x in vbm["kpoint_index"]]  # type: ignore[index]

            bs_efermi = bs.efermi
            nbands = bs.nb_bands

            bs_data[bs_type] = BandStructureSummaryData(  # type: ignore
                task_id=bs_task_id,
                band_gap=band_gap,
                direct_gap=direct_gap,
                cbm=cbm,
                vbm=vbm,
                is_gap_direct=is_gap_direct,
                is_metal=is_metal,
                efermi=bs_efermi,
                nbands=nbands,
                magnetic_ordering=bs_mag_ordering,
            )

    def _bs_eval(
        bs_data: dict[str, BandStructureSymmLine | None],
        bs_rank: list[str] = ["latimer_munro", "hinuma", "setyawan_curtarolo"],
    ) -> str:
        for bs_type in bs_rank:
            if bs_data[bs_type] is not None:
                yield bs_type

    blessed_bs_key = next(_bs_eval(bs_data))

    bs_entry = BandstructureData(**bs_data)  # type: ignore
    band_gap = getattr(bs_entry, blessed_bs_key).band_gap
    cbm = (getattr(bs_entry, blessed_bs_key).cbm or {}).get("energy", None)  # type: ignore
    vbm = (getattr(bs_entry, blessed_bs_key).vbm or {}).get("energy", None)  # type: ignore
    efermi = getattr(bs_entry, blessed_bs_key).efermi  # type: ignore
    is_gap_direct = getattr(bs_entry, blessed_bs_key).is_gap_direct  # type: ignore
    is_metal = getattr(bs_entry, blessed_bs_key).is_metal  # type: ignore

    es_origins_from_bs = None
    for origin in origins:
        if origin.name == blessed_bs_key:
            es_origins_from_bs = PropertyOrigin(
                name="electronic_structure",
                last_updated=origin.last_updated,
                task_id=origin.task_id,
            )

    bs_magnetic_ordering = CollinearMagneticStructureAnalyzer(
        structures[es_origins_from_bs.task_id],
        round_magmoms=True,
        threshold_nonmag=0.2,
        threshold=0,
    ).ordering

    return {
        "band_gap": band_gap,
        "cbm": cbm,
        "vbm": vbm,
        "efermi": efermi,
        "is_gap_direct": is_gap_direct,
        "is_metal": is_metal,
        "bs_magnetic_ordering": bs_magnetic_ordering,
        "bandstructure": bs_entry,
        "es_origins_from_bs": es_origins_from_bs,
    }


def _generate_dos_data(
    dos: DosShim,
    origins: list[PropertyOrigin],
    structures: dict[IdentifierType, Structure],
) -> dict:
    dos_task, dos_obj, _ = dos.dos

    orbitals = [OrbitalType.s, OrbitalType.p, OrbitalType.d]
    spins = list(dos_obj.densities.keys())

    ele_dos = dos_obj.get_element_dos()
    tot_orb_dos = dos_obj.get_spd_dos()

    elements = ele_dos.keys()

    dos_efermi = dos_obj.efermi
    structure = structures[dos_task]

    dos_magnetic_ordering = CollinearMagneticStructureAnalyzer(structure).ordering

    dos_data = {
        "task_id": dos_task,
        "total": defaultdict(dict),
        "elemental": {element: defaultdict(dict) for element in elements},
        "orbital": defaultdict(dict),
        "magnetic_ordering": dos_magnetic_ordering,
    }

    for spin in spins:
        # - Process total DOS data
        band_gap = dos_obj.get_gap(spin=spin)
        (cbm, vbm) = dos_obj.get_cbm_vbm(spin=spin)

        try:
            spin_polarization = dos_obj.spin_polarization
            if spin_polarization is None or isnan(spin_polarization):
                spin_polarization = None
        except KeyError:
            spin_polarization = None

        dos_data["total"][spin] = DosSummaryData(  # type: ignore[index]
            band_gap=band_gap,
            cbm=cbm,
            vbm=vbm,
            efermi=dos_efermi,
            spin_polarization=spin_polarization,
        )

        # - Process total orbital projection data
        for orbital in orbitals:
            band_gap = tot_orb_dos[orbital].get_gap(spin=spin)

            (cbm, vbm) = tot_orb_dos[orbital].get_cbm_vbm(spin=spin)

            spin_polarization = None

            dos_data["orbital"][str(orbital)][spin] = DosSummaryData(  # type: ignore[index]
                band_gap=band_gap,
                cbm=cbm,
                vbm=vbm,
                efermi=dos_efermi,
                spin_polarization=spin_polarization,
            )

    # - Process element and element orbital projection data
    for ele in ele_dos:
        orb_dos = dos_obj.get_element_spd_dos(ele)

        for orbital in ["total"] + list(orb_dos.keys()):  # type: ignore[assignment]
            if orbital == "total":
                proj_dos = ele_dos
                label = ele
            else:
                proj_dos = orb_dos
                label = orbital

            for spin in spins:
                band_gap = proj_dos[label].get_gap(spin=spin)
                (cbm, vbm) = proj_dos[label].get_cbm_vbm(spin=spin)

                spin_polarization = None

                dos_data["elemental"][ele][str(orbital)][spin] = DosSummaryData(  # type: ignore[index]
                    band_gap=band_gap,
                    cbm=cbm,
                    vbm=vbm,
                    efermi=dos_efermi,
                    spin_polarization=spin_polarization,
                )

    dos_entry = DosData(**dos_data)  # type: ignore[arg-type]

    dos_cbm, dos_vbm = dos_obj.get_cbm_vbm()
    dos_gap = max(dos_cbm - dos_vbm, 0.0)

    is_metal = True if np.isclose(dos_gap, 0.0, atol=0.01, rtol=0) else False

    es_origins_from_dos = None
    for origin in origins:
        if origin.task_id == dos_task:
            es_origins_from_dos = PropertyOrigin(
                name="electronic_structure",
                last_updated=origin.last_updated,
                task_id=dos_task,
            )

    return {
        "band_gap": dos_gap,
        "cbm": dos_cbm,
        "vbm": dos_vbm,
        "efermi": dos_efermi,
        "is_metal": is_metal,
        "dos_magnetic_ordering": dos_magnetic_ordering,
        "es_origins_from_dos": es_origins_from_dos,
        "dos_entry": dos_entry,
    }


def bs_checks(
    doc: ElectronicStructureDoc,
    structures: dict[str, Structure],
    bandstructures: BSShim,
    skip_primitive_check: bool = False,
) -> ElectronicStructureDoc:
    for _, bs_summary in doc.bandstructure:
        if bs_summary is not None:
            _bandgap_diff_check(doc, bs_summary.band_gap, bs_summary.task_id)

    mag_orderings: list[tuple[str, Ordering]] = [
        (bs_summary.task_id, bs_summary.magnetic_ordering)
        for _, bs_summary in doc.bandstructure
        if bs_summary is not None
    ]

    _magnetic_ordering_check(doc, mag_orderings)

    if not skip_primitive_check:
        _structure_primitive_checks(doc, structures)

    for _, bandstructure in bandstructures:
        if bandstructure is not None:
            task_id, _, lmaxmix = bandstructure
            _lmaxmix_check(doc, structures[task_id], lmaxmix, task_id)

    return doc


def dos_checks(
    doc: ElectronicStructureDoc,
    structures: dict[str, Structure],
    dos: DosShim,
    skip_primitive_check: bool = False,
) -> ElectronicStructureDoc:
    _bandgap_diff_check(
        doc,
        doc.dos.total[Spin.up].band_gap,
        doc.dos.task_id,
    )

    mag_orderings: list[tuple[str, Ordering]] = [
        (
            doc.dos.task_id,
            doc.dos.magnetic_ordering,
        )
    ]

    _magnetic_ordering_check(doc, mag_orderings)

    if not skip_primitive_check:
        _structure_primitive_checks(doc, structures)

    task_id, dos_obj, lmaxmix = dos.dos
    _lmaxmix_check(doc, structures[task_id], lmaxmix, doc.dos.task_id)

    return doc


def bsdos_checks(
    doc: ElectronicStructureDoc,
    structures: dict[str, Structure],
    bandstructures: BSShim,
    dos: DosShim,
) -> ElectronicStructureDoc:
    _structure_primitive_checks(doc, structures)
    return dos_checks(
        bs_checks(
            doc,
            structures,
            bandstructures,
            skip_primitive_check=True,
        ),
        structures,
        dos,
        skip_primitive_check=True,
    )


def _bandgap_diff_check(
    doc: ElectronicStructureDoc, band_gap: float, task_id: IdentifierType
) -> None:
    if abs(doc.band_gap - band_gap) > 0.25:
        doc.warnings.append(
            "Absolute difference between blessed band gap and the band gap for"
            f"task {str(task_id)} is larger than 0.25 eV.",
        )


def _magnetic_ordering_check(
    doc: ElectronicStructureDoc, mag_orderings: list[tuple[IdentifierType, Ordering]]
) -> None:
    for task_id, ordering in mag_orderings:
        if doc.magnetic_ordering != ordering:
            doc.warnings.append(
                f"Summary data magnetic ordering does not agree with the ordering from {str(task_id)}"
            )


def _lmaxmix_check(
    doc: ElectronicStructureDoc,
    structure: Structure,
    lmaxmix: int,
    task_id: IdentifierType,
) -> None:
    # VASP default LMAXMIX is 2
    expected_lmaxmix = MPStaticSet(structure).incar.get("LMAXMIX", 2)
    if lmaxmix != expected_lmaxmix:
        doc.warnings.append(
            "An incorrect calculation parameter may lead to errors in the band gap of "
            f"0.1-0.2 eV (LMAXIX is {lmaxmix} and should be {expected_lmaxmix} for "
            f"{str(task_id)})."
        )


def _structure_primitive_checks(
    doc: ElectronicStructureDoc, structures: dict[IdentifierType, Structure]
) -> None:
    for task_id, struct in structures.items():
        struct_prim = SpacegroupAnalyzer(struct).get_primitive_standard_structure(
            international_monoclinic=False
        )

        if not np.allclose(
            struct.lattice.matrix, struct_prim.lattice.matrix, atol=1e-3
        ):
            if np.isclose(struct_prim.volume, struct.volume, atol=5, rtol=0):
                doc.warnings.append(
                    f"The input structure for {str(task_id)} is primitive but may not exactly match the "
                    f"standard primitive setting."
                )
            else:
                doc.warnings.append(
                    f"The input structure for {str(task_id)} does not match the expected standard primitive"
                )
