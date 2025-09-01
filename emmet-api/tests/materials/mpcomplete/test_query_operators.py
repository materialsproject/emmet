import os
from emmet.api.routes.materials.mpcomplete.query_operator import (
    MPCompleteGetQuery,
    MPCompletePostQuery,
)
from emmet.api.core.settings import MAPISettings

from pymatgen.core.structure import Structure


def test_mpcomplete_post_query():
    op = MPCompletePostQuery()

    structure = Structure.from_file(
        os.path.join(MAPISettings().TEST_FILES, "Si_mp_149.cif"), primitive=True
    )

    q = {
        "criteria": {
            "structure": structure.as_dict(),
            "public_name": "Test Test",
            "public_email": "test@test.com",
        }
    }

    assert (
        op.query(
            structure=structure.as_dict(),
            public_name="Test Test",
            public_email="test@test.com",
        )
        == q
    )

    docs = [
        {
            "structure": structure.as_dict(),
            "public_name": "Test Test",
            "public_email": "test@test.com",
        }
    ]
    assert op.post_process(docs, q) == docs


def test_mocomplete_get_query():
    op = MPCompleteGetQuery()

    assert op.query(
        public_name="Test Test",
        public_email="test@test.com",
    ) == {"criteria": {"public_name": "Test Test", "public_email": "test@test.com"}}
