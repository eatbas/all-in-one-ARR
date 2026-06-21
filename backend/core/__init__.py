"""All-in-One ARR plugin core.

The core provides the reusable building blocks (config, database, API clients,
scheduler, webhook router, module registry and shared context) that every
module consumes. Modules live under ``modules/`` and are auto-loaded by
:mod:`core.registry`.
"""
