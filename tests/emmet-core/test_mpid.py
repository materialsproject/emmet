from emmet.core.mpid import MPID


def test_mpid():

    assert MPID("mp-3") == MPID("mp-3")
    assert MPID("mp-3") < 3
    assert MPID("mp-3") < MPID("np-3")
    assert MPID("mp-3") > MPID("mp-2")
    assert 3 > MPID("mp-3")
    assert MPID(MPID("mp-1234")) < MPID(1234)
    assert "mp-1234" < MPID(1234)
    assert MPID("1234") > MPID("mp-1234")
    assert MPID("1234") == MPID(1234)
    assert MPID("1234") == "1234"
    assert MPID("mp-12345") > MPID("mp-1234")

    assert min(
        [MPID("mp-44545"), MPID("mp-33"), MPID("mp-2134234"), MPID(33), MPID("33")]
    ) == MPID("mp-33")

    assert (
        len(set([MPID("mp-33"), MPID("mp-44545"), MPID("mp-33"), MPID("mp-2134234")]))
        == 3
    )

    MPID(3)


def test_to_str():
    assert str(MPID("mp-149")) == "mp-149"
