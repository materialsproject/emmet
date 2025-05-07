import h5py
import json
import numpy as np

from emmet.archival.vasp.raw import RawArchive, get_md5_blocked


def test_from_directory(tmp_dir, test_dir):
    archiver = RawArchive.from_directory(test_dir / "test_raw_archive")
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

    RawArchive.from_archive("archive.h5")
    # assert all(
    #     archive.parsed_objects.get is not
    # )

    # assert False
