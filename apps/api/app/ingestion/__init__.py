"""Document ingestion: parse -> chunk -> embed.

Everything in this package is pure with respect to the database. The stages
in ``pipeline`` load and persist; the modules here transform.
"""
