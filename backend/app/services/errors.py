class JobSkipped(Exception):
    """A background job whose prerequisites aren't ready yet. Recorded as "skipped" (not "failed"), and nothing chains after it."""
