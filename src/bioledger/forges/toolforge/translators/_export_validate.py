from __future__ import annotations

import re
import xml.etree.ElementTree as ET


def validate_galaxy_xml(xml_str: str) -> list[str]:
    """Structural checks on generated Galaxy XML."""
    issues: list[str] = []
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError as e:
        return [f"XML parse error: {e}"]
    if root.tag != "tool":
        issues.append("Root element is not <tool>")
    if not root.get("id"):
        issues.append("Missing tool id attribute")
    if root.find("command") is None:
        issues.append("Missing <command> element")
    if root.find(".//requirements/container") is None:
        issues.append("Missing <container> in <requirements>")
    if not root.findall(".//inputs/param"):
        issues.append("No <param> elements in <inputs>")
    if not root.findall(".//outputs/data"):
        issues.append("No <data> elements in <outputs>")
    return issues


def validate_nextflow_dsl2(nf_str: str) -> list[str]:
    """Structural checks on generated Nextflow DSL2 process."""
    issues: list[str] = []
    if not re.search(r"process\s+\w+\s*\{", nf_str):
        issues.append("No process block found")
    if "container" not in nf_str:
        issues.append("Missing container directive")
    if "input:" not in nf_str:
        issues.append("Missing input: block")
    if "output:" not in nf_str:
        issues.append("Missing output: block")
    if not re.search(r"(script|shell):\s*\n", nf_str):
        issues.append("Missing script: or shell: block")
    # Check for unbalanced braces
    if nf_str.count("{") != nf_str.count("}"):
        issues.append("Unbalanced braces in process definition")
    return issues
