from emmet.core.mpid import MPID


def test_mpid():

    assert MPID("mp-3") == MPID("mp-3")
    assert MPID("mp-3") < 3
    assert MPID("mp-3") < MPID("np-3")
    assert MPID("mp-3") > MPID("mp-2")
    assert 3 > MPID("mp-3")
