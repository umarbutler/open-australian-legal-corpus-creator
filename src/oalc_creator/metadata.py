DATA_VERSIONS: dict[str, int] = {
    'corpus' : 1,
    'index' : 1,
    'indices' : 1,
}
"""A map of the names of Corpus data to version numbers. This flags whether Corpus data is compatible with the current version of the Creator.

Unlike storing metadata in `pyproject.toml`, this method of data versioning will also work when debugging the package as local modules.

Semantic versioning is *not* used here as the sole purpose of these version numbers is to indicate absolute data compatibility."""