from pathlib import Path
from monty.serialization import dumpfn

from emmet.core.types.enums import (
    DocEnum,
    ValueEnum,
)


def test_value_enum(tmp_path):
    class TempEnum(ValueEnum):
        A = "A"
        B = "B"

    assert str(TempEnum.A) == "A"
    assert str(TempEnum.B) == "B"

    dumpfn(TempEnum, tmp_path / "temp.json")
    assert Path(tmp_path, "temp.json").is_file()


def test_doc_enum():
    class TestEnum(DocEnum):
        A = "A", "Describes A"
        B = "B", "Might describe B"

    assert str(TestEnum.A) == "A"
    assert TestEnum.B.__doc__ == "Might describe B"
