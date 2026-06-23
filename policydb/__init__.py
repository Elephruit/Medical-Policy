"""policydb — pull medical coverage policies into a queryable SQLite dataset."""

SOURCES = {}


def register(slug, factory):
    SOURCES[slug] = factory


def _bcbsfl():
    from .sources.bcbsfl import BcbsflAdapter
    return BcbsflAdapter()


register("bcbsfl", _bcbsfl)
