""" Core definition of an Electronic Structure """
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from math import isnan
from typing import Dict, Type, TypeVar, Union

import numpy as np
from pydantic import BaseModel, Field
from pymatgen.analysis.magnetism.analyzer import (
    CollinearMagneticStructureAnalyzer,
    Ordering,
)
from pymatgen.core import Structure
from pymatgen.core.periodic_table import Element
from pymatgen.electronic_structure.bandstructure import BandStructureSymmLine
from pymatgen.electronic_structure.core import OrbitalType, Spin
from pymatgen.electronic_structure.dos import CompleteDos
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from pymatgen.symmetry.bandstructure import HighSymmKpath
from typing_extensions import Literal
from enum import Enum

from emmet.core.settings import EmmetSettings
from emmet.core.material_property import PropertyDoc
from emmet.core.mpid import MPID

SETTINGS = EmmetSettings()


class BSPathType(Enum):
    setyawan_curtarolo = "setyawan_curtarolo"
    hinuma = "hinuma"
    latimer_munro = "latimer_munro"


class DOSProjectionType(Enum):
    total = "total"
    elemental = "elemental"
    orbital = "orbital"


class BSObjectDoc(BaseModel):
    """
    Band object document.
    """

    task_id: MPID = Field(
        None, description="The calculation ID this property comes from"
    )

    last_updated: datetime = Field(
        description="The timestamp when this calculation was last updated",
        default_factory=datetime.utcnow,
    )

    data: Union[Dict, BandStructureSymmLine] = Field(
        None, description="The band structure object for the given calculation ID"
    )


class DOSObjectDoc(BaseModel):
    """
    DOS object document.
    """

    task_id: MPID = Field(
        None, description="The calculation ID this property comes from"
    )

    last_updated: datetime = Field(
        description="The timestamp when this calculation was last updated",
        default_factory=datetime.utcnow,
    )

    data: CompleteDos = Field(
        None, description="The density of states object for the given calculation ID"
    )


class ElectronicStructureBaseData(BaseModel):
    task_id: MPID = Field(
        ...,
        description="The source calculation (task) ID for the electronic structure data.",
    )

    band_gap: float = Field(..., description="Band gap energy in eV.")

    cbm: Union[float, Dict] = Field(None, description="Conduction band minimum data.")

    vbm: Union[float, Dict] = Field(None, description="Valence band maximum data.")

    efermi: float = Field(None, description="Fermi energy eV.")


class ElectronicStructureSummary(ElectronicStructureBaseData):
    is_gap_direct: bool = Field(..., description="Whether the band gap is direct.")

    is_metal: bool = Field(..., description="Whether the material is a metal.")

    magnetic_ordering: Union[str, Ordering] = Field(
        ..., description="Magnetic ordering of the calculation."
    )


class BandStructureSummaryData(ElectronicStructureSummary):
    nbands: float = Field(..., description="Number of bands.")

    equivalent_labels: Dict = Field(
        ..., description="Equivalent k-point labels in other k-path conventions."
    )

    direct_gap: float = Field(..., description="Direct gap energy in eV.")


class DosSummaryData(ElectronicStructureBaseData):
    spin_polarization: float = Field(
        None, description="Spin polarization at the fermi level."
    )


class BandstructureData(BaseModel):
    setyawan_curtarolo: BandStructureSummaryData = Field(
        None,
        description="Band structure summary data using the Setyawan-Curtarolo path convention.",
    )

    hinuma: BandStructureSummaryData = Field(
        None,
        description="Band structure summary data using the Hinuma et al. path convention.",
    )

    latimer_munro: BandStructureSummaryData = Field(
        None,
        description="Band structure summary data using the Latimer-Munro path convention.",
    )


class DosData(BaseModel):
    total: Dict[Union[Spin, str], DosSummaryData] = Field(
        None, description="Total DOS summary data."
    )

    elemental: Dict[
        Element,
        Dict[
            Union[Literal["total", "s", "p", "d", "f"], OrbitalType],
            Dict[Union[Literal["1", "-1"], Spin], DosSummaryData],
        ],
    ] = Field(
        None,
        description="Band structure summary data using the Hinuma et al. path convention.",
    )

    orbital: Dict[
        Union[Literal["total", "s", "p", "d", "f"], OrbitalType],
        Dict[Union[Literal["1", "-1"], Spin], DosSummaryData],
    ] = Field(
        None,
        description="Band structure summary data using the Latimer-Munro path convention.",
    )

    magnetic_ordering: Union[str, Ordering] = Field(
        None, description="Magnetic ordering of the calculation."
    )


T = TypeVar("T", bound="ElectronicStructureDoc")


class ElectronicStructureDoc(PropertyDoc, ElectronicStructureSummary):
    """
    Definition for a core Electronic Structure Document
    """

    property_name = "electronic_structure"

    bandstructure: BandstructureData = Field(
        None, description="Band structure data for the material."
    )

    dos: DosData = Field(None, description="Density of states data for the material.")

    last_updated: datetime = Field(
        description="Timestamp for when this document was last updated",
        default_factory=datetime.utcnow,
    )

    @classmethod
    def from_bsdos(  # type: ignore[override]
        cls: Type[T],
        material_id: MPID,
        dos: Dict[MPID, CompleteDos],
        is_gap_direct: bool,
        is_metal: bool,
        structures: Dict[MPID, Structure] = None,
        setyawan_curtarolo: Dict[MPID, BandStructureSymmLine] = None,
        hinuma: Dict[MPID, BandStructureSymmLine] = None,
        latimer_munro: Dict[MPID, BandStructureSymmLine] = None,
        **kwargs
    ) -> T:
        """
        Builds a electronic structure document using band structure and density of states data.

        Args:
            material_id (MPID): A material ID.
            dos (Dict[MPID, CompleteDos]): Dictionary mapping a calculation (task) ID to a CompleteDos object.
            is_gap_direct (bool): Direct gap indicator included at root level of document.
            is_metal (bool): Metallic indicator included at root level of document.
            structures (Dict[MPID, Structure]) = Dictionary mapping a calculation (task) ID to the structures used
                as inputs. This is to ensures correct magnetic moment information is included.
            setyawan_curtarolo (Dict[MPID, BandStructureSymmLine]): Dictionary mapping a calculation (task) ID to a
                BandStructureSymmLine object from a calculation run using the Setyawan-Curtarolo k-path convention.
            hinuma (Dict[MPID, BandStructureSymmLine]): Dictionary mapping a calculation (task) ID to a
                BandStructureSymmLine object from a calculation run using the Hinuma et al. k-path convention.
            latimer_munro (Dict[MPID, BandStructureSymmLine]): Dictionary mapping a calculation (task) ID to a
                BandStructureSymmLine object from a calculation run using the Latimer-Munro k-path convention.

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
                if isnan(spin_polarization):
                    spin_polarization = None
            except KeyError:
                spin_polarization = None

            dos_data["total"][spin] = DosSummaryData(
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

                dos_data["orbital"][orbital][spin] = DosSummaryData(
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

            for orbital in ["total"] + list(orb_dos.keys()):
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

                    dos_data["elemental"][ele][orbital][spin] = DosSummaryData(
                        task_id=dos_task,
                        band_gap=band_gap,
                        cbm=cbm,
                        vbm=vbm,
                        efermi=dos_efermi,
                        spin_polarization=spin_polarization,
                    )

        #  -- Process band structure data
        bs_data = {
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
                        bs.structure
                    ).ordering

                gap_dict = bs.get_band_gap()
                is_metal = bs.is_metal()
                direct_gap = bs.get_direct_band_gap()

                if is_metal:
                    band_gap = 0.0
                    cbm = None
                    vbm = None
                    is_gap_direct = False
                else:
                    band_gap = gap_dict["energy"]
                    cbm = bs.get_cbm()
                    vbm = bs.get_vbm()
                    is_gap_direct = gap_dict["direct"]

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
                            bs.structure
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

        bs_entry = BandstructureData(**bs_data)
        dos_entry = DosData(**dos_data)

        # Obtain summary data

        bs_gap = (
            bs_entry.setyawan_curtarolo.band_gap
            if bs_entry.setyawan_curtarolo is not None
            else None
        )
        dos_cbm, dos_vbm = dos_obj.get_cbm_vbm()
        dos_gap = max(dos_cbm - dos_vbm, 0.0)

        if bs_gap is not None and bs_gap <= dos_gap + 0.2:
            summary_task = bs_entry.setyawan_curtarolo.task_id
            summary_band_gap = bs_gap
            summary_cbm = (
                bs_entry.setyawan_curtarolo.cbm.get("energy", None)  # type: ignore
                if bs_entry.setyawan_curtarolo.cbm is not None
                else None
            )
            summary_vbm = (
                bs_entry.setyawan_curtarolo.vbm.get("energy", None)  # type: ignore
                if bs_entry.setyawan_curtarolo.cbm is not None
                else None
            )  # type: ignore
            summary_efermi = bs_entry.setyawan_curtarolo.efermi
            is_gap_direct = bs_entry.setyawan_curtarolo.is_gap_direct
            is_metal = bs_entry.setyawan_curtarolo.is_metal
            summary_magnetic_ordering = bs_entry.setyawan_curtarolo.magnetic_ordering
        else:
            summary_task = dos_entry.dict()["total"][Spin.up]["task_id"]
            summary_band_gap = dos_gap
            summary_cbm = dos_cbm
            summary_vbm = dos_vbm
            summary_efermi = dos_efermi
            summary_magnetic_ordering = dos_mag_ordering
            is_metal = True if np.isclose(dos_gap, 0.0, atol=0.01, rtol=0) else False

        return cls.from_structure(
            material_id=MPID(material_id),
            task_id=summary_task,
            meta_structure=structure,
            band_gap=summary_band_gap,
            cbm=summary_cbm,
            vbm=summary_vbm,
            efermi=summary_efermi,
            is_gap_direct=is_gap_direct,
            is_metal=is_metal,
            magnetic_ordering=summary_magnetic_ordering,
            bandstructure=bs_entry,
            dos=dos_entry,
            **kwargs
        )
