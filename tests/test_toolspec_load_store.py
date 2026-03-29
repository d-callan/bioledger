from __future__ import annotations

from bioledger.toolspec.load import load_spec, save_spec
from bioledger.toolspec.store import ToolStore


def test_save_and_load_spec(tmp_path, sample_tool_spec):
    path = tmp_path / "test.bioledger.yaml"
    save_spec(sample_tool_spec, path)
    assert path.exists()
    loaded = load_spec(path)
    assert loaded.name == sample_tool_spec.name
    assert loaded.execution.container == sample_tool_spec.execution.container
    assert loaded.execution.status == sample_tool_spec.execution.status


def test_tool_store_save_load(tmp_tools_dir, sample_tool_spec):
    store = ToolStore(tools_dir=tmp_tools_dir)
    store.save(sample_tool_spec)
    assert store.has(sample_tool_spec.name)
    loaded = store.load(sample_tool_spec.name)
    assert loaded.name == sample_tool_spec.name


def test_tool_store_list(tmp_tools_dir, sample_tool_spec):
    store = ToolStore(tools_dir=tmp_tools_dir)
    store.save(sample_tool_spec)
    names = store.list_tools()
    assert sample_tool_spec.name in names


def test_tool_store_list_all(tmp_tools_dir, sample_tool_spec):
    store = ToolStore(tools_dir=tmp_tools_dir)
    store.save(sample_tool_spec)
    all_specs = store.list_all()
    assert len(all_specs) == 1
    assert all_specs[0].name == sample_tool_spec.name


def test_tool_store_search_by_name(tmp_tools_dir, sample_tool_spec):
    store = ToolStore(tools_dir=tmp_tools_dir)
    store.save(sample_tool_spec)
    results = store.search(name="fast")
    assert len(results) == 1
    assert results[0].name == "fastqc"


def test_tool_store_search_by_format(tmp_tools_dir, sample_tool_spec):
    store = ToolStore(tools_dir=tmp_tools_dir)
    store.save(sample_tool_spec)
    results = store.search(input_format="fastq")
    assert len(results) == 1
    results = store.search(input_format="bam")
    assert len(results) == 0


def test_tool_store_search_by_category(tmp_tools_dir, sample_tool_spec):
    store = ToolStore(tools_dir=tmp_tools_dir)
    store.save(sample_tool_spec)
    results = store.search(category="quality-control")
    assert len(results) == 1
    results = store.search(category="alignment")
    assert len(results) == 0


def test_tool_store_not_found(tmp_tools_dir):
    store = ToolStore(tools_dir=tmp_tools_dir)
    import pytest

    with pytest.raises(KeyError):
        store.load("nonexistent")


def test_tool_store_cache_invalidation(tmp_tools_dir, sample_tool_spec):
    store = ToolStore(tools_dir=tmp_tools_dir)
    store.save(sample_tool_spec)
    # Populate cache
    store.list_all()
    assert len(store._cache) == 1
    # Invalidate
    store.invalidate_cache()
    assert len(store._cache) == 0
    # Re-populate
    store.list_all()
    assert len(store._cache) == 1
