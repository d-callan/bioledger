from __future__ import annotations

import hashlib
import shlex
from pathlib import Path

from jinja2 import Template

from bioledger.core.containers.docker import DockerRunner, RunResult
from bioledger.ledger.models import (
    ContainerInfo,
    EntryKind,
    FileRef,
    LedgerEntry,
    LedgerSession,
)
from bioledger.toolspec.models import (
    ExecutionSpec,
    ParamType,
    SpecStatus,
    ToolInput,
    ToolSpec,
)


def _hash_file(path: Path, chunk_size: int = 8192) -> str:
    """Stream-hash a file (safe for multi-GB BAM files)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def _render_command(
    spec: ToolSpec, input_files: dict[str, Path], params: dict, output_dir: str
) -> str:
    """Render the Jinja2 command template with concrete values."""
    context = {
        "inputs": {
            name: f"/input/{name}/{path.name}" for name, path in input_files.items()
        },
        "parameters": {
            **{k: v.default for k, v in spec.execution.parameters.items()},
            **params,
        },
        "outputs": {"_dir": output_dir},
    }
    return Template(spec.execution.command).render(context)


def run_tool(
    session: LedgerSession,
    spec: ToolSpec,
    input_files: dict[str, Path],
    output_dir: Path,
    params: dict | None = None,
    parent_id: str | None = None,
) -> tuple[LedgerEntry, RunResult]:
    """Execute a tool via Docker, record everything in the ledger."""
    runner = DockerRunner()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build volume mounts
    volumes = {
        str(output_dir): {"bind": "/output", "mode": "rw"},
    }
    for name, path in input_files.items():
        volumes[str(path.parent)] = {"bind": f"/input/{name}", "mode": "ro"}

    # Render command via Jinja2, split safely
    rendered_cmd = _render_command(spec, input_files, params or {}, "/output")
    try:
        command = shlex.split(rendered_cmd)
    except ValueError:
        command = ["sh", "-c", rendered_cmd]

    result = runner.run(
        image=spec.container,
        command=command,
        volumes=volumes,
    )

    # Build file refs (streaming hash — safe for large files)
    file_refs = [
        FileRef(
            path=str(p), sha256=_hash_file(p),
            size_bytes=p.stat().st_size, role="input",
        )
        for p in input_files.values()
    ]
    for out_path in output_dir.iterdir():
        if out_path.is_file():
            file_refs.append(
                FileRef(
                    path=str(out_path), sha256=_hash_file(out_path),
                    size_bytes=out_path.stat().st_size, role="output",
                )
            )

    entry = LedgerEntry(
        kind=EntryKind.TOOL_RUN,
        parent_id=parent_id,
        tool_spec_name=spec.name,
        tool_spec_snapshot=spec.execution.model_dump(),
        container=ContainerInfo(
            image=spec.container,
            command=command,
            volumes={k: v["bind"] for k, v in volumes.items()},
        ),
        files=file_refs,
        params=params or {},
        exit_code=result.exit_code,
        duration_seconds=result.duration_seconds,
    )
    session.add(entry)
    return entry, result


def run_script(
    session: LedgerSession,
    script_path: Path,
    container: str = "python:3.11-slim",
    input_files: dict[str, Path] | None = None,
    output_dir: Path | None = None,
    parent_id: str | None = None,
) -> tuple[LedgerEntry, RunResult]:
    """Run a custom script in a container. Auto-generates a transient ExecutionSpec."""
    output_dir = output_dir or Path.cwd() / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    input_files = input_files or {}
    runner = DockerRunner()

    # Build transient spec
    spec = ToolSpec(
        execution=ExecutionSpec(
            name=f"script_{script_path.stem}",
            container=container,
            command=f"python /scripts/{script_path.name}",
            inputs={"script": ToolInput(type=ParamType.FILE, format="any")},
            status=SpecStatus.DRAFT,
        )
    )

    # Mount script + inputs + output
    volumes = {
        str(script_path.parent): {"bind": "/scripts", "mode": "ro"},
        str(output_dir): {"bind": "/output", "mode": "rw"},
    }
    for name, path in input_files.items():
        volumes[str(path.parent)] = {"bind": f"/input/{name}", "mode": "ro"}

    result = runner.run(
        image=container,
        command=["python", f"/scripts/{script_path.name}"],
        volumes=volumes,
    )

    # Capture script + input files + outputs
    file_refs = [
        FileRef(
            path=str(script_path), sha256=_hash_file(script_path),
            size_bytes=script_path.stat().st_size, role="script",
        ),
    ]
    for p in input_files.values():
        file_refs.append(
            FileRef(
                path=str(p), sha256=_hash_file(p),
                size_bytes=p.stat().st_size, role="input",
            )
        )
    for out_path in output_dir.iterdir():
        if out_path.is_file():
            file_refs.append(
                FileRef(
                    path=str(out_path), sha256=_hash_file(out_path),
                    size_bytes=out_path.stat().st_size, role="output",
                )
            )

    entry = LedgerEntry(
        kind=EntryKind.SCRIPT_RUN,
        parent_id=parent_id,
        tool_spec_name=spec.name,
        tool_spec_snapshot=spec.execution.model_dump(),
        container=ContainerInfo(
            image=container,
            command=["python", f"/scripts/{script_path.name}"],
            volumes={k: v["bind"] for k, v in volumes.items()},
        ),
        files=file_refs,
        exit_code=result.exit_code,
        duration_seconds=result.duration_seconds,
    )
    session.add(entry)
    return entry, result
