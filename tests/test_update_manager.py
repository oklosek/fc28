import pytest

from backend.core.update_manager import UpdateManager, UPDATES


def test_update_manager_detects_new_release(monkeypatch):
    monkeypatch.setitem(UPDATES, "enabled", True)
    monkeypatch.setitem(UPDATES, "check_interval_hours", 24)
    monkeypatch.setitem(UPDATES, "apply_script", "")
    monkeypatch.setitem(UPDATES, "manifest_url", "")
    manager = UpdateManager("1.0.0", fetcher=lambda: {"version": "1.1.0", "notes": "test"})
    status = manager.check_for_updates(manual=True)
    assert status["available"] is True
    assert status["latest_version"] == "1.1.0"
    manager.stop()


def test_update_manager_run_update(monkeypatch, tmp_path):
    monkeypatch.setitem(UPDATES, "enabled", True)
    monkeypatch.setitem(UPDATES, "check_interval_hours", 24)
    monkeypatch.setitem(UPDATES, "apply_script", "")
    monkeypatch.setitem(UPDATES, "manifest_url", "")
    monkeypatch.setitem(UPDATES, "download_dir", str(tmp_path))

    manager = UpdateManager("2.0.0", fetcher=lambda: {"version": "2.1.0"})
    manager.check_for_updates(manual=True)
    result = manager.run_update()
    assert result["ok"] is True
    status = manager.status()
    assert status["current_version"] == "2.1.0"
    assert status["available"] is False
    manager.stop()
