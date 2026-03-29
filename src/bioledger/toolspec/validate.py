from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from .models import (
    SPEC_VERSION,
    ExecutionSpec,
    FileFormat,
    InterfaceSpec,
    ParamType,
    SpecStatus,
    ToolSpec,
)


class Severity(str, Enum):
    ERROR = "error"  # blocks execution
    WARNING = "warning"  # allowed in draft, blocks in strict
    INFO = "info"  # suggestion only


@dataclass
class ValidationIssue:
    severity: Severity
    field: str
    message: str


@dataclass
class ValidationResult:
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not any(i.severity == Severity.ERROR for i in self.issues)

    @property
    def is_strict_valid(self) -> bool:
        return not any(i.severity in (Severity.ERROR, Severity.WARNING) for i in self.issues)

    def summary(self) -> str:
        errors = [i for i in self.issues if i.severity == Severity.ERROR]
        warns = [i for i in self.issues if i.severity == Severity.WARNING]
        return f"{len(errors)} errors, {len(warns)} warnings, {len(self.issues)} total issues"


def validate_execution(spec: ExecutionSpec, strict: bool = False) -> ValidationResult:
    """Validate the execution layer of a tool spec."""
    result = ValidationResult()

    # ERRORS: always block
    if not spec.name:
        result.issues.append(ValidationIssue(Severity.ERROR, "name", "Tool name is required"))
    if not spec.container:
        result.issues.append(
            ValidationIssue(Severity.ERROR, "container", "Container image is required")
        )
    if not spec.command:
        result.issues.append(
            ValidationIssue(Severity.ERROR, "command", "Command template is required")
        )

    # Check command references match declared inputs/params/outputs
    refs = set(re.findall(r"\{\{(\w+\.\w+)\}\}", spec.command))
    for ref in refs:
        namespace, name = ref.split(".", 1)
        if namespace == "inputs" and name not in spec.inputs:
            result.issues.append(
                ValidationIssue(
                    Severity.ERROR,
                    f"command.{ref}",
                    f"Command references undeclared input '{name}'",
                )
            )
        elif namespace == "parameters" and name not in spec.parameters:
            result.issues.append(
                ValidationIssue(
                    Severity.ERROR,
                    f"command.{ref}",
                    f"Command references undeclared parameter '{name}'",
                )
            )

    # Parameter validation
    for param_name, param in spec.parameters.items():
        if param.type in (ParamType.INTEGER, ParamType.FLOAT):
            if param.default is not None and param.min is not None:
                if param.default < param.min:
                    result.issues.append(
                        ValidationIssue(
                            Severity.ERROR,
                            f"parameters.{param_name}.default",
                            f"Default value {param.default} is below minimum {param.min}",
                        )
                    )
            if param.default is not None and param.max is not None:
                if param.default > param.max:
                    result.issues.append(
                        ValidationIssue(
                            Severity.ERROR,
                            f"parameters.{param_name}.default",
                            f"Default value {param.default} exceeds maximum {param.max}",
                        )
                    )

    # WARNINGS: block in strict mode only
    if not spec.version:
        result.issues.append(
            ValidationIssue(Severity.WARNING, "version", "Version is recommended")
        )
    if not spec.description:
        result.issues.append(
            ValidationIssue(Severity.WARNING, "description", "Description is recommended")
        )
    if not spec.outputs:
        result.issues.append(
            ValidationIssue(Severity.WARNING, "outputs", "No outputs declared")
        )

    for inp_name, inp in spec.inputs.items():
        if inp.format == "any":
            result.issues.append(
                ValidationIssue(
                    Severity.WARNING,
                    f"inputs.{inp_name}.format",
                    f"Input '{inp_name}' has format 'any' — specify for better chaining",
                )
            )
        elif inp.format not in FileFormat.KNOWN:
            result.issues.append(
                ValidationIssue(
                    Severity.INFO,
                    f"inputs.{inp_name}.format",
                    f"Input '{inp_name}' has non-standard format '{inp.format}' "
                    f"(not in well-known set)",
                )
            )

    for out_name, out in spec.outputs.items():
        if out.format not in FileFormat.KNOWN and out.format != "any":
            result.issues.append(
                ValidationIssue(
                    Severity.INFO,
                    f"outputs.{out_name}.format",
                    f"Output '{out_name}' has non-standard format '{out.format}'",
                )
            )

    # Update status based on validation
    if strict:
        spec.status = SpecStatus.VALID if result.is_strict_valid else SpecStatus.DRAFT
    else:
        spec.status = SpecStatus.VALID if result.is_valid else SpecStatus.DRAFT

    return result


def validate_interface(interface: InterfaceSpec, exec_spec: ExecutionSpec) -> ValidationResult:
    """Validate the interface layer against the execution layer."""
    result = ValidationResult()
    all_fields = set(exec_spec.inputs) | set(exec_spec.parameters)
    for hint_name in interface.hints:
        if hint_name not in all_fields:
            result.issues.append(
                ValidationIssue(
                    Severity.WARNING,
                    f"interface.hints.{hint_name}",
                    f"UI hint references undeclared field '{hint_name}'",
                )
            )
    return result


def validate_spec(spec: ToolSpec, strict: bool = False) -> ValidationResult:
    """Validate a complete tool spec (execution + optional interface)."""
    result = validate_execution(spec.execution, strict=strict)

    # Check spec version
    if spec.spec_version != SPEC_VERSION:
        result.issues.append(
            ValidationIssue(
                Severity.WARNING,
                "spec_version",
                f"Spec version '{spec.spec_version}' differs from current "
                f"'{SPEC_VERSION}' — may need migration",
            )
        )

    if spec.interface:
        iface_result = validate_interface(spec.interface, spec.execution)
        result.issues.extend(iface_result.issues)

    return result
