from emmet.core.tasks import TaskDoc
from emmet.core.vasp.validation import ValidationDoc

# As the validator itself is a separate package with its own tests,
# only check that its integration within emmet-core works.


def test_validator_integration(test_dir):
    calc_dirs = {
        "Si_old_double_relax": ["VASP VERSION"],
        "Si_uniform": [],
        "Si_static": [],
    }
    for calc_dir, ref_reasons in calc_dirs.items():
        task_doc = TaskDoc.from_directory(test_dir / "vasp" / calc_dir)
        valid_doc = ValidationDoc.from_task_doc(task_doc, check_potcar=False)
        if len(ref_reasons) == 0:
            assert valid_doc.valid
        else:
            assert not valid_doc.valid
            assert all(
                any(reason_match in reason for reason in valid_doc.reasons)
                for reason_match in ref_reasons
            )
