from __future__ import annotations

from pathlib import Path

from isatools import isatab
from isatools.model import (
    Investigation,
    OntologyAnnotation,
    OntologySource,
    Sample,
    Source,
    Study,
)

from .models import ISAStudySpec


def create_investigation(spec: ISAStudySpec) -> Investigation:
    """Build an isatools Investigation from a validated spec."""
    inv = Investigation(identifier=spec.investigation_id)
    inv.title = spec.title
    inv.description = spec.description

    # Ontology sources
    for src in spec.ontology_sources:
        inv.ontology_source_references.append(
            OntologySource(name=src.name, file=src.file, version=src.version)
        )

    study = Study(
        identifier=spec.study_id,
        title=spec.study_title,
        description=spec.study_description,
    )

    # Build sources → samples
    for src_spec in spec.sources:
        source = Source(name=src_spec.name)
        for char in src_spec.characteristics:
            source.characteristics.append(
                OntologyAnnotation(term=char.term, term_source=None)
            )
        study.sources.append(source)

    for sample_spec in spec.samples:
        sample = Sample(name=sample_spec.name)
        study.samples.append(sample)

    inv.studies.append(study)
    return inv


def write_isatab(investigation: Investigation, output_dir: Path) -> Path:
    """Serialize to ISA-Tab files on disk."""
    output_dir.mkdir(parents=True, exist_ok=True)
    isatab.dump(investigation, str(output_dir))
    return output_dir
