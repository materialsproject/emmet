import os
from json import load

from emmet.api.core.settings import MAPISettings
from emmet.api.routes.molecules.tasks.utils import calcs_reversed_to_trajectory


def test_calcs_reversed_to_trajectory():
    with open(
        os.path.join(MAPISettings().TEST_FILES, "calcs_reversed_mpcule_36097.json")
    ) as file:
        calcs_reversed = load(file)
        trajectories = calcs_reversed_to_trajectory(calcs_reversed)

    assert len(trajectories) == 1
    assert trajectories[0]["charge"] == 0
    assert trajectories[0]["spin_multiplicity"] == 1
    assert trajectories[0]["frame_properties"][0]["electronic_energy"] == -581.728508782
    assert trajectories[0]["site_properties"][0]["mulliken"] == [
        -0.624353,
        0.48523,
        -0.261599,
        -0.538315,
        0.384461,
        -0.220568,
        -0.991913,
        1.115079,
        0.087732,
        0.097949,
        0.134817,
        0.13877,
        0.108679,
        0.084031,
    ]
