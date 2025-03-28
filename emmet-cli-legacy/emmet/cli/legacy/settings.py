from datetime import datetime
from typing import Dict, List

from pydantic import Field

from emmet.core.settings import EmmetSettings


class EmmetCLISettings(EmmetSettings):
    exclude: Dict[str, Dict] = Field(
        {
            "about.remarks": {"$nin": ["DEPRECATED", "deprecated"]},
            "snl.about.remarks": {"$nin": ["DEPRECATED", "deprecated"]},
        },
        description="",
    )
    skip_labels: List[str] = Field(
        ["He", "He0+", "Ar", "Ar0+", "Ne", "Ne0+", "D", "D+", "T", "M"], description=""
    )
    base_query: Dict = Field(
        {
            "is_ordered": True,
            "is_valid": True,
            "nsites": {"$lt": 200},
            "sites.label": {"$nin": skip_labels},
            "snl.sites.label": {"$nin": skip_labels},
        },
        description="",
    )
    task_base_query: Dict = Field(
        {
            "tags": {"$nin": ["DEPRECATED", "deprecated"]},
            "_mpworks_meta": {"$exists": 0},
        },
        description="",
    )

    aggregation_keys: List[str] = Field(
        ["formula_pretty", "reduced_cell_formula"], description=""
    )

    meta_keys: List[str] = Field(
        ["formula_pretty", "nelements", "nsites", "is_ordered", "is_valid"],
        description="",
    )
    structure_keys: Dict[bool, List[str]] = Field(
        {
            False: [
                "snl_id",
                "lattice",
                "sites",
                "charge",
                "about._materialsproject.task_id",
            ],  # default
            True: [
                "task_id",
                "snl.lattice",
                "snl.sites",
                "snl.charge",
            ],  # for mp_core.snls (nested snl)
        },
        description="",
    )
    NO_POTCARS: List[str] = Field(
        [
            "Po",
            "At",
            "Rn",
            "Fr",
            "Ra",
            "Am",
            "Cm",
            "Bk",
            "Cf",
            "Es",
            "Fm",
            "Md",
            "No",
            "Lr",
        ],
        description="",
    )
    snl_indexes: List[str] = Field(
        [
            "snl_id",
            "task_id",
            "reduced_cell_formula",
            "formula_pretty",
            "nsites",
            "nelements",
            "is_ordered",
            "is_valid",
            "about.remarks",
            "about.projects",
            "sites.label",
            "snl.about.remarks",
            "snl.about.projects",
            "snl.sites.label",
        ],
        description="",
    )
    log_fields: List[str] = Field(
        [
            "level",
            "message",
            "snl_id",
            "formula",
            "tags",
            "spacegroup",
            "task_id",
            "duplicate_id",
            "source_id",
            "fw_id",
            "duplicate_dbname",
        ],
        description="",
    )

    tracker: Dict[str, str] = Field(
        {"org": "materialsproject", "repo": "devops"}, description=""
    )

    year_tags: List[str] = Field(
        ["mp_{}".format(y) for y in range(2018, int(datetime.today().year) + 1)],
        description="list of years to tag tasks",
    )
