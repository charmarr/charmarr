# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""Unit tests for Jellyfin system.xml helpers."""

from _jellyfin import enable_metrics, is_startup_wizard_completed


def test_enable_metrics_flips_false_to_true():
    """A seeded false flag is flipped to true."""
    content = "<ServerConfiguration><EnableMetrics>false</EnableMetrics></ServerConfiguration>"
    assert "<EnableMetrics>true</EnableMetrics>" in enable_metrics(content)


def test_enable_metrics_idempotent_when_true():
    """Already-enabled content is unchanged."""
    content = "<ServerConfiguration><EnableMetrics>true</EnableMetrics></ServerConfiguration>"
    assert enable_metrics(content) == content


def test_enable_metrics_inserts_when_absent():
    """The element is inserted after the root when missing."""
    content = "<ServerConfiguration><Foo>bar</Foo></ServerConfiguration>"
    result = enable_metrics(content)
    assert "<EnableMetrics>true</EnableMetrics>" in result
    assert result.index("<EnableMetrics>") < result.index("<Foo>")


def test_is_startup_wizard_completed_true():
    """Detects a completed startup wizard."""
    content = (
        "<ServerConfiguration>"
        "<IsStartupWizardCompleted>true</IsStartupWizardCompleted>"
        "</ServerConfiguration>"
    )
    assert is_startup_wizard_completed(content) is True


def test_is_startup_wizard_completed_false():
    """Returns False when the wizard is not completed."""
    content = (
        "<ServerConfiguration>"
        "<IsStartupWizardCompleted>false</IsStartupWizardCompleted>"
        "</ServerConfiguration>"
    )
    assert is_startup_wizard_completed(content) is False
