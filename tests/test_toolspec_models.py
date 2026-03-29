from __future__ import annotations

from bioledger.toolspec.models import (
    ExecutionSpec,
    InterfaceSpec,
    ParamType,
    SpecStatus,
    ToolInput,
    ToolOutput,
    ToolParameter,
    ToolSpec,
)


def test_exec_spec_creation(sample_exec_spec):
    assert sample_exec_spec.name == "fastqc"
    assert sample_exec_spec.version == "0.11.9"
    assert sample_exec_spec.status == SpecStatus.VALID
    assert "reads" in sample_exec_spec.inputs
    assert "report" in sample_exec_spec.outputs
    assert "threads" in sample_exec_spec.parameters


def test_tool_spec_wraps_exec(sample_tool_spec):
    assert sample_tool_spec.name == "fastqc"
    assert sample_tool_spec.container == "quay.io/biocontainers/fastqc:0.11.9--0"
    assert sample_tool_spec.execution.status == SpecStatus.VALID


def test_tool_spec_defaults():
    spec = ToolSpec(
        execution=ExecutionSpec(
            name="minimal",
            container="ubuntu:latest",
            command="echo hello",
        )
    )
    assert spec.name == "minimal"
    assert spec.execution.status == SpecStatus.DRAFT
    assert spec.interface is None
    assert spec.execution.inputs == {}
    assert spec.execution.outputs == {}
    assert spec.execution.parameters == {}


def test_param_type_enum():
    assert ParamType.FILE.value == "file"
    assert ParamType.INTEGER.value == "integer"
    assert ParamType.BOOLEAN.value == "boolean"
    assert ParamType.SELECT.value == "select"


def test_tool_parameter_with_constraints():
    param = ToolParameter(
        type=ParamType.INTEGER,
        default=8,
        min=1,
        max=64,
        description="Thread count",
    )
    assert param.default == 8
    assert param.min == 1
    assert param.max == 64


def test_tool_parameter_select():
    param = ToolParameter(
        type=ParamType.SELECT,
        options=["paired", "single"],
        default="paired",
    )
    assert param.options == ["paired", "single"]


def test_tool_input_output():
    inp = ToolInput(type=ParamType.FILE, format="bam", description="Aligned reads")
    out = ToolOutput(format="vcf", description="Variant calls", pattern="*.vcf")
    assert inp.format == "bam"
    assert out.pattern == "*.vcf"


def test_spec_status_progression():
    assert SpecStatus.DRAFT.value == "draft"
    assert SpecStatus.VALID.value == "valid"
    assert SpecStatus.ENRICHED.value == "enriched"


def test_tool_spec_serialization(sample_tool_spec):
    json_str = sample_tool_spec.model_dump_json()
    loaded = ToolSpec.model_validate_json(json_str)
    assert loaded.name == sample_tool_spec.name
    assert loaded.execution.container == sample_tool_spec.execution.container
    assert loaded.execution.status == sample_tool_spec.execution.status


def test_interface_spec():
    iface = InterfaceSpec(
        sections={"advanced": "Advanced Options"},
    )
    assert "advanced" in iface.sections
    assert iface.sections["advanced"] == "Advanced Options"
