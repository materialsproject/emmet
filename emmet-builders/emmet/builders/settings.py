"""
Settings for defaults in the build pipelines for the Materials Project
"""

from pydantic.fields import Field

from emmet.core.provenance import Author, History
from emmet.core.qchem.calc_types import TaskType as QChemTaskType
from emmet.core.settings import EmmetSettings
from emmet.core.vasp.calc_types import TaskType as VaspTaskType


class EmmetBuildSettings(EmmetSettings):
    """
    Settings for the emmet-builder module
    The default way to modify these is to modify ~/.emmet.json or set the environment variable
    EMMET_CONFIG_FILE to point to the json with emmet settings
    """

    BUILD_TAGS: list[str] = Field(
        [], description="Tags for calculations to build materials"
    )
    EXCLUDED_TAGS: list[str] = Field(
        [],
        description="Tags to exclude from materials",
    )

    DEPRECATED_TAGS: list[str] = Field(
        [], description="Tags for calculations to deprecate"
    )

    NON_COMMERCIAL_TAGS: list[str] = Field(
        [], description="Tages for which to add BY-NC as license data in builder_meta"
    )

    VASP_ALLOWED_VASP_TYPES: list[VaspTaskType] = Field(
        [t.value for t in VaspTaskType],
        description="Allowed task_types to build materials from",
    )

    QCHEM_ALLOWED_TASK_TYPES: list[QChemTaskType] = Field(
        [
            "Single Point",
            "Force",
            "Geometry Optimization",
            "Frequency Analysis",
            "Frequency Flattening Geometry Optimization",
        ],
        description="Allowed task_types to build molecules from",
    )

    DEFAULT_REFERENCE: str = Field(
        "@article{Jain2013,\nauthor = {Jain, Anubhav and Ong, Shyue Ping and "
        "Hautier, Geoffroy and Chen, Wei and Richards, William Davidson and "
        "Dacek, Stephen and Cholia, Shreyas and Gunter, Dan and Skinner, David "
        "and Ceder, Gerbrand and Persson, Kristin a.},\n"
        "doi = {10.1063/1.4812323},\nissn = {2166532X},\n"
        "journal = {APL Materials},\nnumber = {1},\npages = {011002},\n"
        "title = {{The Materials Project: A materials genome approach to "
        "accelerating materials innovation}},\n"
        "url = {http://link.aip.org/link/AMPADS/v1/i1/p011002/s1\\&Agg=doi},\n"
        "volume = {1},\nyear = {2013}\n}\n\n@misc{MaterialsProject,\n"
        "title = {{Materials Project}},\nurl = {http://www.materialsproject.org}\n}",
        description="Default bibtex citation for all provenance",
    )

    DEFAULT_AUTHOR: Author = Field(
        Author(name="Materials Project", email="feedback@materialsproject.org"),
        description="Default Author for provenance ",
    )

    DEFAULT_HISTORY: History = Field(
        History(
            name="Materials Project Optimized Structure",
            url="http://www.materialsproject.org",
        ),
        description="Default History for provenance ",
    )
