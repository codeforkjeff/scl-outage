import importlib
from itertools import chain
from typing import List

from .base import DataSource, NeighborhoodIndex


prefix = ".".join(__name__.split(".")[0:-1])

modules = ["renton", "seattle", "shoreline", "tukwila", "wa", "wa_cdp"]

_data_sources = None


def get_data_sources() -> List[DataSource]:
    """
    get all available data sources
    """
    global _data_sources
    if _data_sources is None:
        _data_sources = []
        for module_name in modules:
            module = importlib.import_module(f"{prefix}.{module_name}")
            _data_sources.append(getattr(module, "datasource"))
    return _data_sources


def create_neighborhood_index(data_sources: List[DataSource]):
    return NeighborhoodIndex(
        list(
            chain.from_iterable(
                [data_source.neighborhoods_fn() for data_source in data_sources]
            )
        )
    )


_neighborhood_index = None


def get_neighborhood_index():
    """
    singleton index that contains data from all neighborhood data sources
    """
    global _neighborhood_index
    if _neighborhood_index is None:
        _neighborhood_index = create_neighborhood_index(get_data_sources())
    return _neighborhood_index
