from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from bioledger.core.llm.agents import ForgeDeps
from bioledger.toolspec.models import (
    ExecutionSpec,
    ParamType,
    SpecStatus,
    ToolInput,
    ToolOutput,
    ToolParameter,
    ToolSpec,
)
from bioledger.toolspec.validate import validate_execution


def to_galaxy_xml(spec: ExecutionSpec) -> str:
    """Convert an ExecutionSpec to Galaxy tool XML. Uses ElementTree for proper escaping."""
    tool = ET.Element("tool", id=spec.name, name=spec.name, version=spec.version or "0.1")
    ET.SubElement(tool, "description").text = spec.description

    reqs = ET.SubElement(tool, "requirements")
    ET.SubElement(reqs, "container", type="docker").text = spec.container

    cmd = ET.SubElement(tool, "command", detect_errors="exit_code")
    cmd.text = spec.command  # ElementTree handles escaping

    inputs_el = ET.SubElement(tool, "inputs")
    for name, inp in spec.inputs.items():
        ET.SubElement(
            inputs_el, "param", name=name, type="data",
            format=inp.format, label=inp.description or name,
        )

    for name, param in spec.parameters.items():
        attrs: dict[str, str] = {"name": name, "label": param.description or name}
        if param.type == ParamType.SELECT and param.options:
            attrs["type"] = "select"
            sel = ET.SubElement(inputs_el, "param", **attrs)
            for opt in param.options:
                ET.SubElement(sel, "option", value=opt).text = opt
        elif param.type == ParamType.INTEGER:
            attrs.update(type="integer", value=str(param.default or 0))
            if param.min is not None:
                attrs["min"] = str(param.min)
            if param.max is not None:
                attrs["max"] = str(param.max)
            ET.SubElement(inputs_el, "param", **attrs)
        elif param.type == ParamType.BOOLEAN:
            attrs.update(type="boolean", checked=str(param.default or False).lower())
            ET.SubElement(inputs_el, "param", **attrs)
        else:
            attrs.update(type="text", value=str(param.default or ""))
            ET.SubElement(inputs_el, "param", **attrs)

    outputs_el = ET.SubElement(tool, "outputs")
    for name, out in spec.outputs.items():
        ET.SubElement(
            outputs_el, "data", name=name, format=out.format,
            label=out.description or name,
        )

    ET.indent(tool)
    return ET.tostring(tool, encoding="unicode", xml_declaration=True)


def from_galaxy_xml(xml_str: str) -> ExecutionSpec:
    """Parse a Galaxy tool XML wrapper into a BioLedger ExecutionSpec."""
    root = ET.fromstring(xml_str)

    inputs: dict[str, ToolInput] = {}
    parameters: dict[str, ToolParameter] = {}
    outputs: dict[str, ToolOutput] = {}

    for param in root.findall(".//inputs/param"):
        name = param.get("name", "")
        ptype = param.get("type", "text")

        if ptype == "data":
            fmt = param.get("format", "any")
            inputs[name] = ToolInput(
                type=ParamType.FILE,
                format=fmt,
                description=param.get("label", ""),
            )
        elif ptype == "integer":
            parameters[name] = ToolParameter(
                type=ParamType.INTEGER,
                default=int(param.get("value", 0)),
                min=int(param.get("min")) if param.get("min") else None,
                max=int(param.get("max")) if param.get("max") else None,
                description=param.get("label", ""),
            )
        elif ptype == "select":
            opts = [opt.get("value", "") for opt in param.findall("option")]
            parameters[name] = ToolParameter(
                type=ParamType.SELECT,
                options=opts,
                description=param.get("label", ""),
            )
        elif ptype == "boolean":
            parameters[name] = ToolParameter(
                type=ParamType.BOOLEAN,
                default=param.get("checked", "false").lower() == "true",
                description=param.get("label", ""),
            )

    for data in root.findall(".//outputs/data"):
        name = data.get("name", "")
        outputs[name] = ToolOutput(
            format=data.get("format", "any"),
            description=data.get("label", ""),
        )

    # Extract container from requirements
    container = ""
    for req in root.findall(".//requirements/container"):
        if req.get("type") == "docker":
            container = (req.text or "").strip()
            break

    # Extract command
    command_el = root.find("command")
    command = (command_el.text or "").strip() if command_el is not None else ""

    return ExecutionSpec(
        name=root.get("id", ""),
        version=root.get("version", ""),
        description=(root.findtext("description") or "").strip(),
        container=container,
        command=command,
        inputs=inputs,
        outputs=outputs,
        parameters=parameters,
        status=SpecStatus.DRAFT,  # imported specs start as drafts
    )


async def import_galaxy_tool(
    xml_path: Path,
    deps: ForgeDeps,
    agent: "ToolForgeAgent",  # noqa: F821
    use_llm: bool = True,
) -> ToolSpec:
    """Import a Galaxy tool XML into a BioLedger ToolSpec."""
    xml_str = xml_path.read_text()

    # Step 1: Programmatic translation
    try:
        exec_spec = from_galaxy_xml(xml_str)
    except Exception as e:
        if not use_llm:
            raise
        exec_spec = await agent.parse(xml_str, "Galaxy XML", str(e), deps)

    # Step 2: Programmatic validation
    result = validate_execution(exec_spec, strict=False)

    # Step 3: LLM fix if validation fails
    if not result.is_valid and use_llm:
        exec_spec = await agent.fix(exec_spec, result.issues, deps)
        validate_execution(exec_spec, strict=False)

    # Step 4: LLM conceptual validation
    if use_llm:
        conceptual_issues = await agent.review(exec_spec, "Galaxy XML", deps)
        for issue in conceptual_issues:
            print(f"  {issue}")

    return ToolSpec(execution=exec_spec)


async def export_galaxy_tool(
    spec: ToolSpec,
    deps: ForgeDeps,
    agent: "ToolForgeAgent",  # noqa: F821
    use_llm: bool = True,
) -> str:
    """Export: BioLedger Spec -> Galaxy XML.
    Steps: generate -> validate -> LLM fix (if needed) -> LLM enrich -> re-validate."""
    from ._export_validate import validate_galaxy_xml

    # Step 1: Programmatic generation
    xml_str = to_galaxy_xml(spec.execution)

    # Step 2: Structural validation
    issues = validate_galaxy_xml(xml_str)

    # Step 3: LLM fix if structural issues
    if issues and use_llm:
        issues_str = "\n".join(f"- {i}" for i in issues)
        xml_str = await agent.enrich_export(
            spec, f"ISSUES:\n{issues_str}\n\nXML:\n{xml_str}", "Galaxy XML", deps
        )
        issues = validate_galaxy_xml(xml_str)

    # Step 4: LLM enrichment (add help, citations, test cases)
    if use_llm and not issues:
        xml_str = await agent.enrich_export(spec, xml_str, "Galaxy XML", deps)

    return xml_str
