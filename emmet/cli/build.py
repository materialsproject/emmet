#!/usr/bin/env python
# coding utf-8

from maggma.runner import Runner
from atomate.utils.utils import load_class
from monty.serialization import loadfn
import argparse
import logging

def get_store_from_file(filename):
    """
    helper function to construct a store from a config file
    containing the module path, class name, and kwargs.

    By default, module path is maggma.stores and classname
    is MongoStore, since these are used most often
    """
    store_dict = loadfn(filename)
    modulepath = store_dict.pop("modulepath", "maggma.stores")
    classname = store_dict.pop("classname", "MongoStore")
    store_class = load_class(modulepath, classname)
    return store_class(**store_dict)


def main():
    parser = argparse.ArgumentParser(
        description="emmetbuild is a script used to run builders from "
                    "db or JsonStore configuration files")
    parser.add_argument("-b", "--builder", help="Builder name")
    parser.add_argument("-m", "--module", help="Builder module")
    parser.add_argument("-s", "--source", help="source store config file")
    parser.add_argument("-t", "--target", help="target store config file")
    parser.add_argument("-k", "--kwargs", 
                        default={}, help="builder kwargs, e. g. "
                                         "'{\"query\": {\"tags\": \"project_1\"}}'")
    parser.add_argument("--log", default="WARNING", help="logger level")

    args = parser.parse_args()

    # Set log level
    numeric_level = getattr(logging, args.log.upper())
    logging.basicConfig(level=numeric_level)

    # Get stores
    source_store = get_store_from_file(args.source)
    target_store = get_store_from_file(args.target)

    # Construct builder
    builder_class = load_class(args.module, args.builder)
    builder = builder_class(source_store, target_store, **args.kwargs)

    # Run builder
    runner = Runner([builder])
    runner.run()

if __name__ == "__main__":
    main()
