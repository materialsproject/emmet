import json
import numpy as np
import pytest

from pymatgen.io.vasp import Vasprun

from emmet.core.band_theory import ElectronicBS


def test_elec_band_struct(test_dir):

    vasprun = Vasprun(
        test_dir / "vasp/r2scan_relax/vasprun.xml.gz", parse_projected_eigen=True
    )

    elec_bs = ElectronicBS.from_pmg(vasprun.get_band_structure())

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

    dumped = elec_bs.model_dump_json()
    assert ElectronicBS(**json.loads(dumped)) == elec_bs
