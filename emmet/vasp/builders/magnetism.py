
from pymatgen import Structure
from pymatgen.analysis.magnetism import CollinearMagneticStructureAnalyzer

from maggma.builder import Builder

__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>"


class MagneticBuilder(Builder):
    def __init__(self, materials, magnetism, query={}, **kwargs):
        """
        Creates a magnetism collection for materials

        Args:
            materials (Store): Store of materials documents to match to
            magnetism (Store): Store of magnetism properties
            query (dict): dictionary to limit materials to be analyzed
        """

        self.materials = materials
        self.magnetism = magnetism
        self.query = query

        super().__init__(sources=[materials],
                         targets=[magnetism],
                         **kwargs)

    def get_items(self):
        """
        Gets all items to process into magnetismdocuments

        Returns:
            generator or list relevant tasks and materials to process into magnetism documents
        """
        self.logger.info("Magnestism Builder Started")



        # All relevant materials that have been updated since magnetism props
        # were last calculated
        q = dict(self.query)
        q.update(self.materials.lu_filter(self.magnetism))
        mats = list(self.materials.distinct(self.materials.key, q))
        self.logger.info(
            "Found {} new materials for magnetism data".format(len(mats)))
        for m in mats:
            yield self.materials.query(properties=[self.materials.key, "structure"],criteria={self.materials.key: m}).limit(1)[0]

    def process_item(self, item):
        """
        Process the tasks and materials into a dielectrics collection

        Args:
            item dict: a dict of material_id, structure, and tasks

        Returns:
            dict: a dieletrics dictionary  
        """

        struc = Structure.from_dict(item["structure"])
        msa = CollinearMagneticStructureAnalyzer(struc)

        magnetism = {
            self.magnetism.key : item[self.materials.key],
            "magnetism": {
                'ordering': msa.ordering.value
                }
        }

        return magnetism

    def update_targets(self, items):
        """
        Inserts the new task_types into the task_types collection

        Args:
            items ([([dict],[int])]): A list of tuples of materials to update and the corresponding processed task_ids
        """

        items = list(filter(None, items))

        if len(items) > 0:
            self.logger.info("Updating {} magnetism docs".format(len(items)))
            self.magnetism.update(docs=items)
        else:
            self.logger.info("No items to update")


