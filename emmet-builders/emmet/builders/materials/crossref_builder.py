from collections import defaultdict

from habanero import Crossref
from maggma.builders import MapBuilder
from pybtex.database.input import bibtex

class CrossRefBuilder(MapBuilder):
    def unary_function(self, item):
        item["crossref_entries"] = get_crossref_entries(item)
        return item

def get_crossref_entries(item):
    """"
    Loop over each reference and convert the names to a set of only last names
    For each reference look up the 10 best results from CrossRef by title only
    and take the entry with the most number of matching author last names.
    if all the authors match, set a key `all_authors_matched` to True.

    Return the result as a dictionary keyed by the original bib key
    """
    cr = Crossref()
    cross_ref_res = defaultdict(dict)
    for k, t, a in parse_bibdata(item['about']['references']):
        works = cr.works(query=t, limit=10)
        most_auth_matched = (0, None)
        cross_ref_res[k]['bib_title'] = t
        cross_ref_res[k]['bib_author'] = a
        cross_ref_res[k]['all_authors_matched'] = False
        for cr_item in works['message']['items']:
            authors = cr_item.get('author', [])
            try:
                found_author_lasts = {ii_['family'].lower() for ii_ in authors}
            except KeyError:
                continue
            if found_author_lasts == a:
                cross_ref_res[k]['all_authors_matched'] = True
                cross_ref_res[k]['cross_ref'] = cr_item
                break
            n_auth_matched = len(found_author_lasts & a)
            if n_auth_matched > most_auth_matched[0]:
                most_auth_matched = (n_auth_matched, cr_item)
        if not cross_ref_res[k]['all_authors_matched']:
            cross_ref_res[k]['cross_ref'] = most_auth_matched[1]
    return cross_ref_res

def parse_bibdata(bibdata_str):
    """
    Query the db for particular snl_id and return all bibtex information
    for the bibkey, title, and authors
    """
    parser = bibtex.Parser()
    bibdata = parser.parse_string(bibdata_str)
    for k, v in bibdata.entries.items():
        authors = v.persons['author']
        authors = set(map(lambda x: str(x.last_names[0]).lower(), authors))
        title = v.fields['title']
        yield k, title, authors