"""policydb — pull medical coverage policies into a queryable SQLite dataset."""

SOURCES = {}


def register(slug, factory):
    SOURCES[slug] = factory


def _bcbsfl():
    from .sources.bcbsfl import BcbsflAdapter
    return BcbsflAdapter()


def _oscar():
    from .sources.oscar import OscarAdapter
    return OscarAdapter()


register("bcbsfl", _bcbsfl)
register("oscar", _oscar)
