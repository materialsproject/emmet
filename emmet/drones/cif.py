import logging
import warnings
import re
from pathlib import Path
from typing import Dict, List, Union
from datetime import datetime
from timestring import Date

from atomate.utils.utils import get_meta_from_structure
from monty.json import MSONable
from monty.serialization import loadfn

from pymatgen import Composition, Structure
from pymatgen.io.cif import CifParser


db_urls = {
    "icsd": "https://icsd.fiz-karlsruhe.de/",
    "cod": "http://www.crystallography.net/cod/",
}


class CIFDrone(MSONable):
    def __init__(self, convert_H_isotopes: bool = True, default_user_meta: Path = None):
        """
        Args:
            convert_H_isotopes: Converts Hydrogen Isotopes to Hydrogen
            read_meta_json: reads corresponding JSON files with the same name as additional metadata
            default_user_meta: Path to a JSON file of user metadata to apply to all entries
        """
        self.logger = logging.getLogger(__name__)
        self.convert_H_isotopes = convert_H_isotopes
        self.default_user_meta = default_user_meta

        self._default_user_meta_dict = (
            loadfn(default_user_meta) if default_user_meta else {}
        )

    def assimilate(self, cif_path: Path) -> List[Dict]:
        """
        Assimilate a CIF File and associated JSON
        """
        cif_path = Path(cif_path)

        cif_dict = self._read_cif(cif_path)
        user_meta = self._get_user_meta(cif_path)

        structures = cif_dict["structures"]
        cif_data = cif_dict["cif_data"]

        for struc, data in zip(structures, cif_data):
            struc.remove_oxidation_states()
            metadata = self._analyze_cif_dict(data)
            authors = self._find_authors(data)
            history = self._get_db_history(data)
            composition = data["_chemical_formula_sum"]
            struc_metadata = self._analyze_struc(struc, composition)

            doc_meta = dict(**self._default_user_meta_dict)
            doc_meta.update(user_meta)
            doc_meta.update(metadata)
            doc_meta.update(struc_metadata)

            if self.convert_H_isotopes and struc_metadata["contains_H_isotopes"]:
                doc_meta["reaplced_H_isotopes"] = self._fix_H_isotopes(struc)

            doc = {
                "structure": struc,
                "authors": authors,
                "reference": cif_dict["reference"],
                "history": history,
                "meta": doc_meta,
                "warnings": cif_dict["warnings"],
                "experimental": self._determine_experimental(user_meta, data),
                "created_at": self._get_created_date(data),
            }

            doc.update(get_meta_from_structure(struc))
            yield doc

    def _read_cif(self, cif_path: Path) -> Dict:
        """
        Internal function to convert CIF into a structure + metadata
        """

        file_ID = cif_path.stem
        cif_dict = {"warnings": []}
        with warnings.catch_warnings(record=True) as w:
            cif_parser = CifParser(cif_path)
            cif_dict["structures"] = cif_parser.get_structures()
            cif_dict["reference"] = cif_parser.get_bibtex_string()
            cif_dict["cif_data"] = list(cif_parser.as_dict().values())
            cif_dict["nstructures"] = len(cif_dict["structures"])
            for warn in w:
                cif_dict["warnings"].append(str(warn.message))
                self.logger.warning("{}: {}".format(file_ID, warn.message))

        return cif_dict

    def _analyze_cif_dict(self, cif_data: Dict) -> Dict:
        """
        Builds a metadata dictionary from values within the CIF itself
        """
        metadata = {}
        tags = []
        if "_chemical_name_mineral" in cif_data:
            metadata["min_name"] = cif_data["_chemical_name_mineral"]
            tags.append(metadata["min_name"])
        if "_chemical_name_systematic" in cif_data:
            metadata["chem_name"] = cif_data["_chemical_name_systematic"]
            tags.append(metadata["chem_name"])
        if "_cell_measurement_pressure" in cif_data:
            metadata["pressure"] = float(cif_data["_cell_measurement_pressure"]) / 1000
        else:
            metadata["pressure"] = 0.101325

        if metadata["pressure"] > 0.101324:
            tags.append("High Presure")

        metadata["tags"] = tags

        return metadata

    def _get_db_history(self, cif_data: Dict) -> Dict:
        """
        Gets the database history from the CIF
        """

        db_keys = [k for k in cif_data.keys() if "_database_code" in k]
        db_regex = r"_?(.*)_database_code_?(.*)"
        db_matches = [re.match(db_regex, k) for k in db_keys]
        db_names = [match[1] if match[1] else match[2] for match in db_matches]

        history = []

        for name, key in zip(db_names, db_keys):

            history.append(
                {
                    "name": name,
                    "url": db_urls[name.lower()],
                    "description": {"id": cif_data[key]},
                }
            )
        return history

    def _analyze_struc(
        self, struc: Structure, actual_composition: Union[Composition, str, None] = None
    ) -> Dict:
        """
        Builds a metadata dictionary by analyzing the structure from the CIF
        """

        metadata = {}
        species_string = [
            re.findall(r"[A-z]+", s.species_string)[0] for s in struc.sites
        ]
        contains_H_isotopes = any([s == "D" or s == "T" for s in species_string])

        metadata["contains_H_isotopes"] = contains_H_isotopes

        structure_composition = struc.composition.remove_charges().reduced_composition

        if actual_composition is not None:
            if not isinstance(actual_composition, Composition):
                actual_composition = Composition(actual_composition).reduced_composition

            metadata["consistent_composition"] = structure_composition.almost_equals(
                actual_composition
            )
            metadata["implicit_hydrogen"] = (
                abs(
                    sum(
                        [
                            structure_composition[el] - actual_composition[el]
                            for el in ["H", "D", "T"]
                        ]
                    )
                )
                > 0.1
            )

        return metadata

    def _get_user_meta(self, cif_path: Path) -> Dict:
        file_ID = cif_path.stem
        meta_paths = [
            path for path in cif_path.parent.glob(f"{file_ID}*") if path != cif_path
        ]
        meta_doc = {}
        for path in meta_paths:
            meta_doc.update(loadfn(path))

        return meta_doc

    def _fix_H_isotopes(self, struc: Structure) -> bool:
        """
        Replaces hydrogen isotopes
        """
        species_string = [
            re.findall(r"[A-z]+", s.species_string)[0] for s in struc.sites
        ]
        H_isotopes = [
            site.species_string
            for s, site in zip(species_string, struc.sites)
            if s == "D" or s == "T"
        ]

        if len(H_isotopes) > 0:
            struc.replace_species({s: "H" for s in H_isotopes})
            return True
        return False

    def _find_authors(self, cif_data):
        """
        Gets authors from cif_data
        making this a function since this could be much better
        """
        return [{"name": name, "email": ""} for name in cif_data["_publ_author_name"]]

    def _get_created_date(self, cif_data: Dict) -> datetime:
        """
        Find the creation date
        """

        date_fields = [
            "_audit_creation_date",
            "_audit_update_record",
            "_citation_year",
            "_journal_year",
        ]

        dates = [Date(cif_data[k]).date for k in date_fields if k in cif_data]
        if len(dates) > 0:
            return dates[0]
        else:
            return datetime.now()

    def _determine_experimental(self, user_meta: Dict, cif_data: Dict) -> bool:
        """
        Determines if the CIF is experimental from user tags and data from
        the CIF
        """
        return any(
            [
                user_meta.get("experimental", False),  # MP Tag for various sources
                user_meta.get("experimental_PDF_number", False),  # ICSD Crawler
            ]
        )
