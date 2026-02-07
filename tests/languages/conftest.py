"""Shared fixtures for language plugin tests."""

import pytest

from astrograph.languages.python_plugin import PythonPlugin
from astrograph.languages.registry import LanguageRegistry


@pytest.fixture
def python_plugin():
    """Get Python plugin through registry."""
    plugin = LanguageRegistry.get().get_plugin("python")
    assert plugin is not None
    assert isinstance(plugin, PythonPlugin)
    return plugin


@pytest.fixture(params=["python"])
def language_plugin(request):
    """Parametrized fixture that yields each registered language plugin.

    New language plugins should be added to the params list.
    """
    registry = LanguageRegistry.get()
    plugin = registry.get_plugin(request.param)
    assert plugin is not None, f"Plugin {request.param} not found in registry"
    return plugin


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset the registry between tests to avoid state leakage."""
    yield
    LanguageRegistry.reset()
