"""Ordered schema migration scripts.

Every module defines ``VERSION``, ``NAME``, ``upgrade(connection)`` and
``downgrade(connection)``. Files are discovered automatically and executed in
``VERSION`` order; never renumber or rewrite a script that has shipped.
"""
