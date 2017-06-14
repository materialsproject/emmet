from atomate import SubmissionFilter

class MPSubmissionFilter(SubmissionFilter):
    """
    Minimal filter that takes an SNL, checks against 
    a database of previous submissions, optionally
    checks against a materials collection, generates
    a set of production workflows, adds them to a
    launchpad
    """

    # Set of default matching params
    default_match_params = {}

    def init(self, submission_coll=None, materials_coll=None):
        """
        """
        self.submission_coll = submission_coll
        self.materials_coll = materials_coll

    @staticmethod
    def find_duplicate(snl, collection, match_params=None):
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
        self.submissions_coll.update({"submission_id": prev_submission_id},
                                     {"$push": {"submitted": new_snl}})

    def submit(snl, dupecheck=True, match_params=None, launchpad=None):
        """
        TODO: Add this docstring
        """

