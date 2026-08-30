"""
Holds parsed-but-not-yet-imported CSV rows between the "preview" step
(upload a file, see the guessed column mapping) and the "confirm" step
(import with the user-confirmed mapping) — so confirming a mapping for a
large file doesn't mean shipping the whole dataset back over the wire a
second time as JSON.

Known limitation: this is an in-process Python dict, so it only works
with Flask's single-process dev server (the one this project runs with).
A multi-worker production deployment would need a shared store (Redis,
etc.) instead — noted in the README rather than silently assumed away.
"""
import uuid
import time

_cache = {}
_MAX_AGE_SECONDS = 60 * 30  # previews expire after 30 minutes


def store(headers, rows):
    _cleanup()
    upload_id = uuid.uuid4().hex
    _cache[upload_id] = {'headers': headers, 'rows': rows, 'stored_at': time.time()}
    return upload_id


def retrieve(upload_id):
    entry = _cache.get(upload_id)
    return entry if entry else None


def discard(upload_id):
    _cache.pop(upload_id, None)


def _cleanup():
    cutoff = time.time() - _MAX_AGE_SECONDS
    stale = [k for k, v in _cache.items() if v['stored_at'] < cutoff]
    for k in stale:
        _cache.pop(k, None)
