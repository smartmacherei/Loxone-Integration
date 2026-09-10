"""Read registry entries without assuming iteration returns dictionary keys."""


def registry_entries(items):
    values = getattr(items, "values", None)
    return values() if callable(values) else iter(items)


def registry_ids(items):
    return {entry.id for entry in registry_entries(items)}
