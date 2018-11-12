import io

from bson.binary import Binary
from maggma.builders import Builder
from pydash import py_

import matplotlib
from monty.json import MontyDecoder
from pymatgen.phonon.plotter import PhononBSPlotter

matplotlib.use('agg')


class PhononDispersionPlotter(Builder):
    def __init__(self, pmg_docs, web_docs, images,
                 add_filter=None, ignore_lu=False, **kwargs):
        """
        Produce docs for interactive and static plots of phonon dispersion.

        Args:
            pmg_docs (Store): source of serialized
                `pymatgen.phonon.bandstructure.PhononBandStructure` objects.
            web_docs (Store): target for data needed by interactive plots.
            images (Store): target for png images of phonon dispersion plots.
            add_filter (dict): MongoDB filter to add to default last-updated
                filter.
            ignore_lu (bool): Ignore pmg_docs.lu_filter when getting items.
                Useful for forcing rebuilds given `add_filter`.
        """
        self.pmg_docs = pmg_docs
        self.web_docs = web_docs
        self.images = images
        self.add_filter = add_filter if add_filter else {}
        self.ignore_lu = ignore_lu
        super().__init__(
            sources=[pmg_docs], targets=[web_docs, images], **kwargs)

    def get_items(self):
        lu_filter = self.pmg_docs.lu_filter([self.web_docs, self.images])
        filter_ = {} if self.ignore_lu else lu_filter.copy()
        filter_.update(self.add_filter)
        self.logger.info("Filtering pmg_docs by {}".format(filter_))
        cursor = self.pmg_docs.query(criteria=filter_)
        self.logger.info("Found {} pmg_docs to process".format(cursor.count()))
        if cursor.count() == 0:
            n_updated = self.pmg_docs.query(criteria=lu_filter).count()
            self.logger.debug("{} updated pmg_docs that do not match"
                              " `add_filter`".format(n_updated))
        return cursor

    def process_item(self, item):
        mp_id = item['mp-id']
        self.logger.debug("Processing {}".format(mp_id))
        decoder = MontyDecoder()
        ph_bs = decoder.process_decoded(item['ph_bs'])
        web_doc = ph_bs.as_phononwebsite()
        plotter = PhononBSPlotter(ph_bs)
        ylim = (0, max(py_.flatten_deep(plotter.bs_plot_data()['frequency'])))
        filelike = io.BytesIO()
        plotter.save_plot(filelike, ylim=ylim, img_format="png")
        image = Binary(filelike.getvalue())
        filelike.close()
        return dict(mp_id=mp_id, web_doc=web_doc, image=image)

    def update_targets(self, items):
        self.web_docs.ensure_index("mp-id", unique=True)
        self.images.ensure_index("mp-id", unique=True)
        web_docs = [{"mp-id": item["mp_id"], "ph_bs": item["web_doc"]}
                    for item in items]
        self.web_docs.update(web_docs)
        images = [{"mp-id": item["mp_id"], "plot": item["image"]}
                  for item in items]
        self.images.update(images)
        mp_ids = py_.pluck(items, "mp_id")
        self.logger.info("Updated targets for {}".format(mp_ids))

    def validate_targets(self, n=0):
        self.logger.info("Validating {}".format(
            "all" if not n else "with sample size {}".format(n)))
        ids = self.web_docs.distinct("mp-id")
        sample_ids = py_.sample_size(ids, n) if n else ids
        criteria = {"mp-id": {"$in": sample_ids}}
        web_docs = self.web_docs.query(criteria=criteria)
        n_web_docs = web_docs.count()
        assert n_web_docs == len(sample_ids), "mp-id not unique in web_docs"
        images =self.images.query(criteria=criteria)
        n_images = images.count()
        assert n_web_docs == n_images, "counts for images and web_docs differ"
        for doc in web_docs:
            assert "ph_bs" in doc and doc["ph_bs"] is not None
        self.logger.info("Validated {} of web_docs".format(n_web_docs))
        for doc in images:
            assert "plot" in doc and doc["plot"] is not None
        self.logger.info("Validated {} of images".format(n_images))
