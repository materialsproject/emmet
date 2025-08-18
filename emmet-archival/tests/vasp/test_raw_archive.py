import h5py
import json
import numpy as np

from monty.io import zopen

from emmet.core.tasks import TaskDoc
from emmet.core.utils import get_hash_blocked

from emmet.archival.vasp.raw import RawArchive
from emmet.archival.utils import zpath


def test_from_directory(tmp_dir, test_dir):
    vasp_files_dir = test_dir / "raw_vasp"
    archiver = RawArchive.from_directory(vasp_files_dir)
    archiver.to_archive("archive.h5")

    with h5py.File("archive.h5", "r") as f:
        for calc_type in f:
            for fname in f[calc_type]:
                if computed_md5 := f[calc_type][fname].attrs.get("md5"):
                    assert computed_md5 == get_hash_blocked(
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

        orig_file = zpath(vasp_files_dir / fname)
        # check that original file exists
        assert orig_file.exists()

        # for non-POTCAR data, check that roundtrip returns the same data
        if not any(f in fname.lower() for f in ("potcar", ".h5")):
            with zopen(orig_file, "rt") as f_orig, zopen(file_meta.path, "rt") as f_new:
                assert f_orig.read() == f_new.read()

    # Test validation from RawArchive
    for valid_method in ("validate", "fast_validate"):
        valid_doc = getattr(RawArchive, valid_method)("archive.h5")
        assert not valid_doc.valid
        assert len(valid_doc.reasons) == 1
        assert any(
            "PSEUDOPOTENTIALS --> Incorrect POTCAR files" in r
            for r in valid_doc.reasons
        )
        assert valid_doc.vasp_files.run_type == "relax"
        assert valid_doc.vasp_files.functional == "r2scan"
        assert valid_doc.vasp_files.valid_input_set_name == "MPScanRelaxSet"

    # Test round trip TaskDoc
    # Note that some fields (those with datetimes or with POTCAR info stripped)
    # will differ in resultant RawArchive
    expected_diff_keys = {
        "builder_meta",
        "dir_name",
        "calcs_reversed",
        "orig_inputs",
        "input",
        "last_updated",
        "completed_at",
    }
    orig_task_dict = TaskDoc.from_directory(test_dir / "raw_vasp").model_dump()
    extracted_task_dict = RawArchive.to_task_doc("archive.h5").model_dump()
    assert all(
        orig_task_dict[k] == extracted_task_dict[k]
        for k in set(TaskDoc.model_fields).difference(expected_diff_keys)
    )
