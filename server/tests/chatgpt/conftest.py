"""Shared model settings for the ChatGPT tests.

A ChatGPT plan publication reads the shared assessments of its models at each
use (the author, 2026-10-13). These tests run without the application database,
whose settings table only exists once the app has started, so they read the
default settings, which assess no ChatGPT model. A test that needs an
assessment puts one in the returned settings.
"""

import pytest


@pytest.fixture(autouse=True)
def shared_model_settings(monkeypatch):
    from inku_server import db
    from inku_server.model_settings import default_model_settings

    settings = default_model_settings()
    monkeypatch.setattr(db, "get_model_settings", lambda: settings)
    return settings
