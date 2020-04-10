import os
import json
from random import random
from pathlib import PosixPath

from emmet.core.settings import EmmetSettings


def test_default_config_path(tmp_path: PosixPath):
    """Make sure the default config path works
    """

    rand_symprec = random()
    with open(tmp_path / "temp_config.json", "w") as f:
        json.dump({"SYMPREC": rand_symprec}, f)

    os.environ["EMMET_CONFIG_FILE"] = str(tmp_path.resolve() / "temp_config.json")
    test_config = EmmetSettings()

    assert test_config.SYMPREC == rand_symprec


def test_allow_extra_fields(tmp_path: PosixPath):
    """Makes sure emmet config can be subclassed without loading issues"""

    with open(tmp_path / "temp_config.json", "w") as f:
        json.dump({"sub_class_prop": True}, f)

    os.environ["EMMET_CONFIG_FILE"] = str(tmp_path.resolve() / "temp_config.json")

    test_config = EmmetSettings()
