""" Core definition of an Electronic Structure """
from __future__ import annotations
from collections import defaultdict

from datetime import datetime
from typing import Dict, Type, TypeVar, Union

from pydantic import BaseModel, Field
from pymatgen.core import Structure

from emmet.core.mpid import MPID
from emmet.core.material_property import PropertyDoc
from emmet.core import SETTINGS

from pymatgen.core.periodic_table import Element
from pymatgen.electronic_structure.bandstructure import BandStructureSymmLine
from pymatgen.electronic_structure.core import OrbitalType, Spin
from pymatgen.electronic_structure.dos import CompleteDos
from pymatgen.symmetry.bandstructure import HighSymmKpath
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from pymatgen.analysis.magnetism.analyzer import (
    CollinearMagneticStructureAnalyzer,
    Ordering,
)


class ElectronicStructureBaseData(BaseModel):
    calc_id: Union[MPID, int] = Field(
        ..., description="The source calculation ID for the electronic structure data."
    )

    band_gap: float = Field(
        ..., description="Band gap energy in eV.",
    )

    cbm: Union[float, Dict] = Field(
        None, description="Conduction band minimum data.",
    )

    vbm: Union[float, Dict] = Field(
        None, description="Valence band maximum data.",
    )

    efermi: float = Field(
        ..., description="Fermi energy eV.",
    )


class ElectronicStructureSummary(ElectronicStructureBaseData):
    is_gap_direct: bool = Field(
        ..., description="Whether the band gap is direct.",
    )

    is_metal: bool = Field(
        ..., description="Whether the material is a metal.",
    )

    magnetic_ordering: Union[str, Ordering] = Field(
        ..., description="Magnetic ordering of the calculation.",
    )


class BandStructureSummaryData(ElectronicStructureSummary):
    nbands: float = Field(
        ..., description="Number of bands.",
    )

    equivalent_labels: Dict = Field(
        ..., description="Equivalent k-point labels in other k-path conventions.",
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
    total: Dict[Union[Spin, str], ElectronicStructureBaseData] = Field(
        None, description="Total DOS summary data.",
    )

    elemental: Dict[
        Element,
        Dict[
            Union[str, OrbitalType], Dict[Union[Spin, str], ElectronicStructureBaseData]
        ],
    ] = Field(
        None,
        description="Band structure summary data using the Hinuma et al. path convention.",
    )

    orbital: Dict[
        OrbitalType, Dict[Union[Spin, str], ElectronicStructureBaseData]
    ] = Field(
        None,
        description="Band structure summary data using the Latimer-Munro path convention.",
    )

    magnetic_ordering: Union[str, Ordering] = Field(
        None, description="Magnetic ordering of the calculation.",
    )


T = TypeVar("T", bound="ElectronicStructureDoc")


class ElectronicStructureDoc(PropertyDoc, ElectronicStructureSummary):
    """
    Definition for a core Electronic Structure Document
    """

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
        material_id: Union[MPID, int],
        structure: Structure,
        dos: Dict[Union[MPID, int], CompleteDos],
        is_gap_direct: bool,
        is_metal: bool,
        setyawan_curtarolo: Dict[Union[MPID, int], BandStructureSymmLine] = None,
        hinuma: Dict[Union[MPID, int], BandStructureSymmLine] = None,
        latimer_munro: Dict[Union[MPID, int], BandStructureSymmLine] = None,
    ) -> T:
        """
        Builds a electronic structure document using band structure and density of states data.
        """

        # -- Process density of states data

        dos_task, dos = list(dos.items())[0]

        orbitals = [OrbitalType.s, OrbitalType.p, OrbitalType.d]
        spins = list(dos.densities.keys())

        ele_dos = dos.get_element_dos()
        tot_orb_dos = dos.get_spd_dos()

        elements = ele_dos.keys()

        dos_efermi = dos.efermi

        is_gap_direct = is_gap_direct
        is_metal = is_metal

        dos_mag_ordering = CollinearMagneticStructureAnalyzer(dos.structure).ordering

        summary_band_gap = dos.get_gap()
        summary_cbm, summary_vbm = dos.get_cbm_vbm()

        dos_data = {
            "total": defaultdict(dict),
            "elemental": {element: defaultdict(dict) for element in elements},
            "orbital": defaultdict(dict),
            "magnetic_ordering": dos_mag_ordering,
        }

        for spin in spins:

            # - Process total DOS data
            band_gap = dos.get_gap(spin=spin)
            (cbm, vbm) = dos.get_cbm_vbm(spin=spin)

            dos_data["total"][spin] = ElectronicStructureBaseData(
                calc_id=dos_task, band_gap=band_gap, cbm=cbm, vbm=vbm, efermi=dos_efermi
            )

            # - Process total orbital projection data
            for orbital in orbitals:

                band_gap = tot_orb_dos[orbital].get_gap(spin=spin)

                (cbm, vbm) = tot_orb_dos[orbital].get_cbm_vbm(spin=spin)

                dos_data["orbital"][orbital][spin] = ElectronicStructureBaseData(
                    calc_id=dos_task,
                    band_gap=band_gap,
                    cbm=cbm,
                    vbm=vbm,
                    efermi=dos_efermi,
                )

        # - Process element and element orbital projection data
        for ele in ele_dos:
            orb_dos = dos.get_element_spd_dos(ele)

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

                    dos_data["elemental"][ele][orbital][
                        spin
                    ] = ElectronicStructureBaseData(
                        calc_id=dos_task,
                        band_gap=band_gap,
                        cbm=cbm,
                        vbm=vbm,
                        efermi=dos_efermi,
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

                bs_mag_ordering = CollinearMagneticStructureAnalyzer(
                    bs.structure
                ).ordering

                gap_dict = bs.get_band_gap()
                is_metal = bs.is_metal()

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
                    gen_labels = set([label for label in equivalent_labels["lm"]["sc"]])
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

                bs_data[bs_type] = BandStructureSummaryData(
                    calc_id=bs_task,
                    band_gap=band_gap,
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

        return cls.from_structure(
            material_id=material_id,
            calc_id=dos_task,
            structure=structure,
            band_gap=summary_band_gap,
            cbm=summary_cbm,
            vbm=summary_vbm,
            efermi=dos_efermi,
            is_gap_direct=is_gap_direct,
            is_metal=is_metal,
            magnetic_ordering=dos_mag_ordering,
            bandstructure=bs_entry,
            dos=dos_entry,
        )
