import json

import numpy as np
import pytest

from monty.serialization import loadfn
from pymatgen.electronic_structure.core import Spin
from pymatgen.electronic_structure.dos import CompleteDos, Dos
from pymatgen.io.vasp import Vasprun

from emmet.core import ARROW_COMPATIBLE
from emmet.core.band_theory import (
    BSPathType,
    ElectronicBS,
    ProjectedBS,
    ElectronicDos,
    ProjectedDos,
    obtain_path_type,
    _coarse_list_superset,
    _loose_path_match,
)
from emmet.core.testing_utils import DataArchive

if ARROW_COMPATIBLE:
    import pyarrow as pa

    from emmet.core.arrow import arrowize


@pytest.fixture(scope="module")
def bs_fixture(test_dir):
    vasprun = DataArchive.extract_obj(
        test_dir / "vasp/r2scan_relax.json.gz",
        "vasprun.xml.gz",
        Vasprun,
        parse_projected_eigen=True,
    )
    pmg_bs = vasprun.get_band_structure()
    elec_bs = ElectronicBS.from_pmg(pmg_bs, identifier="mp-0")

    return (vasprun, pmg_bs, elec_bs)


@pytest.fixture(scope="module")
def dos_fixture(test_dir):
    vasprun = DataArchive.extract_obj(
        test_dir / "vasp/Si_uniform.json.gz",
        "vasprun.xml.gz",
        Vasprun,
        parse_projected_eigen=True,
    )
    pmg_dos = vasprun.complete_dos
    edos = ElectronicDos.from_pmg(pmg_dos, identifier="mp-0")

    return (vasprun, pmg_dos, edos)


def test_elec_band_struct(bs_fixture):
    vasprun, pmg_bs, elec_bs = bs_fixture

    assert len(elec_bs.qpoints) == 116
    assert np.all(
        np.abs(
            np.array(elec_bs.reciprocal_lattice)
            - np.array(vasprun.final_structure.lattice.reciprocal_lattice.matrix)
        )
        < 1e-6
    )
    assert elec_bs.structure == vasprun.final_structure
    assert elec_bs.efermi == pytest.approx(2.72974902)
    assert elec_bs.band_gap == pytest.approx(0.0)
    assert elec_bs.is_metal

    assert all(
        getattr(elec_bs, f"spin_{s}_bands", None) is not None for s in ("up", "down")
    )

    assert isinstance(elec_bs.projections, ProjectedBS)

    assert all(
        isinstance(getattr(elec_bs.projections, f"spin_{s}", None), list)
        for s in ("up", "down")
    )

    dict_rep = elec_bs.model_dump()
    assert isinstance(dict_rep["structure"], dict)

    # round trip JSON
    dumped = elec_bs.model_dump_json()
    assert ElectronicBS(**json.loads(dumped)) == elec_bs

    # round trip pymatgen
    assert pmg_bs.as_dict() == elec_bs.to_pmg().as_dict()

    assert (
        str(elec_bs)
        == f"ElectronicBS({elec_bs.identifier}: {elec_bs.structure.formula})"
    )
    assert elec_bs.__repr__() == str(elec_bs)


def test_base_electronic_dos():
    """Test base electronic DOS class for jellium."""
    rs = 4.0
    efermi = (9 * np.pi / 4.0) ** (1 / 3) / rs
    energies = np.linspace(0, 3 * efermi, 200)
    heg_dos = (2 * energies) ** (0.5) / np.pi**2

    for spin_pol in (1, 0.5):
        edos = ElectronicDos(
            spin_up_densities=spin_pol * heg_dos,
            spin_down_densities=spin_pol * heg_dos if spin_pol < 1 else None,
            energies=energies,
            efermi=efermi,
        )

        spins_to_check = [Spin.up]
        pmg_dos = edos.to_pmg()
        if abs(spin_pol) < 1:
            spins_to_check.append(Spin.down)
        else:
            assert pmg_dos.densities.get(Spin.down) is None

        for spin in spins_to_check:
            assert np.all(
                np.abs(
                    np.array(getattr(edos, f"spin_{spin.name}_densities"))
                    - pmg_dos.densities[spin]
                )
                < 1e-6
            )


def test_electronic_dos(dos_fixture):
    vasprun, pmg_dos, edos = dos_fixture

    assert edos.efermi == pytest.approx(6.26639781)
    assert edos.structure == vasprun.final_structure
    for spin, dos in pmg_dos.densities.items():
        assert np.all(
            np.abs(np.array(getattr(edos, f"spin_{spin.name}_densities")) - dos) < 1e-6
        )
    assert len(set(edos.projected_densities.site_index)) == len(edos.structure)
    assert isinstance(edos.projected_densities, ProjectedDos)
    assert (
        ProjectedDos._from_list_of_dict(edos.projected_densities._to_list_of_dict())
        == edos.projected_densities
    )

    # test roundtrip json
    dumped = edos.model_dump_json()
    assert ElectronicDos(**json.loads(dumped)) == edos

    # test roundtrip pymatgen
    new_pmg_dos = edos.to_pmg()
    assert new_pmg_dos.as_dict() == pmg_dos.as_dict()
    assert isinstance(new_pmg_dos, CompleteDos)

    # test partial data return type
    edos_incomplete = ElectronicDos(
        **edos.model_dump(exclude=["structure", "projected_densities"])
    )
    assert isinstance(edos_incomplete.to_pmg(), Dos)

    assert str(edos) == f"ElectronicDos({edos.identifier}: {edos.structure.formula})"
    assert edos.__repr__() == str(edos)


@pytest.mark.skipif(
    not ARROW_COMPATIBLE, reason="pyarrow must be installed to run this test."
)
def test_arrow(bs_fixture, dos_fixture):
    _, _, elec_bs = bs_fixture
    bs_arrow_struct = pa.scalar(
        elec_bs.model_dump(context={"format": "arrow"}), type=arrowize(ElectronicBS)
    )
    test_arrow_bs_doc = ElectronicBS(**bs_arrow_struct.as_py(maps_as_pydicts="strict"))
    assert test_arrow_bs_doc == elec_bs

    _, _, edos = dos_fixture
    dos_arrow_struct = pa.scalar(
        edos.model_dump(context={"format": "arrow"}), type=arrowize(ElectronicDos)
    )
    test_arrow_dos_doc = ElectronicDos(
        **dos_arrow_struct.as_py(maps_as_pydicts="strict")
    )
    assert test_arrow_dos_doc == edos


def test_obtain_path_type(test_dir):

    line_band_struct = loadfn(test_dir / "electronic_structure" / "Fe_bs.json.gz")

    path_type, kpath, _ = next(
        obtain_path_type(
            line_band_struct.structure,
            [x.frac_coords for x in line_band_struct.kpoints],
        )
    )
    assert isinstance(path_type, BSPathType)
    assert path_type == BSPathType.setyawan_curtarolo
    assert kpath == [
        "\\Gamma",
        "H",
        "N",
        "\\Gamma",
        "P",
        "H",
        "P",
        "N",
    ]


def test_utilities():

    assert _coarse_list_superset([1, 2, 3, 4, 5, 6, 7], [3, 4, 5])
    assert _coarse_list_superset([1, 2, 3, 4, 5, 6, 7], [3, 4, 5, 6, 7])
    assert _coarse_list_superset([1, 2, 3, 4, 5, 6, 7], [1, 2])
    assert not _coarse_list_superset(["a", "b", "c", "d", "e"], ["b", "d", "f"])

    assert (
        _loose_path_match(["\\Gamma", "A", "B", "P_1"]) == BSPathType.setyawan_curtarolo
    )
    assert _loose_path_match(["\\Gamma", "GAMMA", "B"]) == BSPathType.unknown
    assert _loose_path_match(["\\Gamma", "Γ", "B"]) == BSPathType.unknown
    assert _loose_path_match(["\\Gamma", "A", "B", r"P_{1}"]) == BSPathType.unknown

    assert _loose_path_match(["GAMMA", "A", "B", "P_1"]) == BSPathType.hinuma
    assert _loose_path_match(["\\Gamma", "GAMMA", "B"]) == BSPathType.unknown
    assert _loose_path_match(["GAMMA", "Γ", "B"]) == BSPathType.unknown
    assert _loose_path_match(["GAMMA", "a", "B"]) == BSPathType.unknown
    assert _loose_path_match(["GAMMA", "A", "B", r"P_{1}"]) == BSPathType.unknown

    assert _loose_path_match(["Γ", "a", "b", r"p_{1}"]) == BSPathType.latimer_munro
    assert _loose_path_match(["Γ", "\\Gamma", "b"]) == BSPathType.unknown
    assert _loose_path_match(["GAMMA", "Γ", "b"]) == BSPathType.unknown
    assert _loose_path_match(["Γ", "a", "b", "P_1"]) == BSPathType.unknown
