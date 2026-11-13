"""Test the CHGCAR-like volumetric data model."""

import numpy as np
import pytest

from emmet.core import ARROW_COMPATIBLE
from emmet.core.io.pymatgen import Chgcar, Elfcar, Locpot
from emmet.core.vasp.models import (
    VOLUMETRIC_PARSERS,
    ChgcarLike,
    Pot,
    VolumetricLabel,
    volumetric_file_type,
)

if ARROW_COMPATIBLE:
    import pyarrow as pa

    from emmet.core.arrow import arrowize

GRID = (2, 2, 3)


@pytest.mark.parametrize(
    "file_name, expected",
    [
        ("CHGCAR", "CHGCAR"),
        ("CHGCAR.relax1.gz", "CHGCAR"),
        ("CHG", "CHG"),
        ("CHG.relax2.gz", "CHG"),
        ("PARCHG", "PARCHG"),
        ("PARCHG.0001.0002", "PARCHG"),
        ("AECCAR0.gz", "AECCAR0"),
        ("AECCAR2", "AECCAR2"),
        ("LOCPOT.relax1.gz", "LOCPOT"),
        ("ELFCAR", "ELFCAR"),
        ("POT", "POT"),
        ("locpot", "LOCPOT"),
        # not volumetric files
        ("POTCAR", None),
        ("POTCAR.spec", None),
        ("POTCAR.orig.gz", None),
        ("CHGCAR_backup", None),
        ("vasprun.xml", None),
        ("DOSCAR", None),
    ],
)
def test_volumetric_file_type(file_name, expected):
    assert volumetric_file_type(file_name) == expected
    assert volumetric_file_type(f"/some/dir/{file_name}") == expected


def test_volumetric_parsers():
    assert VOLUMETRIC_PARSERS["LOCPOT"] is Locpot
    assert VOLUMETRIC_PARSERS["ELFCAR"] is Elfcar
    assert VOLUMETRIC_PARSERS["POT"] is Pot
    assert {k for k, v in VOLUMETRIC_PARSERS.items() if v is Chgcar} == {
        "CHGCAR",
        "CHG",
        "AECCAR0",
        "AECCAR1",
        "AECCAR2",
        "PARCHG",
    }


@pytest.mark.parametrize(
    "pmg_cls, file_key, labels",
    [
        (Chgcar, "collinear", ["total", "diff"]),
        (Chgcar, "collinear_no_aug", ["total", "diff"]),
        (Chgcar, "unpolarized", ["total"]),
        (Chgcar, "noncollinear", ["total", "diff_x", "diff_y", "diff_z", "diff"]),
        (Locpot, "collinear_no_aug", ["spin_up", "spin_down"]),
        (Locpot, "unpolarized", ["total"]),
        (Elfcar, "collinear_no_aug", ["spin_up", "spin_down"]),
        (Elfcar, "unpolarized", ["total"]),
    ],
)
def test_pmg_roundtrip(volumetric_files, pmg_cls, file_key, labels):
    pmg_obj = pmg_cls.from_file(volumetric_files[file_key])
    model = ChgcarLike.from_pmg(pmg_obj, identifier="mp-0")

    assert [lab.value for lab in model.labels] == labels
    assert all(rank == GRID for rank in model.data_rank)
    # the in-memory model keeps full precision
    for lab, data in zip(model.labels, model.data):
        assert np.array(data) == pytest.approx(pmg_obj.data[lab.value].flatten())
    # Note that CHGCAR-formatted files without augmentation blocks have a
    # list of empty entries in `data_aug`, not None
    has_aug_data = model.data_aug is not None and any(model.data_aug)
    assert has_aug_data == (file_key == "collinear" and pmg_cls is Chgcar)

    new_pmg_obj = model.to_pmg(pmg_cls=pmg_cls)
    assert isinstance(new_pmg_obj, pmg_cls)
    assert new_pmg_obj.structure == pmg_obj.structure
    assert set(new_pmg_obj.data) == set(pmg_obj.data)
    for k, v in pmg_obj.data.items():
        assert np.allclose(new_pmg_obj.data[k], v)


@pytest.mark.skipif(
    not ARROW_COMPATIBLE, reason="pyarrow must be installed to run this test."
)
def test_arrow_types():
    schema = pa.schema(arrowize(ChgcarLike))
    assert schema.field("data").type == pa.list_(pa.large_list(pa.float32()))
    assert schema.field("labels").type == pa.list_(pa.string())

    # augmentation data is not downcast
    aug_type = schema.field("data_aug").type
    assert aug_type == pa.list_(
        pa.list_(pa.struct([("label", pa.string()), ("data", pa.list_(pa.float64()))]))
    )


@pytest.mark.skipif(
    not ARROW_COMPATIBLE, reason="pyarrow must be installed to run this test."
)
def test_arrow_roundtrip(volumetric_files):
    schema = pa.schema(arrowize(ChgcarLike))

    # a batch mixing every flavor of volumetric data, to ensure the same
    # schema is valid for all of them
    entries = [
        (Chgcar, "collinear"),
        (Chgcar, "collinear_no_aug"),
        (Chgcar, "unpolarized"),
        (Chgcar, "noncollinear"),
        (Locpot, "collinear_no_aug"),
        (Elfcar, "unpolarized"),
    ]
    pmg_objs = [cls.from_file(volumetric_files[key]) for cls, key in entries]
    models = [
        ChgcarLike.from_pmg(obj, identifier=f"mp-{i}") for i, obj in enumerate(pmg_objs)
    ]

    table = pa.Table.from_pylist(
        [m.model_dump(context={"format": "arrow"}) for m in models], schema=schema
    )
    assert table.schema == schema
    assert table.num_rows == len(models)
    assert table["data"].type == pa.list_(pa.large_list(pa.float32()))

    for (cls, _), pmg_obj, row in zip(
        entries, pmg_objs, table.to_pylist(maps_as_pydicts="strict")
    ):
        new_pmg_obj = ChgcarLike(**row).to_pmg(pmg_cls=cls)
        assert new_pmg_obj.structure == pmg_obj.structure
        assert set(new_pmg_obj.data) == set(pmg_obj.data)
        for k, v in pmg_obj.data.items():
            # values are stored as float32 in arrow
            assert np.allclose(new_pmg_obj.data[k], v, rtol=1e-6, atol=1e-6)


def test_volumetric_labels():
    for lab in ("total", "diff", "diff_x", "diff_y", "diff_z", "spin_up", "spin_down"):
        assert VolumetricLabel(lab).value == lab


class TestPot:
    """A POT file is a potential, whose spin blocks are not those of a CHGCAR."""

    def test_spin_polarized_blocks_are_spin_up_and_down(self, volumetric_files):
        path = volumetric_files["pot_collinear"]

        # pymatgen's Chgcar reader labels the blocks of a POT `total` and `diff`
        assert set(Chgcar.from_file(path).data) == {"total", "diff"}

        pot = Pot.from_file(path)
        assert isinstance(pot, Chgcar)
        assert set(pot.data) == {"spin_up", "spin_down"}
        # the blocks are the ones in the file, in order, not a sum or a difference
        chgcar = Chgcar.from_file(path)
        assert np.array_equal(pot.data["spin_up"], chgcar.data["total"])
        assert np.array_equal(pot.data["spin_down"], chgcar.data["diff"])
        assert not np.allclose(pot.data["spin_up"], pot.data["spin_down"])

    def test_augmentation_data_is_kept_and_relabelled(self, volumetric_files):
        path = volumetric_files["pot_collinear"]
        chgcar = Chgcar.from_file(path)
        pot = Pot.from_file(path)
        assert set(pot.data_aug) == {"spin_up", "spin_down"}
        for new, old in (("spin_up", "total"), ("spin_down", "diff")):
            assert pot.data_aug[new].keys() == chgcar.data_aug[old].keys()
            assert pot.data_aug[new]  # not empty
            for atom, occupancies in chgcar.data_aug[old].items():
                assert np.array_equal(pot.data_aug[new][atom], occupancies)

    def test_other_numbers_of_blocks(self, volumetric_files):
        unpolarized = Pot.from_file(volumetric_files["pot_unpolarized"])
        assert set(unpolarized.data) == {"total"}
        assert set(unpolarized.data_aug) == {"total"}

        # the scalar potential and the three components of the magnetic field
        noncollinear = Pot.from_file(volumetric_files["pot_noncollinear"])
        assert set(noncollinear.data) >= {"total", "diff_x", "diff_y", "diff_z"}
        assert "spin_up" not in noncollinear.data

    def test_there_is_no_magnetization(self, volumetric_files):
        assert (
            Pot.from_file(volumetric_files["pot_collinear"]).net_magnetization is None
        )
        assert Chgcar.from_file(volumetric_files["pot_collinear"]).net_magnetization

    def test_model_roundtrip(self, volumetric_files):
        pot = Pot.from_file(volumetric_files["pot_collinear"])
        model = ChgcarLike.from_pmg(pot, identifier="mp-0")
        assert [lab.value for lab in model.labels] == ["spin_up", "spin_down"]
        assert model.data_aug is not None and all(model.data_aug)

        new_pot = model.to_pmg(pmg_cls=Pot)
        assert isinstance(new_pot, Pot)
        assert set(new_pot.data) == {"spin_up", "spin_down"}
        assert set(new_pot.data_aug) == {"spin_up", "spin_down"}
        for k, v in pot.data.items():
            assert np.allclose(new_pot.data[k], v)
        # `to_pmg` gives the augmentation data of each atom as an AugChargeData
        for k, atoms in pot.data_aug.items():
            assert len(new_pot.data_aug[k]) == len(atoms)
            for aug, occupancies in zip(new_pot.data_aug[k], atoms.values()):
                assert np.allclose(aug.data, occupancies)

    @pytest.mark.skipif(
        not ARROW_COMPATIBLE, reason="pyarrow must be installed to run this test."
    )
    def test_arrow_roundtrip(self, volumetric_files):
        schema = pa.schema(arrowize(ChgcarLike))
        pot = Pot.from_file(volumetric_files["pot_collinear"])
        model = ChgcarLike.from_pmg(pot, identifier="mp-0")
        table = pa.Table.from_pylist(
            [model.model_dump(context={"format": "arrow"})], schema=schema
        )
        row = table.to_pylist(maps_as_pydicts="strict")[0]
        new_pot = ChgcarLike(**row).to_pmg(pmg_cls=Pot)
        assert set(new_pot.data) == {"spin_up", "spin_down"}
        for k, v in pot.data.items():
            assert np.allclose(new_pot.data[k], v, rtol=1e-6, atol=1e-6)
