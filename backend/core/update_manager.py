# -*- coding: utf-8 -*-
"""Background update manager responsible for periodic version checks."""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sqlalchemy.exc import OperationalError

from backend.core.config import BASE_DIR, UPDATES
from backend.core.db import SessionLocal, Setting
from backend.core.notifications import log_event


DEFAULT_TIMEOUT = 10


class UpdateManager:
    """Fetches update manifests and applies updates on demand."""

    def __init__(
        self,
        current_version: str,
        fetcher: Optional[Callable[[], Dict[str, Any]]] = None,
    ) -> None:
        self.current_version = str(current_version)
        self.enabled = bool(UPDATES.get("enabled"))
        self.channel = UPDATES.get("channel") or "stable"
        interval_hours = int(UPDATES.get("check_interval_hours") or 24)
        self._interval = max(1, interval_hours) * 3600
        self._fetch_manifest = fetcher or self._default_fetcher
        self._download_dir = Path(UPDATES.get("download_dir") or (BASE_DIR / "updates"))
        self._apply_script = UPDATES.get("apply_script") or ""

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._state: Dict[str, Any] = {
            "current_version": self.current_version,
            "latest_version": self.current_version,
            "available": False,
            "last_checked": None,
            "notes": None,
            "error": None,
            "download_url": None,
            "checksum": None,
            "channel": self.channel,
            "last_applied": None,
        }
        self._connectivity_state: Optional[str] = None
        self._last_server_issue: Optional[tuple[Optional[int], Optional[str]]] = None
        self._notified_available_version: Optional[str] = None
        self._last_error_message: Optional[str] = None
        self._load_state()
        if self._state.get("available"):
            self._notified_available_version = self._state.get("latest_version")
        if self._state.get("error"):
            self._last_error_message = self._state.get("error")

    # ------------------------------------------------------------------
    # Lifecycle management
    # ------------------------------------------------------------------
    def start(self) -> None:
        if not self.enabled:
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="update-manager", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        try:
            self.check_for_updates()
        except Exception:
            pass
        while not self._stop_event.wait(self._interval):
            try:
                self.check_for_updates()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def status(self) -> Dict[str, Any]:
        with self._lock:
            snapshot = dict(self._state)
        snapshot["enabled"] = self.enabled
        snapshot["check_interval_hours"] = self._interval / 3600
        return snapshot

    def check_for_updates(self, manual: bool = False) -> Dict[str, Any]:
        if not self.enabled and not manual:
            return self.status()

        try:
            manifest = self._fetch_manifest()
        except HTTPError as exc:  # pragma: no cover - remote server issues
            status_code = getattr(exc, "code", None)
            reason = getattr(exc, "reason", None)
            status_val = int(status_code) if isinstance(status_code, int) else None
            detail = str(reason) if reason else None
            self._record_server_issue(status_val, detail)
            self._set_error(f"Manifest HTTP error: {exc}")
            return self.status()
        except URLError as exc:  # pragma: no cover - network failure path
            reason = getattr(exc, "reason", exc)
            self._signal_connectivity(False, detail=str(reason))
            self._set_error(f"Manifest network error: {exc}")
            return self.status()
        except Exception as exc:
            self._set_error(f"Manifest error: {exc}")
            return self.status()

        self._signal_connectivity(True)
        self._last_server_issue = None

        latest_version = str(
            manifest.get("version")
            or manifest.get("latest_version")
            or manifest.get("latest")
            or ""
        ).strip()
        if not latest_version:
            self._set_error("Manifest does not define 'version'")
            return self.status()

        notes = manifest.get("notes") or manifest.get("changelog")
        download_url = manifest.get("download_url") or manifest.get("url")
        checksum = manifest.get("checksum")
        channel = manifest.get("channel") or self.channel

        with self._lock:
            current_version = self._state.get("current_version", self.current_version)
            prev_available = bool(self._state.get("available"))
        available = self._is_newer(latest_version, current_version)
        with self._lock:
            self._state.update(
                {
                    "latest_version": latest_version,
                    "notes": notes,
                    "download_url": download_url,
                    "checksum": checksum,
                    "channel": channel,
                    "available": available,
                    "error": None,
                    "last_checked": datetime.now(timezone.utc).isoformat(),
                }
            )
        self._last_error_message = None
        self._save_state()

        if available:
            if latest_version:
                if self._notified_available_version != latest_version:
                    meta = {"version": latest_version}
                    if channel:
                        meta["channel"] = channel
                    log_event("UPDATE_AVAILABLE", meta=meta, category="updates")
                self._notified_available_version = latest_version
        else:
            if prev_available:
                meta = {"version": latest_version or current_version}
                if channel:
                    meta["channel"] = channel
                log_event("UPDATE_UP_TO_DATE", meta=meta, category="updates")
            self._notified_available_version = None

        return self.status()

    def run_update(self) -> Dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "detail": "Updater disabled"}

        with self._lock:
            if not self._state.get("available"):
                return {"ok": False, "detail": "No update available"}
            latest_version = self._state["latest_version"]
            download_url = self._state.get("download_url")

        artifact_path: Optional[Path] = None
        if download_url:
            try:
                artifact_path = self._download_package(download_url)
            except HTTPError as exc:  # pragma: no cover - remote server issues
                status_code = getattr(exc, "code", None)
                reason = getattr(exc, "reason", None)
                status_val = int(status_code) if isinstance(status_code, int) else None
                detail = str(reason) if reason else None
                self._record_server_issue(status_val, detail)
                self._set_error(f"Download failed: {exc}")
                return {"ok": False, "detail": f"Download failed: {exc}"}
            except URLError as exc:  # pragma: no cover - network failure path
                reason = getattr(exc, "reason", exc)
                self._signal_connectivity(False, detail=str(reason))
                self._set_error(f"Download failed: {exc}")
                return {"ok": False, "detail": f"Download failed: {exc}"}
            except Exception as exc:  # pragma: no cover - unexpected failure path
                self._set_error(f"Download failed: {exc}")
                return {"ok": False, "detail": f"Download failed: {exc}"}
            else:
                self._signal_connectivity(True)

        try:
            self._execute_install(artifact_path)
        except Exception as exc:
            self._set_error(f"Install failed: {exc}")
            return {"ok": False, "detail": f"Install failed: {exc}"}

        with self._lock:
            self.current_version = latest_version
            self._state.update(
                {
                    "current_version": latest_version,
                    "available": False,
                    "error": None,
                    "last_applied": datetime.now(timezone.utc).isoformat(),
                }
            )
        self._save_state()
        self._last_error_message = None
        self._notified_available_version = None
        meta = {"version": latest_version}
        if artifact_path:
            meta["artifact"] = str(artifact_path)
        log_event("UPDATE_APPLIED", meta=meta, category="updates")
        return {"ok": True, "status": self.status(), "artifact": str(artifact_path) if artifact_path else None}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _signal_connectivity(self, online: bool, detail: Optional[str] = None) -> None:
        state = "online" if online else "offline"
        if self._connectivity_state == state:
            return
        self._connectivity_state = state
        meta = {"source": "update_manager"}
        if detail:
            meta["detail"] = str(detail)
        event = "NETWORK_ONLINE" if online else "NETWORK_OFFLINE"
        log_event(event, meta=meta, category="network")

    def _record_server_issue(
        self,
        status: Optional[int],
        detail: Optional[str] = None,
    ) -> None:
        key = (status, detail)
        if self._last_server_issue == key:
            return
        self._last_server_issue = key
        meta = {"source": "update_manager"}
        if status is not None:
            try:
                meta["status"] = int(status)
            except (TypeError, ValueError):
                pass
        if detail:
            meta["detail"] = detail
        log_event("SERVER_UNREACHABLE", meta=meta, category="network")

    def _set_error(self, message: str) -> None:
        with self._lock:
            self._state["error"] = message
            self._state["last_checked"] = datetime.now(timezone.utc).isoformat()
        self._save_state()
        if message and message != self._last_error_message:
            log_event("UPDATE_FAILED", meta={"detail": message}, category="updates")
        self._last_error_message = message

    def _load_state(self) -> None:
        try:
            with SessionLocal() as session:
                row = session.get(Setting, "update.state")
                if not row or not row.value:
                    return
                data = json.loads(row.value)
        except (OperationalError, json.JSONDecodeError):
            return
        except Exception:
            return
        with self._lock:
            self._state.update(data)
            self._state["current_version"] = self.current_version
            self._state.setdefault("channel", self.channel)
            self._state.setdefault("available", False)

    def _save_state(self) -> None:
        with self._lock:
            payload = json.dumps(self._state)
        try:
            with SessionLocal() as session:
                session.merge(Setting(key="update.state", value=payload))
                session.commit()
        except OperationalError:
            return
        except Exception:
            return

    def _default_fetcher(self) -> Dict[str, Any]:
        manifest_url = UPDATES.get("manifest_url")
        if not manifest_url:
            raise RuntimeError("updates.manifest_url is not configured")
        req = Request(manifest_url, headers={"User-Agent": "FarmCare-Updater"})
        with urlopen(req, timeout=DEFAULT_TIMEOUT) as response:
            if response.status != 200:
                raise HTTPError(manifest_url, response.status, "Unexpected response", response.headers, None)
            data = response.read()
        return json.loads(data.decode("utf-8"))

    @staticmethod
    def _is_newer(candidate: str, current: str) -> bool:
        def normalize(value: str) -> tuple:
            parts = []
            for chunk in value.replace('-', '.').split('.'):
                if chunk.isdigit():
                    parts.append(int(chunk))
                else:
                    parts.append(chunk)
            return tuple(parts)

        return normalize(candidate) > normalize(current)

    def _download_package(self, url: str) -> Path:
        self._download_dir.mkdir(parents=True, exist_ok=True)
        filename = url.split('/')[-1] or f"update-{int(time.time())}.pkg"
        target = self._download_dir / filename
        req = Request(url, headers={"User-Agent": "FarmCare-Updater"})
        with urlopen(req, timeout=DEFAULT_TIMEOUT) as response:
            if response.status != 200:
                raise HTTPError(url, response.status, "Unexpected download response", response.headers, None)
            data = response.read()
        with target.open("wb") as handle:
            handle.write(data)
        return target

    def _execute_install(self, artifact: Optional[Path]) -> None:
        script = self._apply_script
        if not script:
            return
        script_path = Path(script)
        if not script_path.is_absolute():
            script_path = Path(BASE_DIR) / script_path
        if not script_path.exists():
            raise FileNotFoundError(f"Update script not found: {script_path}")

        env = os.environ.copy()
        if artifact:
            env["FARMCARE_UPDATE_PACKAGE"] = str(artifact)

        suffix = script_path.suffix.lower()
        if suffix == ".sh":
            cmd = ["bash", str(script_path)]
        elif suffix in {".bat", ".cmd"}:
            cmd = [str(script_path)]
        elif suffix == ".ps1":
            cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script_path)]
        else:
            cmd = [str(script_path)]

        subprocess.run(cmd, check=True, env=env)


__all__ = ["UpdateManager"]





