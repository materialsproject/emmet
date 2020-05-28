# coding: utf-8
"""
This modules defines a base class of a calculation database
"""

import re
import logging

from datetime import datetime
from typing import Dict, List, Union, Tuple
from abc import ABCMeta, abstractmethod
from pydash.objects import has, get, unset

from monty.json import MSONable
from monty.serialization import loadfn
from maggma.stores import Store, MongoStore

from emmet.core.utils import jsanitize

logger = logging.getLogger("emmet")


class KeyTransformer(MSONable, metaclass=ABCMeta):
    @abstractmethod
    def get_max(self, keys: List):
        pass

    @abstractmethod
    def to_key(self, id):
        pass


class MPKeyTransformer(KeyTransformer):

    _to_id = re.compile(r"mp-(\d*)")
    _to_key = "mp-{}"

    def get_max(self, keys: List):
        ids = []

        for key in keys:
            try:
                _id = int(self._to_id.search(key).group(1))
            except IndexError:
                _id = 0
            finally:
                ids.append(_id)

        ids = ids if len(ids) > 0 else [0]
        return max(ids)

    def to_key(self, id: List):
        return self._to_key.format(id)


class CalcDB(MSONable, metaclass=ABCMeta):
    def __init__(
        self,
        documents: MongoStore,
        data: Store,
        key_regex: KeyTransformer = MPKeyTransformer(),
        doc_keys: Dict[str, str] = {
            "bandstructure": "calcs_reversed.0.bandstructure",
            "dos": "calcs_reversed.0.dos",
        },
        removed_keys: List[str] = [
            "calcs_reversed.1.bandstructure",
            "calcs_reversed.2.bandstructure",
            "calcs_reversed.1.dos",
            "calcs_reversed.2.dos",
        ],
    ):

        self.documents = documents
        self.data = data
        self.key_regex = key_regex  # TODO: Make this a transformer class
        self.doc_keys = doc_keys
        self.removed_keys = removed_keys

        self._key_name = self.documents.key

    def build_indexes(self, indexes=None, background=True):
        """
         Build the indexes.
         Args:
             indexes (list): list of single field indexes to be built.
             background (bool): Run in the background or not.
         """
        self.documents.connect()
        self.data.connect()

        self.documents.ensure_index("task_id")
        self.documents.ensure_index("last_updated")
        self.documents.ensure_index("dir_name")

        self.documents.ensure_index("task_id")
        self.documents.ensure_index("last_updated")
        self.documents.ensure_index("type")

    def insert(self, tasks: Union[Dict, List[Dict]], update_duplicates=False):
        """
        Insert the task documents to the documents store
        Args:
            d (dict): task document
            update_duplicates (bool): whether to update the duplicates
        """

        self.documents.connect()
        self.data.connect()
        self.build_indexes()

        tasks = [tasks] if isinstance(tasks, Dict) else tasks

        result = {
            d["dir_name"]: d[self._key_name]
            for d in self.documents.query(
                {"dir_name": {"$in": [d["dir_name"] for d in tasks]}},
                ["dir_name", self._key_name],
            )
        }

        # Group by new items vs replacements
        to_update = []  # needs task_ids assigned
        to_replace = []  # can just be inserted into the DB
        for doc in tasks:
            doc["last_updated"] = datetime.utcnow()
            if "task_id" in doc:  # Forcing a task_id
                to_replace.append(jsanitize(doc, allow_bson=True))
            elif doc["dir_name"] not in result:
                to_update.append(jsanitize(doc, allow_bson=True))
            elif update_duplicates:
                doc["task_id"] = result[doc["dir_name"]]
                logger.info(
                    "Updating {} with taskid = {}".format(
                        doc["dir_name"], doc["task_id"]
                    )
                )
                to_replace.append(jsanitize(doc, allow_bson=True))

        all_task_ids = self.documents.distinct("task_id")
        max_tid = self.key_regex.get_max(all_task_ids)

        seperator_tid = max_tid + len(to_update)
        next_tid = max_tid + 1
        self.documents.update(
            {"task_id": self.key_regex.to_key(seperator_tid)}, key="task_id"
        )
        logger.debug(f"Inserted separator task with task_id {seperator_tid}.")

        all_task_ids = self.documents.distinct("task_id")
        max_tid = self.key_regex.get_max(all_task_ids)

        assert (
            max_tid == seperator_tid
        ), f"Failed reserving block of {len(to_update)} task_ids"
        for d in to_update:
            if "task_id" not in d:  # Not forcing a task_id
                d["task_id"] = self.key_regex.to_key(next_tid)
                next_tid += 1

        data = self.extract_data(to_update + to_replace)
        self.documents.update(to_update, key="task_id")
        self.documents.update(to_replace, key="task_id")
        self.data.update(data, key=["task_id", "type"])

        return to_update + to_replace

    def extract_data(self, docs) -> List[Dict]:
        """
        Extracts the data blobs in-place, removing them from the provided documents
        """

        data = []

        for d in docs:
            for doc_type, path in self.doc_keys.items():
                if has(d, path):
                    new_blob = get(d, path)
                    if not isinstance(new_blob, dict):
                        new_blob = {"data": new_blob}

                    new_blob["type"] = doc_type
                    new_blob["task_id"] = d["task_id"]
                    new_blob["last_updated"] = d["last_updated"]
                    data.append(new_blob)
                    unset(d, path)
            for path in self.removed_keys:
                unset(d, path)
        return data
