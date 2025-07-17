import os
from pathlib import Path
import requests
from emmet.core.mpid import AlphaID, VALID_ALPHA_SEPARATORS

GH_OBSCENITY = "https://raw.githubusercontent.com/LDNOOBW/List-of-Dirty-Naughty-Obscene-and-Otherwise-Bad-Words/master/"
LANGUAGES = [
    "ar",
    "cs",
    "da",
    "de",
    "en",
    "eo",
    "es",
    "fa",
    "fi",
    "fil",
    "fr",
    "fr-CA-u-sd-caqc",
    "hi",
    "hu",
    "it",
    "ja",
    "kab",
    "ko",
    "nl",
    "no",
    "pl",
    "pt",
    "ru",
    "sv",
    "th",
    "tlh",
    "tr",
    "zh",
]
DEFAULT_FILE = (
    Path(__file__).parent / ".." / "emmet" / "core" / "_forbidden_alpha_id.py"
)


def generate_exclude_list(
    github_url: str = GH_OBSCENITY,
    languages: list[str] = LANGUAGES,
    output_file: str | Path = DEFAULT_FILE,
) -> list[int]:
    """Generate a list of integers corresponding to multi-lingual obscene words.

    Parameters
    -----------
    github_url: str = GH_OBSCENITY
        The github repo URL to fetch obscene word lists from
    languages: list[str] = LANGUAGES
        The languages in the repo to select word lists for
    output_file: str | Path = DEFAULT_FILE
        The file to write the integer list to

    Returns
    -----------
    list of int
        AlphaID integer values of those words/phrases
    """

    obscene_alpha_ids = set()
    for lang in languages:
        for word in (
            requests.get(f"{os.path.join(github_url,lang)}")
            .content.decode()
            .splitlines()
        ):
            for sep in VALID_ALPHA_SEPARATORS | {" "}:
                word = word.replace(sep, "")

            alpha_id = None
            try:
                alpha_id = AlphaID(word)
            except Exception:
                continue

            # Only retain "obscene AlphaIDs" that
            # are longer than two characters, with leading "a"'s removed
            if len(AlphaID(int(alpha_id))) > 2:
                obscene_alpha_ids.update({alpha_id})

    if any(alpha_id._prefix for alpha_id in obscene_alpha_ids):
        badly_parsed = "\n".join(
            alpha_id._identifier for alpha_id in obscene_alpha_ids if alpha_id._prefix
        )
        raise ValueError(
            "None of the obscene AlphaIDs should have prefixes or separators. "
            "Please check the following strings, which have been parsed incorrectly:\n"
            f"{badly_parsed}"
        )

    obscene_alpha_id = sorted(obscene_alpha_ids)
    output_str = """\"\"\"Define AlphaID integer values which cannot be used.\"\"\"

FORBIDDEN_ALPHA_ID_VALUES : set[int] = {
"""
    output_str += (
        ",\n".join(f"   {int(alpha_id)}" for alpha_id in obscene_alpha_id) + "\n}"
    )

    with open(output_file, "w+") as f:
        f.write(output_str)

    return obscene_alpha_id


if __name__ == "__main__":

    _ = generate_exclude_list()
