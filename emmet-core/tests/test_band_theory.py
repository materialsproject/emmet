import json

import numpy as np
import pytest

from emmet.core.io.pymatgen import (
    Lattice,
    Orbital,
    PeriodicSite,
    Spin,
    CompleteDos,
    Dos,
    Structure,
    Vasprun,
)

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
from emmet.core.testing_utils import DataArchive, assert_nested_close

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
    # arrow stores band energies and projections as float32
    assert_nested_close(test_arrow_bs_doc, elec_bs)

    _, _, edos = dos_fixture
    dos_arrow_struct = pa.scalar(
        edos.model_dump(context={"format": "arrow"}), type=arrowize(ElectronicDos)
    )
    test_arrow_dos_doc = ElectronicDos(
        **dos_arrow_struct.as_py(maps_as_pydicts="strict")
    )
    # arrow stores densities as float32
    assert_nested_close(test_arrow_dos_doc, edos)


@pytest.mark.skipif(
    not ARROW_COMPATIBLE, reason="pyarrow must be installed to run this test."
)
def test_arrow_float32_types(bs_fixture, dos_fixture):
    f32 = pa.float32()

    bs_type = arrowize(ElectronicBS)
    assert bs_type.field("spin_up_bands").type == pa.list_(pa.list_(f32))
    assert bs_type.field("spin_down_bands").type == pa.list_(pa.list_(f32))
    assert bs_type.field("projections").type.field("spin_up").type == pa.large_list(f32)
    assert bs_type.field("projections").type.field("spin_down").type == pa.large_list(
        f32
    )
    # quantities not downcast: k-points, lattice, Fermi level
    assert bs_type.field("qpoints").type == pa.list_(pa.list_(pa.float64()))
    assert bs_type.field("efermi").type == pa.float64()

    dos_type = arrowize(ElectronicDos)
    assert dos_type.field("spin_up_densities").type == pa.list_(f32)
    assert dos_type.field("spin_down_densities").type == pa.list_(f32)
    assert dos_type.field("energies").type == pa.list_(pa.float64())
    pdos_type = dos_type.field("projected_densities").type
    assert pdos_type.field("spin_up_densities").type == pa.list_(pa.list_(f32))
    assert pdos_type.field("spin_down_densities").type == pa.list_(pa.list_(f32))

    # the types are used when building tables, including nested projections
    _, _, elec_bs = bs_fixture
    assert elec_bs.projections is not None
    table = pa.Table.from_pylist(
        [elec_bs.model_dump(context={"format": "arrow"})],
        schema=pa.schema(bs_type),
    )
    assert table["projections"].type.field("spin_up").type == pa.large_list(f32)

    _, _, edos = dos_fixture
    assert edos.projected_densities is not None
    table = pa.Table.from_pylist(
        [edos.model_dump(context={"format": "arrow"})], schema=pa.schema(dos_type)
    )
    assert table["spin_up_densities"].type == pa.list_(f32)
    assert table["projected_densities"].type.field("spin_up_densities").type == (
        pa.list_(pa.list_(f32))
    )


def _make_pdos(num_sites: int, num_orbitals: int = 3, num_energies: int = 5):
    """A structure of identical elements, and projected DOS of each of its sites."""
    rng = np.random.default_rng(seed=num_sites)
    side = round(num_sites ** (1 / 3)) + 1
    coords = [
        [i / side, j / side, k / side]
        for i in range(side)
        for j in range(side)
        for k in range(side)
    ][:num_sites]
    structure = Structure(Lattice.cubic(4.0 * side), ["Si"] * num_sites, coords)
    orbitals = [Orbital.s, Orbital.py, Orbital.pz, Orbital.px][:num_orbitals]
    pdos = {
        structure[i]: {
            orbital: {Spin.up: rng.random(num_energies)} for orbital in orbitals
        }
        for i in range(num_sites)
    }
    return pdos, structure


class _CountSiteComparisons:
    """Count the comparisons of sites, which is how sites are slow to find."""

    def __init__(self, monkeypatch):
        self.count = 0
        original = PeriodicSite.__eq__

        def counting_eq(site, other):
            self.count += 1
            return original(site, other)

        monkeypatch.setattr(PeriodicSite, "__eq__", counting_eq)


@pytest.mark.parametrize("num_sites, num_orbitals", [(8, 3), (27, 4)])
def test_projected_dos_site_indices(monkeypatch, num_sites, num_orbitals):
    pdos, structure = _make_pdos(num_sites, num_orbitals)
    comparisons = _CountSiteComparisons(monkeypatch)

    projected_dos = ProjectedDos.from_pmg_like(pdos, structure)

    # the sites of the DOS are the sites of the structure, which are
    # found by identity and are not compared with each other at all
    assert comparisons.count == 0
    assert projected_dos.site_index == [
        i for i in range(num_sites) for _ in range(num_orbitals)
    ]
    assert projected_dos.orbital == ["s", "py", "pz", "px"][:num_orbitals] * num_sites

    # and the DOS can be recovered
    recovered = projected_dos.to_pmg_like(structure)
    assert set(recovered) == set(pdos)
    for site, orbitals in pdos.items():
        for orbital, spin_dos in orbitals.items():
            assert np.allclose(recovered[site][orbital][Spin.up], spin_dos[Spin.up])


def test_projected_dos_site_indices_of_unlisted_sites(monkeypatch):
    """Sites which are not the structure's objects are found by comparing them."""
    num_sites, num_orbitals = 27, 4
    pdos, structure = _make_pdos(num_sites, num_orbitals)

    # equal sites which are different objects, in a different order
    copied = structure.copy()
    shuffled = {copied[i]: pdos[structure[i]] for i in reversed(range(num_sites))}
    assert not any(site is ref for site in shuffled for ref in structure)
    comparisons = _CountSiteComparisons(monkeypatch)

    projected_dos = ProjectedDos.from_pmg_like(shuffled, structure)

    assert projected_dos.site_index == [
        i for i in reversed(range(num_sites)) for _ in range(num_orbitals)
    ]
    # each site is looked up once, and not once for each of its orbitals, which
    # would be num_orbitals times as many comparisons
    assert 0 < comparisons.count <= num_sites * (num_sites + 1) // 2


def test_projected_dos_site_not_in_structure():
    pdos, structure = _make_pdos(8)
    moved = structure.copy()
    moved.translate_sites([0], [0.01, 0.0, 0.0])
    with pytest.raises(ValueError, match="not in the structure"):
        ProjectedDos.from_pmg_like({moved[0]: pdos[structure[0]]}, structure)


def test_projected_dos_from_vasprun_sites(dos_fixture):
    """The sites of a real DOS are the objects of its structure."""
    _, pmg_dos, edos = dos_fixture
    assert all(any(site is ref for ref in pmg_dos.structure) for site in pmg_dos.pdos)
    projected = edos.projected_densities
    assert sorted(set(projected.site_index)) == list(range(len(pmg_dos.structure)))


def test_obtain_path_type(fe_line_mode_bandstructure):

    path_type, kpath, _ = next(
        obtain_path_type(
            fe_line_mode_bandstructure.structure,
            [x.frac_coords for x in fe_line_mode_bandstructure.kpoints],
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
