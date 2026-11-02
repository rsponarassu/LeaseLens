"""LeaseLens: tenancy-clause analysis for the Tamil Nadu Rent Act, 2017.

Layering, outside in:

``main`` -> ``api`` (HTTP) -> ``services`` (the pipeline) -> ``models`` (data)
with ``core`` (config, errors, logging), ``cache``, ``data``, ``llm`` and
``rules`` as supporting packages.

The dependency rule is one-directional: services never import from ``app.api``,
and only ``app.api`` knows about HTTP status codes.
"""

__version__ = "1.0.0"
