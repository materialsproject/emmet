import traceback
from datetime import datetime
from itertools import chain
from typing import Dict, List

from maggma.builders import GroupBuilder
from maggma.core import Store

from emmet.core.feff.task import TaskDocument as FEFFTaskDocument
from emmet.core.utils import jsanitize
from emmet.core.xas import XASDoc


class XASBuilder(GroupBuilder):
    """
    Generates XAS Docs from FEFF tasks

    # TODO: Generate MPID from materials collection rather than from task metadata
    """

    def __init__(self, tasks: Store, xas: Store, num_samples: int = 200, **kwargs):
        self.tasks = tasks
        self.xas = xas
        self.num_samples = num_samples
        self.kwargs = kwargs

        super().__init__(source=tasks, target=xas, grouping_keys=["mp_id"])
        self._target_keys_field = "xas_ids"

    def process_item(self, spectra: List[Dict]) -> Dict:
        # TODO: Change this to do structure matching against materials collection
        mpid = spectra[0]["mp_id"]

        self.logger.debug(f"Processing: {mpid}")

        tasks = [FEFFTaskDocument(**task) for task in spectra]

        try:
            docs = XASDoc.from_task_docs(tasks, material_id=mpid)
            processed = [d.model_dump() for d in docs]

            for d in processed:
                d.update({"state": "successful"})
        except Exception as e:
            self.logger.error(traceback.format_exc())
            processed = [
                {
                    "error": str(e),
                    "state": "failed",
                    "task_ids": list(d.task_id for d in tasks),
                }
            ]

        update_doc = {
            "_bt": datetime.utcnow(),
        }
        for d in processed:
            d.update({k: v for k, v in update_doc.items() if k not in d})

        return jsanitize(processed, allow_bson=True)

    def update_targets(self, items):
        """
        Group buidler isn't designed for many-to-many so we unwrap that here
        """

        items = list(filter(None.__ne__, chain.from_iterable(items)))
        super().update_targets(items)
