from __future__ import annotations

import json
import os
from random import random
from typing import TYPE_CHECKING

from emmet.core.settings import EmmetSettings
from monty.serialization import dumpfn, loadfn
from monty.tempfile import ScratchDir

if TYPE_CHECKING:
    from pathlib import PosixPath


def test_default_config_path(tmp_path: PosixPath):
    """Make sure the default config path works."""
    rand_symprec = random()
    with open(tmp_path / "temp_config.json", "w") as f:
        json.dump({"SYMPREC": rand_symprec}, f)

    os.environ["EMMET_CONFIG_FILE"] = str(tmp_path.resolve() / "temp_config.json")
    test_config = EmmetSettings()

    assert rand_symprec == test_config.SYMPREC


def test_allow_extra_fields(tmp_path: PosixPath):
    """Makes sure emmet config can be subclassed without loading issues."""
    with open(tmp_path / "temp_config.json", "w") as f:
        json.dump({"sub_class_prop": True}, f)

    os.environ["EMMET_CONFIG_FILE"] = str(tmp_path.resolve() / "temp_config.json")

    EmmetSettings()


def test_from_url():
    """Makes sure loading from a URL Works."""
    os.environ[
        "EMMET_CONFIG_FILE"
    ] = "https://raw.githubusercontent.com/materialsproject/emmet/master/test_files/test_settings.json"

    test_config = EmmetSettings()

    assert test_config.ANGLE_TOL == 1.0


def test_seriallization():
    test_config = EmmetSettings()

    with ScratchDir("."):
        dumpfn(test_config, "test.json")
        reload_config = loadfn("test.json")

        assert isinstance(reload_config, EmmetSettings)
