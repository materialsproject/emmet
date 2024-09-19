import json
import logging

import pymongo
from pymongo import ReturnDocument

from emmet.core.tasks import TaskDoc
from emmet.core.utils import jsanitize, utcnow


class TaskStore:
    object_names: list[str] = [
        "dos",
        "bandstructure",
        "chgcar",
        "locpot",
        "aeccar0",
        "aeccar1",
        "aeccar2",
        "elfcar",
    ]

    def __init__(
        self,
        host: str,
        database: str,
        collection: str,
        username: str,
        password: str,
        authSource: str = None,
        protocol: str = "mongodb",
        object_store_auth={},
    ) -> None:
        self.mongo_uri = f"{protocol}://{username}:{password}@{host}"

        self.database = database
        self.collection = collection
        self.authSource = authSource or database
        self.object_store_auth = object_store_auth

        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)

        self.logger = logging.getLogger("TaskStore")
        self.logger.setLevel(logging.INFO)
        self.logger.addHandler(handler)

    @classmethod
    def from_db_file(cls, db_file):
        with open(db_file, "r") as f:
            store_kwargs = json.load(f)

        return cls(**store_kwargs)

    def insert(self, dct: dict, update_duplicates: bool = True) -> str | None:
        with pymongo.MongoClient(self.mongo_uri, authSource=self.authSource) as client:
            collection = client[self.database][self.collection]

            result = collection.find_one(
                {"dir_name": dct["dir_name"]}, ["dir_name", "task_id"]
            )
            if result is None or update_duplicates:
                dct["last_updated"] = utcnow()
                if result is None:
                    self.logger.info("No duplicate!")

                    if ("task_id" not in dct) or (not dct["task_id"]):
                        dct["task_id"] = collection.find_one_and_update(
                            {"_id": "taskid"},
                            {"$inc": {"c": 1}},
                            return_document=ReturnDocument.AFTER,
                        )["c"]
                    self.logger.info(
                        f"Inserting {dct['dir_name']} with taskid = {dct['task_id']}"
                    )
                elif update_duplicates:
                    dct["task_id"] = result["task_id"]
                    self.logger.info(
                        f"Updating {dct['dir_name']} with taskid = {dct['task_id']}"
                    )
                dct = jsanitize(dct, allow_bson=True)
                collection.update_one(
                    {"dir_name": dct["dir_name"]}, {"$set": dct}, upsert=True
                )
                return dct["task_id"]

            else:
                self.logger.info(f"Skipping duplicate {dct['dir_name']}")

    def insert_task(self, task_doc: TaskDoc) -> int:
        big_data_to_store = {}

        def extract_from_calcs_reversed(obj_key: str):
            calcs_r_data = task_doc["calcs_reversed"][0][obj_key]
            for i_calcs in range(len(task_doc["calcs_reversed"])):
                if obj_key in task_doc["calcs_reversed"][i_calcs]:
                    del task_doc["calcs_reversed"][i_calcs][obj_key]
            return calcs_r_data

        for data_key in self._object_names:
            if data_key in task_doc["calcs_reversed"][0]:
                big_data_to_store[data_key] = extract_from_calcs_reversed(data_key)

        task_id = self.insert(task_doc)

        # for data_key, data_val in big_data_to_store.items():
        #     fs_di_, compression_type_ = self.insert_object(
        #         dct=data_val,
        #         collection=f"{data_key}_fs",
        #         task_id=task_id,
        #     )
        #
        #     with pymongo.MongoClient(
        #         self.mongo_uri, authSource=self.authSource
        #     ) as client:
        #         collection = client[self.database][self.collection]
        #         collection.update_one(
        #             {"task_id": task_id},
        #             {
        #                 "$set": {
        #                     f"calcs_reversed.0.{data_key}_compression": compression_type_,
        #                     f"calcs_reversed.0.{data_key}_fs_id": fs_di_,
        #                 }
        #             },
        #         )

        return task_id

    def insert_object(**kwargs):
        pass
