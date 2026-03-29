from __future__ import annotations

import time
from dataclasses import dataclass

import docker


@dataclass
class RunResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float


class DockerRunner:
    """Thin wrapper around docker-py for running bioinformatics tools in containers.
    Handles timeouts, memory limits, network isolation, and cleanup."""

    def __init__(self):
        self.client = docker.from_env()

    def run(
        self,
        image: str,
        command: list[str] | None = None,
        volumes: dict | None = None,
        env: dict | None = None,
        workdir: str | None = None,
        timeout: int = 3600,
        mem_limit: str = "8g",
        network_disabled: bool = True,
    ) -> RunResult:
        """Run a command in a container with safety constraints.

        Args:
            image: Docker image URI
            command: Command to run
            volumes: Volume mounts {host_path: {"bind": container_path, "mode": "rw"}}
            env: Environment variables
            workdir: Working directory inside container
            timeout: Max seconds before killing container
            mem_limit: Memory limit (e.g. "8g", "512m")
            network_disabled: If True, container has no network access
        """
        container = None
        try:
            start = time.monotonic()
            container = self.client.containers.run(
                image,
                command=command,
                volumes=volumes or {},
                environment=env or {},
                working_dir=workdir,
                detach=True,
                stdout=True,
                stderr=True,
                mem_limit=mem_limit,
                network_mode="none" if network_disabled else "bridge",
            )
            result = container.wait(timeout=timeout)
            elapsed = time.monotonic() - start
            stdout = container.logs(stdout=True, stderr=False).decode()
            stderr = container.logs(stdout=False, stderr=True).decode()
            return RunResult(
                exit_code=result["StatusCode"],
                stdout=stdout,
                stderr=stderr,
                duration_seconds=elapsed,
            )
        except Exception:
            if container:
                try:
                    container.kill()
                except Exception:
                    pass
            raise
        finally:
            if container:
                try:
                    container.remove(force=True)
                except Exception:
                    pass
