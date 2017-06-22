# coding: utf-8
import six


def get_mongolike(d, key):
    """
    Grab a dict value using dot-notation like "a.b.c" from dict {"a":{"b":{"c": 3}}}
    Args:
        d (dict): the dictionary to search
        key (str): the key we want to grab with dot notation, e.g., "a.b.c" 

    Returns:
        value from desired dict (whatever is stored at the desired key)

    """
    lead_key = key.split(".", 1)[0]
    try:
        lead_key = int(lead_key)  # for searching array data
    except:
        pass

    if "." in key:
        remainder = key.split(".", 1)[1]
        return get_mongolike(d[lead_key], remainder)
    return d[lead_key]

def make_mongolike(d, get_key, put_key):
    """ 
    Builds a dictionary with a value from another dictionary using mongo dot-notation
    
    Args:
        d (dict)L the dictionary to search
        get_key (str): the key to grab using mongo notation
        put_key (str): the key to put into using mongo notation, doesn't support arrays
    """
    lead_key = put_key.split(".", 1)[0]

    if "." in put_key:
        remainder = put_key.split(".", 1)[1]
        return {lead_key : make_mongolike(d,get_key,remainder)}
    return {lead_key: get_mongolike(d,get_key)}


def recursive_update(d,u):
    """
    Recursive updates d with values from u
    :param d: dict to update
    :param u: updates to propogate
    :return: 
    """

    for k,v in u.items():
        if k in d:
            if isinstance(v,dict) and isinstance(d[k],dict):
                recursive_update(d[k],v)
            elif isinstance(v,list) and isinstance(d[k],list):
                d[k].extend(v)
            else:
                d[k] = v
        else:
            d[k] = v
