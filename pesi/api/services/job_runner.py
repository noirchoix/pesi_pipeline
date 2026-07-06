from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pesi.api.config import ApiSettings
from pesi.api.schemas import RunRecord, RunRequest


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobStore:
    def __init__(self, settings: ApiSettings):
        self.settings = settings
        self.base = settings.safe_path(settings.job_dir)
        self.base.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def record_path(self, run_id: str) -> Path:
        return self.base / run_id / "record.json"

    def log_path(self, run_id: str) -> Path:
        return self.base / run_id / "run.log"

    def create(self, request: RunRequest) -> RunRecord:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:10]
        run_dir = self.base / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        record = RunRecord(
            run_id=run_id,
            status="queued",
            created_at=utcnow(),
            updated_at=utcnow(),
            request=request,
            output_dir=request.out_dir,
            artifact_dir=request.artifact_dir,
            log_path=str(self.log_path(run_id)),
        )
        self.save(record)
        return record

    def save(self, record: RunRecord) -> None:
        with self._lock:
            path = self.record_path(record.run_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(record.model_dump_json(indent=2), encoding="utf-8")

    def get(self, run_id: str) -> RunRecord | None:
        path = self.record_path(run_id)
        if not path.exists():
            return None
        return RunRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def list(self, limit: int = 50) -> list[RunRecord]:
        records: list[RunRecord] = []
        for path in sorted(self.base.glob("*/record.json"), reverse=True):
            try:
                records.append(RunRecord.model_validate_json(path.read_text(encoding="utf-8")))
            except Exception:
                continue
            if len(records) >= limit:
                break
        return records

    def append_log(self, run_id: str, line: str) -> None:
        with self.log_path(run_id).open("a", encoding="utf-8") as f:
            f.write(line)
            if not line.endswith("\n"):
                f.write("\n")

    def read_log(self, run_id: str, tail: int = 400) -> dict[str, Any]:
        path = self.log_path(run_id)
        if not path.exists():
            return {"status": "missing", "lines": []}
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return {"status": "ok", "lines": lines[-tail:], "total_lines": len(lines), "path": str(path)}


class SubprocessJobRunner:
    def __init__(self, settings: ApiSettings, store: JobStore):
        self.settings = settings
        self.store = store
        self._threads: dict[str, threading.Thread] = {}

    def launch(self, request: RunRequest) -> RunRecord:
        record = self.store.create(request)
        thread = threading.Thread(target=self._run, args=(record.run_id,), daemon=True)
        self._threads[record.run_id] = thread
        thread.start()
        return record

    def _set_status(self, record: RunRecord, status: str, **updates: Any) -> RunRecord:
        data = record.model_dump()
        data.update(updates)
        data["status"] = status
        data["updated_at"] = utcnow()
        new = RunRecord.model_validate(data)
        self.store.save(new)
        return new

    def _run(self, run_id: str) -> None:
        record = self.store.get(run_id)
        if not record:
            return
        record = self._set_status(record, "running", started_at=utcnow())
        self.store.append_log(run_id, f"PESI run {run_id} started at {record.started_at.isoformat()}")
        try:
            scenario_path = self._write_scenario_file(run_id, record.request)
            run_cmd = [
                sys.executable,
                "-m",
                "pesi.cli.main",
                "run-all",
                "--raw",
                record.request.raw_dir,
                "--out",
                record.request.out_dir,
                "--artifact",
                record.request.artifact_dir,
                "--sabio-mode",
                record.request.sabio_mode.value,
                "--profile",
                record.request.profile.value,
            ]
            if scenario_path:
                self.store.append_log(run_id, f"Scenario captured at {scenario_path}")
            code = self._run_command(run_id, run_cmd)
            if code != 0:
                record = self.store.get(run_id) or record
                self._set_status(record, "failed", return_code=code, finished_at=utcnow(), error="run-all failed")
                return

            if record.request.run_benchmark:
                bench_cmd = [
                    sys.executable,
                    "-m",
                    "pesi.cli.main",
                    "benchmark",
                    "--out",
                    record.request.out_dir,
                    "--artifact",
                    record.request.artifact_dir,
                ]
                code = self._run_command(run_id, bench_cmd)
                if code != 0:
                    record = self.store.get(run_id) or record
                    self._set_status(record, "failed", return_code=code, finished_at=utcnow(), error="benchmark failed")
                    return

            record = self.store.get(run_id) or record
            self._set_status(record, "succeeded", return_code=0, finished_at=utcnow())
            self.store.append_log(run_id, f"PESI run {run_id} completed successfully")
        except Exception as exc:
            record = self.store.get(run_id) or record
            self.store.append_log(run_id, f"ERROR: {exc}")
            self._set_status(record, "failed", return_code=1, finished_at=utcnow(), error=str(exc))

    def _write_scenario_file(self, run_id: str, request: RunRequest) -> str | None:
        if not request.scenario:
            return None
        path = self.store.base / run_id / "scenario.json"
        path.write_text(json.dumps(request.scenario.model_dump(), indent=2), encoding="utf-8")
        return str(path)

    def _run_command(self, run_id: str, command: list[str]) -> int:
        self.store.append_log(run_id, "$ " + " ".join(command))
        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")
        process = subprocess.Popen(
            command,
            cwd=str(self.settings.project_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
        assert process.stdout is not None
        for line in process.stdout:
            self.store.append_log(run_id, line.rstrip("\n"))
        return process.wait()


_runner: SubprocessJobRunner | None = None
_store: JobStore | None = None


def get_job_store(settings: ApiSettings) -> JobStore:
    global _store
    if _store is None:
        _store = JobStore(settings)
    return _store


def get_job_runner(settings: ApiSettings) -> SubprocessJobRunner:
    global _runner
    store = get_job_store(settings)
    if _runner is None:
        _runner = SubprocessJobRunner(settings, store)
    return _runner
