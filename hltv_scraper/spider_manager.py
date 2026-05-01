import json
import os
import time
from typing import Any

from .cleaner import OldDataCleaner, JsonOldDataCleaner
from .data import JsonDataLoader, DataLoader
from .path_generator import JsonFilePathGenerator, FilePathGenerator
from .conditions_checker import AnyConditionsChecker as ConditionsChecker
from .conditions_factory import ConditionFactory as CF
from .process import SpiderProcess

class SpiderManager:
    DEFAULT_RETRY_AFTER_SECONDS = 2

    def __init__(self, dir: str) -> None:
        self.loader: DataLoader = JsonDataLoader()
        self.path: FilePathGenerator = JsonFilePathGenerator(dir)
        self.cleaner: OldDataCleaner = JsonOldDataCleaner()
        self.dir: str = dir

    def _result_path(self, path: str) -> str:
        return self.path.generate(path)

    def _lock_path(self, result_path: str) -> str:
        return f"{result_path}.lock"

    def _read_lock(self, lock_path: str) -> dict[str, Any]:
        try:
            if not os.path.exists(lock_path):
                return {}
            with open(lock_path, "r") as lock_file:
                payload = json.load(lock_file)
                return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _write_lock(self, lock_path: str, payload: dict[str, Any]) -> None:
        with open(lock_path, "w") as lock_file:
            json.dump(payload, lock_file)

    def _clear_lock(self, lock_path: str) -> None:
        try:
            os.remove(lock_path)
        except FileNotFoundError:
            pass

    def _is_process_running(self, pid) -> bool:
        try:
            normalized_pid = int(pid)
        except (TypeError, ValueError):
            return False

        if normalized_pid <= 0:
            return False

        try:
            os.kill(normalized_pid, 0)
        except OSError:
            return False
        return True

    def _ready_state(self, result_path: str, retry_after: int) -> dict[str, Any]:
        return {
            "status": "ready",
            "path": result_path,
            "retry_after": retry_after,
        }

    def _processing_state(
        self, pid: int, retry_after: int, started_at: float | None
    ) -> dict[str, Any]:
        return {
            "status": "processing",
            "pid": pid,
            "retry_after": retry_after,
            "started_at": started_at,
        }

    def _failed_state(self, retry_after: int, message: str) -> dict[str, Any]:
        return {
            "status": "failed",
            "error": "Failed to fetch match details",
            "message": message,
            "retry_after": retry_after,
        }

    def _normalize_retry_after(self, value: Any, default: int) -> int:
        if isinstance(value, bool):
            return default
        if isinstance(value, int):
            return value if value > 0 else default
        if isinstance(value, str):
            try:
                parsed = int(value)
            except ValueError:
                return default
            return parsed if parsed > 0 else default
        return default

    def __get_conditions__(self, path: str, hours: int = 1) -> list[Any]:
        return [
            CF.get("file_time", file_path=path, hours=hours),
            CF.get("json_file_empty", file_path=path),
        ]

    def __should_run__(self, path: str, hours: int = 1) -> bool:
        conditions = self.__get_conditions__(path, hours)
        checker = ConditionsChecker(conditions)
        return checker.check()

    def run_spider(self, name: str, path: str, args: str) -> None:
        path = self._result_path(path)
        if CF.get("file_exists", file_path=path).check():
            self.cleaner.clean(path)
        SpiderProcess().execute(name, self.dir, args)

    def execute(self, name: str, path: str, args: str, hours: int = 1) -> None:
        path = self._result_path(path)
        if self.__should_run__(path, hours):
            if CF.get("file_exists", file_path=path).check():
                self.cleaner.clean(path)
            SpiderProcess().execute(name, self.dir, args)

    def execute_async(
        self,
        name: str,
        path: str,
        args: str,
        hours: int = 1,
        retry_after: int = DEFAULT_RETRY_AFTER_SECONDS,
    ) -> dict[str, Any]:
        result_path = self._result_path(path)
        lock_path = self._lock_path(result_path)

        if not self.__should_run__(result_path, hours):
            self._clear_lock(lock_path)
            return self._ready_state(result_path, retry_after)

        lock_payload = self._read_lock(lock_path)
        if lock_payload:
            pid = lock_payload.get("pid")
            normalized_pid = self._normalize_retry_after(pid, 0)
            if normalized_pid > 0 and self._is_process_running(normalized_pid):
                return self._processing_state(
                    normalized_pid,
                    self._normalize_retry_after(
                        lock_payload.get("retry_after"), retry_after
                    ),
                    lock_payload.get("started_at"),
                )

            self._clear_lock(lock_path)

            if not self.__should_run__(result_path, hours):
                return self._ready_state(result_path, retry_after)

            return self._failed_state(
                retry_after,
                "Background spider exited before producing a usable cached result",
            )

        if CF.get("file_exists", file_path=result_path).check():
            self.cleaner.clean(result_path)

        process = SpiderProcess().spawn(name, self.dir, args)
        started_at = time.time()
        self._write_lock(
            lock_path,
            {
                "pid": process.pid,
                "spider_name": name,
                "retry_after": retry_after,
                "started_at": started_at,
            },
        )
        return self._processing_state(process.pid, retry_after, started_at)

    def get_result(self, path: str) -> dict[str, Any]:
        result_path = self._result_path(path)
        print(result_path)
        return self.loader.load(result_path)

    def get_profile(self, filename: str, profile: str) -> dict[str, Any]:
        path = self.path.generate(filename)
        profiles = self.loader.load(path)
        return profiles[profile]

    def is_profile(self, filename: str, profile: str) -> bool:
        path = self.path.generate(filename)
        if not CF.get("file_exists", file_path=path).check():
            return False
        profiles = self.loader.load(path)
        return profile in profiles
