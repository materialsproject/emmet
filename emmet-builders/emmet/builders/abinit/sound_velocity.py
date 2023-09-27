import tempfile
import traceback
from math import ceil
from maggma.utils import grouper
from typing import Optional, Dict, List, Iterator

from abipy.dfpt.vsound import SoundVelocity as AbiSoundVelocity
from abipy.dfpt.ddb import DdbFile
from maggma.builders import Builder
from maggma.core import Store
from abipy.flowtk.tasks import TaskManager

from emmet.core.phonon import SoundVelocity
from emmet.core.utils import jsanitize


class SoundVelocityBuilder(Builder):
    def __init__(
        self,
        phonon_materials: Store,
        ddb_source: Store,
        sound_vel: Store,
        query: Optional[dict] = None,
        manager: Optional[TaskManager] = None,
        **kwargs
    ):
        """
        Creates a collection with the data of the sound velocities extracted from
        the phonon calculations.

        Args:
            phonon_materials (Store): source Store of phonon materials documents
                containing abinit_input and abinit_output.
            ddb_source (Store): source Store of ddb files. Matching the data in the materials Store.
            sound_vel (Store): target Store of the sound velocity
            query (dict): dictionary to limit materials to be analyzed
            manager (TaskManager): an instance of the abipy TaskManager. If None it will be
                generated from user configuration.
        """

        self.phonon_materials = phonon_materials
        self.ddb_source = ddb_source
        self.sound_vel = sound_vel
        self.query = query or {}

        if manager is None:
            self.manager = TaskManager.from_user_config()
        else:
            self.manager = manager

        super().__init__(
            sources=[phonon_materials, ddb_source], targets=[sound_vel], **kwargs
        )

    def prechunk(self, number_splits: int):  # pragma: no cover
        """
        Gets all materials that need sound velocity

        Returns:
            generator of materials to extract phonon sound velocity
        """

        # All relevant materials that have been updated since phonon props were last calculated
        q = dict(self.query)

        mats = self.sound_vel.newer_in(
            self.phonon_materials, exhaustive=True, criteria=q
        )

        N = ceil(len(mats) / number_splits)

        for mpid_chunk in grouper(mats, N):
            yield {"query": {self.phonon_materials.key: {"$in": list(mpid_chunk)}}}

    def get_items(self) -> Iterator[Dict]:
        """
        Gets all materials that need sound velocity.

        Returns:
            generator of materials to extract the sound velocity
        """

        self.logger.info("Sound Velocity Builder Started")

        self.logger.info("Setting indexes")
        self.ensure_indexes()

        # All relevant materials that have been updated since sound velocities were last calculated
        q = dict(self.query)
        mats = self.sound_vel.newer_in(
            self.phonon_materials, exhaustive=True, criteria=q
        )
        self.logger.info(
            "Found {} new materials for sound velocity data".format(len(mats))
        )

        # list of properties queried from the results DB
        # basic informations
        projection = {"mp_id": 1}
        # input data
        projection["abinit_input"] = 1
        # file ids to be fetched
        projection["abinit_output.ddb_id"] = 1

        for m in mats:
            item = self.phonon_materials.query_one(
                properties=projection, criteria={self.phonon_materials.key: m}
            )

            # Read the DDB file and pass as an object. Do not write here since in case of parallel
            # execution each worker will write its own file.
            ddb_data = self.ddb_source.query_one(
                criteria={"_id": item["abinit_output"]["ddb_id"]}
            )

            item["ddb_str"] = ddb_data["data"].decode("utf-8")

            yield item

    def process_item(self, item: Dict) -> Optional[Dict]:
        """
        Generates the sound velocity document from an item

        Args:
            item (dict): a dict extracted from the phonon calculations results.

        Returns:
            dict: a dict with phonon data
        """
        self.logger.debug("Processing sound velocity item for {}".format(item["mp_id"]))

        try:
            sound_vel_data = self.get_sound_vel(item)

            sv = SoundVelocity(
                material_id=item["mp_id"],
                structure=sound_vel_data["structure"],
                directions=sound_vel_data["directions"],
                labels=sound_vel_data["labels"],
                sound_velocities=sound_vel_data["sound_velocities"],
                mode_types=sound_vel_data["mode_types"],
            )

            self.logger.debug("Item generated for {}".format(item["mp_id"]))

            return jsanitize(sv.model_dump())
        except Exception:
            self.logger.warning(
                "Error generating the sound velocity for {}: {}".format(
                    item["mp_id"], traceback.format_exc()
                )
            )
            return None

    @staticmethod
    def get_sound_vel(item: Dict) -> Dict:
        """
        Runs anaddb and return the extracted data for the speed of sound.

        Args:
            item (dict): the item to process
        Returns:
            A dictionary with the sound velocity values
        """
        with tempfile.NamedTemporaryFile(
            mode="wt", suffix="_DDB", delete=True
        ) as ddb_file:
            ddb_file.write(item["ddb_str"])
            ngqpt = item["abinit_input"]["ngqpt"]
            sv = AbiSoundVelocity.from_ddb(
                ddb_file.name,
                ngqpt=ngqpt,
                num_points=20,
                qpt_norm=0.1,
                ignore_neg_freqs=True,
                directions=None,
            )

            ddb = DdbFile.from_string(item["ddb_str"])
            sv_data = dict(
                directions=sv.directions.tolist(),
                sound_velocities=sv.sound_velocities.tolist(),
                mode_types=sv.mode_types,
                labels=sv.labels,
                structure=ddb.structure,
            )

            return sv_data

    def update_targets(self, items: List[Dict]):
        """
        Inserts the new task_types into the task_types collection

        Args:
            items ([dict]): a list of dictionaries with sound velocities
                to update.
        """
        self.logger.debug("Start update_targets")
        items = list(filter(None, items))

        if len(items) > 0:
            self.logger.info("Updating {} sound velocity docs".format(len(items)))
            self.sound_vel.update(docs=items)
        else:
            self.logger.info("No items to update")

    def ensure_indexes(self):
        """
        Ensures indexes on the sound_vel collection.
        """

        # Search index for sound velocity
        self.sound_vel.ensure_index(self.sound_vel.key, unique=True)
