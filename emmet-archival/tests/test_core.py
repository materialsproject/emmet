"""Test core archival features."""

from pathlib import Path
import pytest

from emmet.archival.core import FileArchive, _get_path_relative_to_parent
from emmet.archival.utils import CompressionType


@pytest.mark.parametrize("compressor", ["ZSTD", "GZIP"])
def test_file_archiver(tmp_dir, compressor):

    lorem = [
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua",
        "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat",
        "Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur",
        "Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.",
    ]

    fs = [
        Path(x).absolute()
        for x in [
            "root/sub1/file1.txt",
            "root/file2.txt",
            "root/sub1/sub2/sub3/file3.txt",
            "root/sub1/sub2/file4.txt",
        ]
    ]

    for i, p in enumerate(fs):
        if not p.parent.exists():
            p.parent.mkdir(exist_ok=True, parents=True)
        p.write_text(lorem[i])

    depth_to_idx = {
        1: [1],
        2: [0, 1],
        3: [0, 1, 3],
        4: [0, 1, 2, 3],
        None: [0, 1, 2, 3],
    }

    # Check that we get expected number of files with specified depths:
    # int = number of sub levels that are searched
    # None = search until you hit the bottom
    assert all(
        set(FileArchive.from_directory("root", depth=depth).files)
        == {fs[idx] for idx in idxs}
        for depth, idxs in depth_to_idx.items()
    )

    # Now archive this
    archiver = FileArchive.from_directory("root", depth=None, compression=compressor)
    archiver.to_archive("lorem.h5")

    # extract and compare extracted file structure + data to original
    orig = {
        str(_get_path_relative_to_parent(p, Path("root").absolute())): p.read_text()
        for p in fs
    }

    output_path = Path("lorem").absolute()
    for compression in (CompressionType.AUTO_DETECT, compressor):
        archiver.extract("lorem.h5", output_dir=output_path, compression=compression)
        extracted = {
            str(_get_path_relative_to_parent(p, output_path)): p.read_text()
            for p in output_path.glob("**/*.txt")
        }

        assert set(extracted) == set(orig)
        assert all(v == extracted[k] for k, v in orig.items())
