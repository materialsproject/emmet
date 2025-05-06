""" Instantiate database objects for emmet cli. """
from __future__ import annotations
from bson import ObjectId
import json
import logging
from maggma.core import Store
from maggma.stores import GridFSStore, MongoStore, MongoURIStore, S3Store
from monty.json import jsanitize, MontyDecoder, MontyEncoder
from pymongo import ReturnDocument
from typing import Literal, TYPE_CHECKING, Union, Optional
import zlib

from emmet.core.utils import utcnow

if TYPE_CHECKING:
    from emmet.core.tasks import TaskDoc
    from typing import Any

logger = logging.getLogger("emmet")


class TaskStore:
    _get_store_from_type: dict[str, Store] = {
        "mongo": MongoStore,
        "s3": S3Store,
        "gridfs": GridFSStore,
        "mongo_uri": MongoURIStore,
    }

    _object_names: tuple[str, ...] = (
        "dos",
        "bandstructure",
        "chgcar",
        "locpot",
        "aeccar0",
        "aeccar1",
        "aeccar2",
        "elfcar",
    )

    def __init__(
        self,
        store_kwargs: dict,
        store_type: Optional[Literal["mongo", "s3", "gridfs", "mongo_uri"]] = None,
    ) -> None:
        self._store_kwargs = store_kwargs
        self._store_type = store_type

        if all(
            store_kwargs.get(k)
            for k in (
                "@module",
                "@class",
            )
        ):
            self.store = MontyDecoder().process_decoded(store_kwargs)

        elif store_type and self._get_store_from_type.get(store_type):
            store = self._get_store_from_type[store_type]
            store_kwargs = {
                k: v
                for k, v in store_kwargs.items()
                if k
                in Store.__init__.__code__.co_varnames
                + store.__init__.__code__.co_varnames
            }
            self.store = store(**store_kwargs)
        else:
            raise ValueError("TaskStore cannot construct desired store!")

        self.store.connect()
        self.db = self.store._coll
        self.collection = self.db[store_kwargs.get("collection")]

        self.large_data_store = None
        if isinstance(self.store, (MongoStore, MongoURIStore)):
            gridfs_store_kwargs = store_kwargs.copy()
            gridfs_store_kwargs["collection_name"] = gridfs_store_kwargs.get(
                "gridfs_collection", gridfs_store_kwargs["collection_name"]
            )
            self.large_data_store = GridFSStore(**gridfs_store_kwargs)

        elif isinstance(self.store, S3Store):
            self.large_data_store = self.store

        if self.large_data_store:
            self.large_data_store.connect()
            self.large_data_db = self.large_data_store._coll

    @classmethod
    def from_db_file(cls, db_file) -> TaskStore:
        from monty.serialization import loadfn

        store_kwargs = loadfn(db_file, cls=None)
        if store_kwargs.get("collection") and not store_kwargs.get("collection_name"):
            store_kwargs["collection_name"] = store_kwargs["collection"]

        store_kwargs.pop("aliases", None)

        if not all(store_kwargs.get(key) for key in ("username", "password")):
            for mode in ("admin", "readonly"):
                if all(
                    store_kwargs.get(f"{mode}_{key}") for key in ("user", "password")
                ):
                    store_kwargs["username"] = store_kwargs[f"{mode}_user"]
                    store_kwargs["password"] = store_kwargs[f"{mode}_password"]
                    break

        return cls(store_kwargs, store_type="mongo")

    def insert(self, dct: dict, update_duplicates: bool = True) -> Union[str | None]:
        """
        Insert the task document to the database collection.

        Args:
            dct (dict): task document
            update_duplicates (bool): whether to update the duplicates
        """

        result = self.collection.find_one(
            {"dir_name": dct["dir_name"]}, ["dir_name", "task_id"]
        )
        if result is None or update_duplicates:
            dct["last_updated"] = utcnow()
            if result is None:
                logger.info("No duplicate!")
                if ("task_id" not in dct) or (not dct["task_id"]):
                    dct["task_id"] = self.db.counter.find_one_and_update(
                        {"_id": "taskid"},
                        {"$inc": {"c": 1}},
                        return_document=ReturnDocument.AFTER,
                    )["c"]
                logger.info(
                    f"Inserting {dct['dir_name']} with taskid = {dct['task_id']}"
                )
            elif update_duplicates:
                dct["task_id"] = result["task_id"]
                logger.info(
                    f"Updating {dct['dir_name']} with taskid = {dct['task_id']}"
                )
            dct = jsanitize(dct, allow_bson=True)
            self.collection.update_one(
                {"dir_name": dct["dir_name"]}, {"$set": dct}, upsert=True
            )
            return dct["task_id"]

        else:
            logger.info(f"Skipping duplicate {dct['dir_name']}")

    def insert_task(self, task_doc: TaskDoc) -> int:
        """
        Inserts a TaskDoc into the database.
        Handles putting DOS, band structure and charge density into GridFS as needed.
        During testing, a percentage of runs on some clusters had corrupted AECCAR files
        when even if everything else about the calculation looked OK.
        So we do a quick check here and only record the AECCARs if they are valid

        Args:
            task_doc (dict): the task document
        Returns:
            (int) - task_id of inserted document
        """

        big_data_to_store = {}

        def extract_from_calcs_reversed(obj_key: str) -> Any:
            """
            Grab the data from calcs_reversed.0.obj_key and store on gridfs directly or some Maggma store
            Args:
                obj_key: Key of the data in calcs_reversed.0 to store
            """
            calcs_r_data = task_doc["calcs_reversed"][0][obj_key]

            # remove the big object from all calcs_reversed
            # this can catch situations where the drone added the data to more than one calc.
            for i_calcs in range(len(task_doc["calcs_reversed"])):
                if obj_key in task_doc["calcs_reversed"][i_calcs]:
                    del task_doc["calcs_reversed"][i_calcs][obj_key]
            return calcs_r_data

        # drop the data from the task_document and keep them in a separate dictionary (big_data_to_store)
        if self.large_data_store and task_doc.get("calcs_reversed"):
            for data_key in self._object_names:
                if data_key in task_doc["calcs_reversed"][0]:
                    big_data_to_store[data_key] = extract_from_calcs_reversed(data_key)

        # insert the task document
        t_id = self.insert(task_doc)

        if "calcs_reversed" in task_doc:
            # upload the data to a particular location and store the reference to that location in the task database
            for data_key, data_val in big_data_to_store.items():
                fs_di_, compression_type_ = self.insert_object(
                    dct=data_val,
                    collection=f"{data_key}_fs",
                    task_id=t_id,
                )
                self.collection.update_one(
                    {"task_id": t_id},
                    {
                        "$set": {
                            f"calcs_reversed.0.{data_key}_compression": compression_type_
                        }
                    },
                )
                self.collection.update_one(
                    {"task_id": t_id},
                    {"$set": {f"calcs_reversed.0.{data_key}_fs_id": fs_di_}},
                )
        return t_id

    def insert_object(self, *args, **kwargs) -> tuple[int, str]:
        """Insert the object into big object storage, try maggma_store if
            it is available, if not try storing directly to girdfs.

        Returns:
            fs_id: The id of the stored object
            compression_type: The compress method of the stored object
        """
        if isinstance(self.large_data_store, GridFSStore):
            return self.insert_gridfs(*args, **kwargs)
        else:
            return self.insert_maggma_store(*args, **kwargs)

    def insert_gridfs(
        self,
        dct: dict,
        compression_type: Optional[Literal["zlib"]] = "zlib",
        oid: Optional[ObjectId] = None,
        task_id: Optional[Union[int, str]] = None,
    ) -> tuple[int, str]:
        """
        Insert the given document into GridFS.

        Args:
            dct (dict): the document
            collection (string): the GridFS collection name
            compression_type (str = Literal["zlib"]or None) : Whether to compress the data using a known compressor
            oid (ObjectId()): the _id of the file; if specified, it must not already exist in GridFS
            task_id(int or str): the task_id to store into the gridfs metadata
        Returns:
            file id, the type of compression used.
        """
        oid = oid or ObjectId()
        if isinstance(oid, ObjectId):
            oid = str(oid)

        # always perform the string conversion when inserting directly to gridfs
        dct = json.dumps(dct, cls=MontyEncoder)
        if compression_type == "zlib":
            d = zlib.compress(dct.encode())

        metadata = {"compression": compression_type}
        if task_id:
            metadata["task_id"] = task_id
        # Putting task id in the metadata subdocument as per mongo specs:
        # https://github.com/mongodb/specifications/blob/master/source/gridfs/gridfs-spec.rst#terms
        fs_id = self.large_data_db.put(d, _id=oid, metadata=metadata)

        return fs_id, compression_type

    def insert_maggma_store(
        self,
        dct: Any,
        collection: str,
        oid: Optional[Union[str, ObjectId]] = None,
        task_id: Optional[Any] = None,
    ) -> tuple[int, str]:
        """
        Insert the given document into a Maggma store.

        Args:
            data: the document to be stored
            collection (string): the name prefix for the maggma store
            oid (str, ObjectId, None): the _id of the file; if specified, it must not already exist in GridFS
            task_id(int or str): the task_id to store into the gridfs metadata
        Returns:
            file id, the type of compression used.
        """
        oid = oid or ObjectId()
        if isinstance(oid, ObjectId):
            oid = str(oid)

        compression_type = None

        doc = {
            "fs_id": oid,
            "maggma_store_type": self.get_store(collection).__class__.__name__,
            "compression": compression_type,
            "data": dct,
        }

        search_keys = [
            "fs_id",
        ]

        if task_id is not None:
            search_keys.append("task_id")
            doc["task_id"] = str(task_id)
        elif isinstance(dct, dict) and "task_id" in dct:
            search_keys.append("task_id")
            doc["task_id"] = str(dct["task_id"])

        if getattr(self.large_data_store, "compression", False):
            compression_type = "zlib"
            doc["compression"] = "zlib"

        self.store.update([doc], search_keys)

        return oid, compression_type
