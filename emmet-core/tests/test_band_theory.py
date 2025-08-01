import json
import numpy as np
import pytest

from pymatgen.electronic_structure.dos import Dos, CompleteDos
from pymatgen.io.vasp import Vasprun

from emmet.core.band_theory import ElectronicBS, ElectronicDos

try:
    import pyarrow
except ImportError:
    pyarrow = None


def test_elec_band_struct(test_dir):

    vasprun = Vasprun(
        test_dir / "vasp/r2scan_relax/vasprun.xml.gz", parse_projected_eigen=True
    )

    pmg_bs = vasprun.get_band_structure()
    elec_bs = ElectronicBS.from_pmg(pmg_bs)

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

    assert all(
        getattr(elec_bs, f"spin_{s}_projections", None) is not None
        for s in ("up", "down")
    )

    dict_rep = elec_bs.model_dump()
    assert isinstance(dict_rep["structure"], dict)

    # round trip JSON
    dumped = elec_bs.model_dump_json()
    assert ElectronicBS(**json.loads(dumped)) == elec_bs

    # round trip pymatgen
    assert pmg_bs.as_dict() == elec_bs.to_pmg().as_dict()

    if pyarrow:
        # round trip arrow
        table = elec_bs.to_arrow()
        assert isinstance(table, pyarrow.Table)
        assert set(ElectronicBS.model_fields) == set(table.column_names)
        assert ElectronicBS.from_arrow(table) == elec_bs


def test_elec_dos(test_dir):

    vasprun = Vasprun(
        test_dir / "vasp/Si_uniform/vasprun.xml.gz",
    )
    pmg_dos = vasprun.complete_dos

    edos = ElectronicDos.from_pmg(pmg_dos)
    assert edos.efermi == pytest.approx(6.26639781)
    assert edos.structure == vasprun.final_structure
    for spin, dos in pmg_dos.densities.items():
        assert np.all(
            np.abs(np.array(getattr(edos, f"spin_{spin.name}_densities")) - dos) < 1e-6
        )
    assert len(edos.projected_densities) == len(edos.structure)

    # test roundtrip json
    dumped = edos.model_dump_json()
    assert ElectronicDos(**json.loads(dumped)) == edos

    # test roundtrip pymatgen
    new_pmg_dos = edos.to_pmg()
    assert new_pmg_dos.as_dict() == pmg_dos.as_dict()
    assert isinstance(new_pmg_dos, CompleteDos)

    if pyarrow:
        # test roundtrip parquet
        assert ElectronicDos.from_arrow(edos.to_arrow()) == edos

    # test partial data return type
    edos_incomplete = ElectronicDos(
        **edos.model_dump(exclude=["structure", "projected_densities"])
    )
    assert isinstance(edos_incomplete.to_pmg(), Dos)
