"""Core definition of an Electronic Structure"""

from __future__ import annotations

from collections import defaultdict
from math import isnan
from typing import TYPE_CHECKING, Annotated, Literal, TypeVar

import numpy as np
from pydantic import BaseModel, BeforeValidator, Field, WrapSerializer, field_validator
from pymatgen.analysis.magnetism.analyzer import (
    CollinearMagneticStructureAnalyzer,
    Ordering,
)
from pymatgen.core import Structure
from pymatgen.electronic_structure.bandstructure import BandStructureSymmLine
from pymatgen.electronic_structure.core import OrbitalType, Spin
from pymatgen.electronic_structure.dos import CompleteDos
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from pymatgen.symmetry.bandstructure import HighSymmKpath

from emmet.core.material_property import PropertyDoc
from emmet.core.mpid import AlphaID
from emmet.core.settings import EmmetSettings
from emmet.core.types.enums import ValueEnum
from emmet.core.types.pymatgen_types.bandstructure_symm_line_adapter import (
    BandStructureSymmLineType,
)
from emmet.core.types.pymatgen_types.dos_adapter import CompleteDosType
from emmet.core.types.pymatgen_types.element_adapter import ElementType
from emmet.core.types.typing import DateTimeType, IdentifierType, TypedBandDict

if TYPE_CHECKING:
    from typing_extensions import Self

SETTINGS = EmmetSettings()

OrderingType = Annotated[
    Ordering,
    BeforeValidator(lambda x: Ordering(x) if isinstance(x, str) else x),
    WrapSerializer(lambda x, nxt, info: x.value, return_type=str),
]


class BSPathType(ValueEnum):
    setyawan_curtarolo = "setyawan_curtarolo"
    hinuma = "hinuma"
    latimer_munro = "latimer_munro"


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
    task_id: IdentifierType = Field(
        ...,
        description="The source calculation (task) ID for the electronic structure data. "
        "This has the same form as a Materials Project ID.",
    )

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


class BandStructureSummaryData(ElectronicStructureSummary):
    equivalent_labels: dict[str, dict[str, dict[str, str]]] = Field(
        ..., description="Equivalent k-point labels in other k-path conventions."
    )

    nbands: float = Field(..., description="Number of bands.")
    direct_gap: float = Field(..., description="Direct gap energy in eV.")
    cbm: TypedBandDict | None = Field(None, description="Conduction band minimum data.")
    vbm: TypedBandDict | None = Field(None, description="Valence band maximum data.")

    @field_validator("cbm", "vbm", mode="before")
    def deserialize_bands(cls, band):
        if band:
            if isinstance(band["kpoint"], dict) and "label" not in band["kpoint"]:
                band["kpoint"]["label"] = None
        return band

    @field_validator("equivalent_labels", mode="before")
    def deserialize_labels(cls, equivalent_labels):
        if isinstance(next(iter(equivalent_labels.values())), list):
            equivalent_labels = {
                convention: {
                    other_convention: {k: v for k, v in label_tuples}
                    for other_convention, label_tuples in other_mapping
                }
                for convention, other_mapping in equivalent_labels.items()
            }
        return equivalent_labels


class DosSummaryData(ElectronicStructureBaseData):
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


class DosData(BaseModel):
    total: dict[SpinType, DosSummaryData] | None = Field(
        None, description="Total DOS summary data."
    )

    elemental: (
        dict[
            ElementType,
            dict[Literal["s", "p", "d", "f", "total"], dict[SpinType, DosSummaryData]],
        ]
        | None
    ) = Field(
        None,
        description="Band structure summary data using the Hinuma et al. path convention.",
    )

    orbital: (
        dict[Literal["s", "p", "d", "f", "total"], dict[SpinType, DosSummaryData]]
        | None
    ) = Field(
        None,
        description="Band structure summary data using the Latimer-Munro path convention.",
    )

    magnetic_ordering: OrderingType | None = Field(
        None, description="Magnetic ordering of the calculation."
    )

    @field_validator("elemental", mode="before")
    def elemental_deserializer(cls, elemental):
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

    @field_validator("orbital", mode="before")
    def oribital_deserializer(cls, orbital):
        if isinstance(next(iter(orbital.values())), list):
            orbital = {
                oribital_type: {
                    spin: summary_data for spin, summary_data in spin_summary_pairs
                }
                for oribital_type, spin_summary_pairs in orbital.items()
            }

        return orbital


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
    def from_bsdos(  # type: ignore[override]
        cls,
        dos: dict[IdentifierType, CompleteDos],
        is_gap_direct: bool,
        is_metal: bool,
        material_id: IdentifierType | None = None,
        origins: list[dict] = [],
        structures: dict[IdentifierType, Structure] | None = None,
        setyawan_curtarolo: dict[IdentifierType, BandStructureSymmLine] | None = None,
        hinuma: dict[IdentifierType, BandStructureSymmLine] | None = None,
        latimer_munro: dict[IdentifierType, BandStructureSymmLine] | None = None,
        **kwargs,
    ) -> Self:
        """
        Builds a electronic structure document using band structure and density of states data.

        Args:
            material_id (AlphaID or MPID): A material ID.
            dos (dict[AlphaID or MPID, CompleteDos]): Dictionary mapping a calculation (task) ID to a CompleteDos object.
            is_gap_direct (bool): Direct gap indicator included at root level of document.
            is_metal (bool): Metallic indicator included at root level of document.
            structures (dict[AlphaID or MPID, Structure]) = Dictionary mapping a calculation (task) ID to the structures used
                as inputs. This is to ensures correct magnetic moment information is included.
            setyawan_curtarolo (dict[AlphaID or MPID, BandStructureSymmLine]): Dictionary mapping a calculation (task) ID to a
                BandStructureSymmLine object from a calculation run using the Setyawan-Curtarolo k-path convention.
            hinuma (dict[AlphaID or MPID, BandStructureSymmLine]): Dictionary mapping a calculation (task) ID to a
                BandStructureSymmLine object from a calculation run using the Hinuma et al. k-path convention.
            latimer_munro (dict[AlphaID or MPID, BandStructureSymmLine]): Dictionary mapping a calculation (task) ID to a
                BandStructureSymmLine object from a calculation run using the Latimer-Munro k-path convention.
            origins (list[dict]): Optional origins information for final doc

        """

        # -- Process density of states data

        dos_task, dos_obj = list(dos.items())[0]

        orbitals = [OrbitalType.s, OrbitalType.p, OrbitalType.d]
        spins = list(dos_obj.densities.keys())

        ele_dos = dos_obj.get_element_dos()
        tot_orb_dos = dos_obj.get_spd_dos()

        elements = ele_dos.keys()

        dos_efermi = dos_obj.efermi

        is_gap_direct = is_gap_direct
        is_metal = is_metal

        structure = dos_obj.structure

        if structures is not None and structures[dos_task]:
            structure = structures[dos_task]

        dos_mag_ordering = CollinearMagneticStructureAnalyzer(structure).ordering

        dos_data = {
            "total": defaultdict(dict),
            "elemental": {element: defaultdict(dict) for element in elements},
            "orbital": defaultdict(dict),
            "magnetic_ordering": dos_mag_ordering,
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
                task_id=dos_task,
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
                    task_id=dos_task,
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
                        task_id=dos_task,
                        band_gap=band_gap,
                        cbm=cbm,
                        vbm=vbm,
                        efermi=dos_efermi,
                        spin_polarization=spin_polarization,
                    )

        #  -- Process band structure data
        bs_data = {  # type: ignore
            "setyawan_curtarolo": setyawan_curtarolo,
            "hinuma": hinuma,
            "latimer_munro": latimer_munro,
        }

        for bs_type, bs_input in bs_data.items():
            if bs_input is not None:
                bs_task, bs = list(bs_input.items())[0]

                if structures is not None and structures[bs_task]:
                    bs_mag_ordering = CollinearMagneticStructureAnalyzer(
                        structures[bs_task]
                    ).ordering
                else:
                    bs_mag_ordering = CollinearMagneticStructureAnalyzer(
                        bs.structure  # type: ignore[arg-type]
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

                # - Get equivalent labels between different conventions
                hskp = HighSymmKpath(
                    bs.structure,
                    path_type="all",
                    symprec=0.1,
                    angle_tolerance=5,
                    atol=1e-5,
                )
                equivalent_labels = hskp.equiv_labels

                if bs_type == "latimer_munro":
                    gen_labels = set(
                        [
                            label
                            for label in equivalent_labels["latimer_munro"][
                                "setyawan_curtarolo"
                            ]
                        ]
                    )
                    kpath_labels = set(
                        [
                            kpoint.label
                            for kpoint in bs.kpoints
                            if kpoint.label is not None
                        ]
                    )

                    if not gen_labels.issubset(kpath_labels):
                        new_structure = SpacegroupAnalyzer(
                            bs.structure  # type: ignore[arg-type]
                        ).get_primitive_standard_structure(
                            international_monoclinic=False
                        )

                        hskp = HighSymmKpath(
                            new_structure,
                            path_type="all",
                            symprec=SETTINGS.SYMPREC,
                            angle_tolerance=SETTINGS.ANGLE_TOL,
                            atol=1e-5,
                        )
                        equivalent_labels = hskp.equiv_labels

                bs_data[bs_type] = BandStructureSummaryData(  # type: ignore
                    task_id=bs_task,
                    band_gap=band_gap,
                    direct_gap=direct_gap,
                    cbm=cbm,
                    vbm=vbm,
                    is_gap_direct=is_gap_direct,
                    is_metal=is_metal,
                    efermi=bs_efermi,
                    nbands=nbands,
                    equivalent_labels=equivalent_labels,
                    magnetic_ordering=bs_mag_ordering,
                )

        bs_entry = BandstructureData(**bs_data)  # type: ignore
        dos_entry = DosData(**dos_data)  # type: ignore[arg-type]

        # Obtain summary data

        bs_gap = (
            bs_entry.setyawan_curtarolo.band_gap
            if bs_entry.setyawan_curtarolo is not None
            else None
        )
        dos_cbm, dos_vbm = dos_obj.get_cbm_vbm()
        dos_gap = max(dos_cbm - dos_vbm, 0.0)

        new_origin_last_updated = None
        new_origin_task_id = None

        if bs_gap is not None and bs_gap <= dos_gap + 0.2:
            summary_task = bs_entry.setyawan_curtarolo.task_id  # type: ignore
            summary_band_gap = bs_gap
            summary_cbm = (
                bs_entry.setyawan_curtarolo.cbm.get("energy", None)  # type: ignore
                if bs_entry.setyawan_curtarolo.cbm is not None  # type: ignore
                else None
            )
            summary_vbm = (
                bs_entry.setyawan_curtarolo.vbm.get("energy", None)  # type: ignore
                if bs_entry.setyawan_curtarolo.cbm is not None  # type: ignore
                else None
            )  # type: ignore
            summary_efermi = bs_entry.setyawan_curtarolo.efermi  # type: ignore
            is_gap_direct = bs_entry.setyawan_curtarolo.is_gap_direct  # type: ignore
            is_metal = bs_entry.setyawan_curtarolo.is_metal  # type: ignore

            for origin in origins:
                if origin["name"] == "setyawan_curtarolo":
                    new_origin_last_updated = origin["last_updated"]
                    new_origin_task_id = origin["task_id"]

        else:
            summary_task = dos_entry.model_dump()["total"][str(Spin.up)]["task_id"]
            summary_band_gap = dos_gap
            summary_cbm = dos_cbm
            summary_vbm = dos_vbm
            summary_efermi = dos_efermi
            is_metal = True if np.isclose(dos_gap, 0.0, atol=0.01, rtol=0) else False

            for origin in origins:
                if origin["name"] == "dos":
                    new_origin_last_updated = origin["last_updated"]
                    new_origin_task_id = origin["task_id"]

        if new_origin_task_id is not None:
            for origin in origins:
                if origin["name"] == "electronic_structure":
                    origin["last_updated"] = new_origin_last_updated
                    origin["task_id"] = new_origin_task_id

        summary_magnetic_ordering = CollinearMagneticStructureAnalyzer(
            kwargs["meta_structure"],
            round_magmoms=True,
            threshold_nonmag=0.2,
            threshold=0,
        ).ordering

        return cls.from_structure(
            material_id=AlphaID(material_id),
            task_id=summary_task,
            band_gap=summary_band_gap,
            cbm=summary_cbm,
            vbm=summary_vbm,
            efermi=summary_efermi,
            is_gap_direct=is_gap_direct,
            is_metal=is_metal,
            magnetic_ordering=summary_magnetic_ordering,
            bandstructure=bs_entry,
            dos=dos_entry,
            **kwargs,
        )
