import pytest

from emmet.api.utils import process_identifiers


def test_process_ids():
    for test_data, ref_data, use_prefix in [
        ("mp-13, mp-149,77", ["mp-aaaaaaan", "mp-aaaaaaft", "mp-aaaaaacz"], True),
        ("1000000000", ["adgehtym"], False),
        ("1000000000,abcdefg", ["mp-adgehtym", "mp-aabcdefg"], True),
    ]:
        assert process_identifiers(test_data, use_prefix=use_prefix) == ref_data


@pytest.mark.parametrize("use_prefix", [True, False])
def test_process_ids_strict_accepts(use_prefix: bool):
    for test_data in (
        "mp-13, mp-149,77",
        "mp-149,ft, aaaaaaft ,mp-aaaaaaft",
        "",
        "149",
    ):
        assert process_identifiers(
            test_data, use_prefix=use_prefix, strict=True
        ) == process_identifiers(test_data, use_prefix=use_prefix)


@pytest.mark.parametrize(
    "test_data",
    [
        "fake-149",
        "mp-149,fake-149",
        "task-1",
        "mvc-13",
        "mp_ft",
        "mp:ft",
        "mp-",
        "-ft",
        "MP-149",
        "mp-149,",  # trailing comma -> empty id
    ],
)
def test_process_ids_strict_rejects(test_data: str):
    with pytest.raises(ValueError, match="Invalid identifier"):
        process_identifiers(test_data, strict=True)


def test_process_ids_lenient_unchanged():
    for test_data in ("fake-149", "149", "ft", "mp-ft"):
        assert process_identifiers(test_data) == ["mp-aaaaaaft"]
        assert process_identifiers(test_data, strict=False) == ["mp-aaaaaaft"]


def test_process_ids_strict_reports_all_invalid():
    with pytest.raises(ValueError) as exc_info:
        process_identifiers("mp-149, fake-149, task-1, mp-ft", strict=True)
    msg = str(exc_info.value)
    assert "'fake-149'" in msg and "'task-1'" in msg
    assert "mp-149" not in msg.replace("fake-149", "")


def test_process_ids_strict_allowed_prefixes():
    assert process_identifiers(
        "mvc-13", strict=True, allowed_prefixes={"mp", "mvc"}
    ) == ["mp-aaaaaaan"]
    with pytest.raises(ValueError, match="prefix 'mp' is not one of"):
        process_identifiers("mp-149", strict=True, allowed_prefixes=())
