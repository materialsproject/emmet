from pathlib import Path
import h5py
import json
import numpy as np

from monty.io import zopen
from monty.os.path import zpath
from emmet.core.utils import get_md5_blocked

from emmet.archival.vasp.raw import RawArchive


def test_from_directory(tmp_dir, test_dir):
    vasp_files_dir = test_dir / "test_raw_archive"
    archiver = RawArchive.from_directory(vasp_files_dir)
    archiver.to_archive("archive.h5")

    with h5py.File("archive.h5", "r") as f:
        for calc_type in f:
            for fname in f[calc_type]:
                if computed_md5 := f[calc_type][fname].attrs.get("md5"):
                    assert computed_md5 == get_md5_blocked(
                        f[calc_type][fname].attrs["file_path"]
                    )

                if "POTCAR" in fname:
                    potcar_data = json.loads(np.array(f[calc_type][fname])[0].decode())
                    assert isinstance(potcar_data, list)
                    assert all(
                        isinstance(potcar_spec, dict)
                        and potcar_spec.get("keywords")
                        and potcar_spec.get("stats")
                        for potcar_spec in potcar_data
                    )

    raw_data = RawArchive.extract("archive.h5")
    for file_meta in raw_data:
        if "potcar" in file_meta.name.lower():
            fname = file_meta.name.split(".")[0]
        else:
            fname = file_meta.name

        orig_file = Path(zpath(str(vasp_files_dir / fname)))
        # check that original file exists
        assert orig_file.exists()

        # for non-POTCAR data, check that roundtrip returns the same data
        if not any(f in fname.lower() for f in ("potcar", ".h5")):
            with zopen(orig_file, "rt") as f_orig, zopen(file_meta.path, "rt") as f_new:
                assert f_orig.read() == f_new.read()
