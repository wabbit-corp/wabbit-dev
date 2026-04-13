from __future__ import annotations

from dev.dashboard_backend import _overall_registry_visibility, _registry_status


def test_registry_status_is_ok_when_current_version_exists_in_registry() -> None:
    status = _registry_status(
        "2.0.0",
        "maven-central",
        "one.wabbit:kotlin-web-wayback",
        "2.0.0",
        ("1.0.0", "2.0.0"),
        (),
    )

    assert status.status == "ok"


def test_registry_status_is_error_when_registry_has_no_versions() -> None:
    status = _registry_status(
        "0.0.1",
        "jitpack",
        "com.github.wabbit-corp:kotlin-web-jitpack",
        None,
        (),
        (),
    )

    assert status.status == "error"


def test_registry_status_is_warn_when_registry_is_outdated() -> None:
    status = _registry_status(
        "2.0.0",
        "pypi",
        "lang-mu",
        "1.9.0",
        ("1.8.0", "1.9.0"),
        (),
    )

    assert status.status == "warn"


def test_overall_registry_visibility_prefers_ok_then_warn_then_error() -> None:
    ok_status = _registry_status("2.0.0", "maven-central", "pkg", "2.0.0", ("2.0.0",), ())
    warn_status = _registry_status("2.0.0", "jitpack", "pkg", "1.9.0", ("1.9.0",), ())
    error_status = _registry_status("2.0.0", "nuget", "pkg", None, (), ())

    assert _overall_registry_visibility((error_status,)) == "unknown"
    assert _overall_registry_visibility((warn_status, error_status)) == "missing"
    assert _overall_registry_visibility((ok_status, warn_status, error_status)) == "published"
