from dataclasses import dataclass
import gzip
import json
import numpy as np
from pymatgen.core import Structure
import pytest

from emmet.core.featurization.featurizers import (
    Featurizer,
    CrystalNNFingerprint,
    SiteStatsFingerprint,
)


@pytest.fixture
def fingerprint_test_data(test_dir):
    with gzip.open(test_dir / "featurizers_data.json.gz", "rb") as f:
        return json.load(f)


@pytest.fixture
def test_structure(test_dir):
    return Structure.from_file(test_dir / "Si_mp_149.cif")


@dataclass
class badClass(Featurizer):

    def featurize(self):
        return [1.0]


@dataclass
class otherBadClass(Featurizer):

    def feature_labels(self):
        return ["label"]


def test_abc():
    for test_cls in (Featurizer, badClass, otherBadClass):
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            test_cls()


def test_stats():

    fingerprinter = SiteStatsFingerprint()

    test_arr = np.linspace(min_v := 1, max_v := 42.1, 23)
    assert fingerprinter.get_stat("mean", test_arr) == pytest.approx(21.55)
    assert fingerprinter.get_stat("minimum", test_arr) == pytest.approx(min_v)
    assert fingerprinter.get_stat("maximum", test_arr) == pytest.approx(max_v)
    assert fingerprinter.get_stat("std_dev", test_arr) == pytest.approx(12.392116, 1e-6)


def test_fingerprinters(fingerprint_test_data, test_structure):

    for preset in ("cn", "ops"):
        cnnf = CrystalNNFingerprint.from_preset(preset)
        assert (
            cnnf.feature_labels == fingerprint_test_data["crystal_nn"][preset]["labels"]
        )
        assert cnnf.featurize(test_structure, 0) == pytest.approx(
            fingerprint_test_data["crystal_nn"][preset]["features"]
        )

        ssf = SiteStatsFingerprint(site_featurizer=cnnf)
        assert (
            ssf.feature_labels == fingerprint_test_data["site_stats"][preset]["labels"]
        )
        assert ssf.featurize(test_structure) == pytest.approx(
            fingerprint_test_data["site_stats"][preset]["features"]
        )
