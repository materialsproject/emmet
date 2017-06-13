from atomate import SubmissionFilter

class MPSubmissionFilter(SubmissionFilter):
    """
    Minimal filter that takes an SNL, checks
    against a database of previous submissions,
    generates a set of production workflows, 
    and adds those 
    """

    # Set of default matching params
    default_match_params = {}

    def init(self, submission_db_file=None):
        pass

    def check_for_duplicate(self, snl, match_params=None):
        """
        Args:
            structure (Structure): struct object to attempt
                finding in the submissions db
            match_params (dict): dictionary of parameters
                for structure matcher
        """
        match_params = match_params or default_match_params

    def add_snl_to_submission_db(self, snl):
        """
        TODO: Add this docstring
        """
        pass

    def submit(snl, match_params=None, launchpad=None):
        """
        TODO: Add this docstring
        """
        pass
