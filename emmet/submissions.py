__author__ = "Joseph Montoya"
__email__ = "montoyjh@lbl.gov"

class MPSubmissionFilter(object):
    """
    Minimal filter that takes an SNL, checks against 
    a database of previous submissions, optionally
    checks against a materials collection, generates
    a set of production workflows, adds them to a
    launchpad
    """

    # Set of default matching params
    default_match_params = {}
    # Set of default properties-workflow
    default_property_wflows = {"bandstructure": "wf_bandstructure",
                               "elasticity": "wf_elastic_constant",
                               "piezo": "wf_piezoelectric_constant"}

    def __init__(self, submission_coll, materials_coll=None):
        """
        submissions_coll (collection):
        materials_coll (collection):
        """
        self.submission_coll = submission_coll
        self.materials_coll = materials_coll

    @staticmethod
    def find_duplicate_snl(snl, collection, match_params=None):
        """
        Args:
            structure (Structure): struct object to attempt
                finding in the submissions db
            match_params (dict): dictionary of parameters
                for structure matcher
        """
        match_params = match_params or default_match_params
        sm = StructureMatcher(**match_params)
        formula_matches = collection.find({
            "pretty_formula": snl.composition.reduced_formula},
            {"snl": 1, "submission_id": 1})
        for formula_match in formula_matches:
            prev_snl = formula_match["snl"]
            if sm.fit(prev_snl, snl):
                return formula_match
        return None

    def add_submission(self, snl):
        """
        Submission document is minimal, simply an SNL and formula
        """
        snl_doc = {"snl":snl.as_dict(), 
                   "pretty_formula": snl.composition.reduced_formula}
        return self.submissions_coll.insert(snl_doc)

    def update_submission(self, prev_submission_id, new_snl):
        """
        """
        self.submissions_coll.update({"submission_id": prev_submission_id},
                                     {"$push": {"submitted": new_snl}})

    def get_wflows(snl, properties=None, materials_coll=None):
        """
        Args:
            properties (dict): dictionary such that 
        """

    def submit(self, snl, dupecheck=True, wflows=None,
               match_params=None, launchpad=None):
        """
        TODO: Add this docstring
        TODO: prevent race condition?
        """
        dup_submission = self.find_duplicate(snl, self.submission_coll,
                                             match_params=match_params)
        if dup_submission:
            # add duplicate to submissions db?
            # self.update_submission(dup_submission["submission_id"], snl)
            # logger print duplicate submission
            return None
        
        if self.materials_coll:
            dup_material = self.find_duplicate(snl, self.materials_coll,
                                               match_params=match_params)
            if dup_material:
                # add material snl to submissions collection
                # logger print duplicate submission from materials coll
                return None
        
        # Check for properties specific to builder?
        wflows = get_wflows(snl)


