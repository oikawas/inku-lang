"""A saved record the retired Saijiki (v1) wrote is a state of the record, not a bad request.

The core refuses it with saijiki_migration_required until the one-time
migration moves it; the host answers 409, as for a locked description.
"""

from inku_server.pipeline_api import _host_error_status


def test_the_refusal_is_a_conflict():
    assert _host_error_status("saijiki_migration_required") == 409
    assert _host_error_status("description_locked") == 409
    assert _host_error_status("schema_violation") == 422
