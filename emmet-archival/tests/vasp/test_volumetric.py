"""Test volumetric archival."""

from tempfile import NamedTemporaryFile
import numpy as np

from pymatgen.analysis.structure_matcher import StructureMatcher
from pymatgen.io.vasp import Chgcar, Vasprun

from emmet.archival.volumetric import VolumetricArchive
from emmet.archival.vasp.volumetric import DosArchive, BandStructureArchive

chgcar_str = """Fake CHGCAR
    4.0
0.0 0.5 0.5
0.5 0.0 0.5
0.5 0.5 0.0
    Cs Cl
    1 1
Direct
0.125 0.125 0.125
0.875 0.875 0.875

    2 2 3
 4.544104e+00 2.149723e+01 1.583639e+01 1.480454e+01 2.127773e+01
 7.698752e+00 1.668832e+01 1.854999e+01 1.348429e+01 1.072021e+01
 2.835300e+01 1.854545e+01
augmentation occupancies 1 8
 1.260048e+01 1.714564e+01 1.661357e+01 2.858822e+01 2.787026e+01
 1.410466e+01 2.336182e+01 1.469713e+01
augmentation occupancies 2 8
 2.425031e+01 1.936727e+01 1.474219e+01 7.047136e+00 2.467184e+01
 1.982424e+01 1.073396e+01
    2 2 3
 1.690371e+01 1.102890e+01 1.568510e+01 1.937636e+01 1.666929e+01
 2.531654e+01 1.975681e+01 1.591917e+00 2.262067e+01 3.886095e+00
 1.616691e+01 2.299770e+01
augmentation occupancies 1 8
 1.260048e+01 1.714564e+01 1.661357e+01 2.858822e+01 2.787026e+01
 1.410466e+01 2.336182e+01 1.469713e+01
augmentation occupancies 2 8
 2.425031e+01 1.936727e+01 1.474219e+01 7.047136e+00 2.467184e+01
 1.982424e+01 1.073396e+01
"""


def test_volumetric_archive():
    with NamedTemporaryFile(mode="wt") as f:
        f.write(chgcar_str)
        f.seek(0)
        chg = Chgcar.from_file(f.name)

    chg_arch = VolumetricArchive.from_pmg(chg)
    for k, v in chg_arch.data.items():
        assert np.all(np.abs(v - chg.data[k.value]) < 1e-6)

    # Note that pymatgen doesn't parse augmentation charge data
    # cleanly - the data won't be equal here but the keys are.
    assert all(k.value in chg.data_aug for k in chg_arch.data_aug)

    # ensure structure is same on round trip
    assert chg.structure == chg_arch.structure


def test_dos(test_dir):
    vasprun = Vasprun(test_dir / "raw_vasp" / "vasprun.xml.gz")
    dos_arch = DosArchive.from_vasprun(vasprun)

    dos_table = dos_arch.to_arrow()

    pmg_from_arrow = DosArchive.from_arrow(dos_table)
    orig_dos_dict = vasprun.complete_dos.as_dict()
    dos_arch.to_archive("dos.parquet")
    pmg_from_parquet = DosArchive.extract("dos.parquet")

    for obj in (pmg_from_arrow, pmg_from_parquet):
        for k, v in obj.as_dict().items():
            if k == "structure":
                assert StructureMatcher().fit(
                    obj.structure, vasprun.complete_dos.structure
                )
            else:
                assert v == orig_dos_dict[k]


def test_bs(test_dir):

    vasprun = Vasprun(test_dir / "raw_vasp" / "vasprun.xml.gz")
    pmg_bs_dict = vasprun.get_band_structure().as_dict()
    bs_arch = BandStructureArchive.from_vasprun(vasprun)
    bs_arch.to_archive("bs.parquet")
    pmg_from_parquet = BandStructureArchive.extract("bs.parquet")
    for k, v in pmg_from_parquet.as_dict().items():
        if k == "structure":
            assert StructureMatcher().fit(
                pmg_from_parquet.structure, vasprun.final_structure
            )
        else:
            assert v == pmg_bs_dict[k]
