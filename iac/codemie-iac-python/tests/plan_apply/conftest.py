import pytest

from codemie_iac.plan_apply.credentials import EnvCredentialResolver

_ORIGINAL_INIT = EnvCredentialResolver.__init__


def _stand_in_lookup(provider_name, toolkit_id):
    """Stand-in for the platform provider schema: only ``api_key`` is secret."""
    return ["api_key"]


@pytest.fixture(autouse=True)
def _provider_schema_lookup(monkeypatch):
    """Resolvers built without an explicit lookup get the stand-in schema."""

    def init(self, environ=None, provider_secret_lookup=_stand_in_lookup):
        _ORIGINAL_INIT(self, environ, provider_secret_lookup)

    monkeypatch.setattr(EnvCredentialResolver, "__init__", init)


@pytest.fixture
def no_lookup(monkeypatch):
    """The production state: no provider schema lookup unless one is passed."""
    monkeypatch.setattr(EnvCredentialResolver, "__init__", _ORIGINAL_INIT)
