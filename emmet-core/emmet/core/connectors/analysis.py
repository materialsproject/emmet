"""Tools for processing database CIFs."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout, nullcontext, contextmanager
from io import StringIO
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING

from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from pymatgen.core import Structure
from pymatgen.io.cif import CifParser, CifBlock

from emmet.core.settings import EmmetSettings

try:
    from pycodcif import parse as cod_tools_parse_cif
except ImportError:
    cod_tools_parse_cif = None

if TYPE_CHECKING:
    from contextlib import AbstractContextManager

EMMET_SETTINGS = EmmetSettings()


@contextmanager
def _get_context_manager(verbose: bool) -> AbstractContextManager:
    if verbose:
        yield nullcontext()
    else:
        with redirect_stderr(StringIO()) as stderr, redirect_stdout(
            StringIO()
        ) as stdout:
            yield stderr, stdout


def parse_cif_cod_tools(
    cif_str: str,
    verbose: bool = False,
    cif_parser: CifParser | None = None,
) -> tuple[list[Structure], list[str]]:
    """Parse a CIF with the COD tools parser.

    Parameters
    -----------
    cif_str : str
        The CIF string to parse
    verbose : bool = False
        Whether to pass error messages from pymatgen and CIF parsing tools.
        Defaults to suppressing these messages.
    cif_parser : pymatgen.io.cif.CifParser or None (default)
        Existing instance of a CifParser to use

    Returns
    -----------
    List of Structure if parsing is successful
    List of str documenting any parsing issues
    """

    structures: list[Structure] = []
    remarks: list[str] = []

    temp_file = NamedTemporaryFile(suffix=".cif")
    cif_data = []
    with open(temp_file.name, "w", encoding="utf-8") as f:
        # remove non-ASCII characters
        f.write(cif_str.encode("ascii", "ignore").decode("ascii"))
        f.seek(0)
    try:
        cif_data, _, _ = cod_tools_parse_cif(temp_file.name)
    except Exception as exc:
        remarks += [f"pycodcif.parse: {exc}"]

    temp_file.close()

    if cif_data:

        try:
            cif_parser = cif_parser or CifParser.from_str(cif_str)
            with _get_context_manager(verbose):
                structures += [
                    cif_parser._get_structure(
                        CifBlock(block["values"], block["loops"], block["name"]),
                        primitive=True,
                        symmetrized=False,
                        check_occu=True,
                    )
                    for block in cif_data
                ]
        except Exception as exc:
            remarks += [f"pycodcif/pymatgen: {exc}"]

    return structures, remarks


def remove_artificial_disorder(
    structures: list[Structure], in_place: bool = True
) -> list[Structure]:
    """Remove artificial disorder from a structure.

    Some of the ICSD CIFs are disordered in oxidation states only.
    Because these are assigned by hand and don't reflect
    actual chemical or configurational disorder, we
    remove this artificial disorder here.

    Parameters
    -----------
    structures : list of Structure
    in_place : bool = True
        Whether to modify `Structure`s in place

    Returns
    -----------
    list of Structure
    """
    output_structs = structures if in_place else [None] * len(structures)
    for idx, structure in enumerate(structures):
        if (
            not structure.is_ordered
            and (
                non_oxi_struct := Structure(
                    structure.lattice,
                    species=[site.species for site in structure],
                    coords=structure.frac_coords,
                    coords_are_cartesian=False,
                    charge=structure.charge,
                ).remove_oxidation_states()
            ).is_ordered
        ):
            output_structs[idx] = non_oxi_struct
    return output_structs


def remove_structures_with_fictive_elements(
    structures: list[Structure],
) -> list[Structure]:
    """Remove structures with fictive elements.

    This is used to ensure that a Structure contains only real elements.

    Sometimes, ICSD structures will use fictive elements to represent,
    e.g., cation substitution. Without a list of substituents,
    this is not useful for atomistic modelling.

    Parameters
    -----------
    structures : list of Structure

    Returns
    -----------
    list of Structure
    """
    output_structs = []
    for structure in structures:
        try:
            _ = structure.composition.remove_charges().as_dict()
            output_structs.append(structure)
        except Exception:
            continue
    return output_structs


def remove_structures_with_unphysical_symmetry(
    structures: list[Structure],
) -> list[Structure]:
    """Remove structures whose symmetry cannot be determined.

    Sometimes the distances between atoms in a CIF is
    unphysically small, or some other issue prevents symmetry
    determination of a CIF.

    Parameters
    -----------
    structures : list of Structure

    Returns
    -----------
    list of Structure
    """
    output_structures = []
    for structure in structures:
        try:
            sga = SpacegroupAnalyzer(
                structure,
                symprec=EMMET_SETTINGS.SYMPREC,
                angle_tolerance=EMMET_SETTINGS.ANGLE_TOL,
            )
            _ = sga.get_space_group_number()
            output_structures.append(structure)
        except Exception:
            continue
    return output_structures


def parse_cif(cif_str: str, verbose: bool = False) -> tuple[list[Structure], list[str]]:
    """Parse a CIF string and apply sanity checks.

    Parameters
    -----------
    cif_str : str
        The CIF string to parse
    verbose : bool = False
        Whether to pass error messages from pymatgen and CIF parsing tools.
        Defaults to suppressing these messages.

    Returns
    -----------
    List of Structure if parsing is successful
    List of str documenting any parsing issues
    """

    structures: list[Structure] = []
    remarks: list[str] = []

    cif_parser = CifParser.from_str(cif_str, check_cif=False)
    # Step 1: Try to parse with pymatgen without any changes to the CIF
    try:

        with _get_context_manager(verbose):
            structures = cif_parser.parse_structures(primitive=True)

    except Exception as exc:
        remarks.append(f"pymatgen.io.cif.CifParser: {exc}")

    # Step 2 (Optional): Use the Crystallography Open Database CIF parser
    # to correct errors in the CIF if the structures could not be parsed.
    if not structures and cod_tools_parse_cif:
        structures, new_remarks = parse_cif_cod_tools(
            cif_str, verbose=verbose, cif_parser=cif_parser
        )
        remarks.extend(new_remarks)

    # Step 3: Remove structures with fictive elements
    structures = remove_structures_with_fictive_elements(structures)

    # Step 4: Remove structures whose symmetry cannot be determined
    structures = remove_structures_with_unphysical_symmetry(structures)

    # Step 5: Check remaining CIFs with pymatgen CIF checker
    structures = [
        structure for structure in structures if (not cif_parser.check(structure))
    ]

    # Step 6: Remove artificial disorder in oxidation states
    return remove_artificial_disorder(structures), remarks
