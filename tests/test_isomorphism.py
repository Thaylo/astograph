"""Tests for the graph isomorphism-based code structure analysis."""

import pytest

from astrograph.ast_to_graph import (
    ast_to_graph,
    extract_code_units,
)
from astrograph.canonical_hash import (
    fingerprints_compatible,
    structural_fingerprint,
    weisfeiler_leman_hash,
)
from astrograph.index import CodeStructureIndex


class TestASTToGraph:
    """Tests for AST to graph conversion."""

    def test_simple_function(self):
        code = """
def add(a, b):
    return a + b
"""
        graph = ast_to_graph(code)
        assert graph.number_of_nodes() > 0
        assert graph.number_of_edges() > 0

    @pytest.mark.parametrize(
        "code1,code2,should_match,description",
        [
            # Same structure, different names - should match
            (
                "def add(a, b):\n    return a + b",
                "def sum_values(x, y):\n    return x + y",
                True,
                "isomorphic functions with different names",
            ),
            # Different structure - should not match
            (
                "def add(a, b):\n    return a + b",
                "def add(a, b):\n    result = a + b\n    return result",
                False,
                "different structures",
            ),
            # Complex isomorphic functions - should match
            (
                "def process_items(items):\n    results = []\n    for item in items:\n        if item > 0:\n            results.append(item * 2)\n    return results",
                "def transform_data(data):\n    output = []\n    for element in data:\n        if element > 0:\n            output.append(element * 2)\n    return output",
                True,
                "complex isomorphic functions",
            ),
        ],
    )
    def test_hash_comparison(self, code1, code2, should_match, description):
        """Test WL hash comparison for {description}."""
        g1 = ast_to_graph(code1)
        g2 = ast_to_graph(code2)

        h1 = weisfeiler_leman_hash(g1)
        h2 = weisfeiler_leman_hash(g2)

        if should_match:
            assert h1 == h2, f"Expected same hash for {description}"
        else:
            assert h1 != h2, f"Expected different hash for {description}"


class TestFingerprinting:
    """Tests for structural fingerprinting."""

    @pytest.mark.parametrize(
        "code1,code2,should_be_compatible",
        [
            ("def f(x): return x + 1", "def g(y): return y + 1", True),
            ("def f(x): return x + 1", "def f(x, y): return x + y + 1", False),
        ],
    )
    def test_fingerprint_compatibility(self, code1, code2, should_be_compatible):
        """Test fingerprint compatibility for code pairs."""
        g1 = ast_to_graph(code1)
        g2 = ast_to_graph(code2)

        fp1 = structural_fingerprint(g1)
        fp2 = structural_fingerprint(g2)

        assert fingerprints_compatible(fp1, fp2) == should_be_compatible


class TestCodeStructureIndex:
    """Tests for the code structure index."""

    def test_index_and_find_duplicates(self):
        index = CodeStructureIndex()

        # Create test code units
        from astrograph.ast_to_graph import CodeUnit

        code1 = """
def calculate(a, b):
    return a * b + 1
"""
        code2 = """
def compute(x, y):
    return x * y + 1
"""
        code3 = """
def different(a, b):
    result = a * b
    return result + 1
"""

        unit1 = CodeUnit(
            name="calculate",
            code=code1,
            file_path="file1.py",
            line_start=1,
            line_end=3,
            unit_type="function",
        )
        unit2 = CodeUnit(
            name="compute",
            code=code2,
            file_path="file2.py",
            line_start=1,
            line_end=3,
            unit_type="function",
        )
        unit3 = CodeUnit(
            name="different",
            code=code3,
            file_path="file3.py",
            line_start=1,
            line_end=4,
            unit_type="function",
        )

        index.add_code_unit(unit1)
        index.add_code_unit(unit2)
        index.add_code_unit(unit3)

        duplicates = index.find_all_duplicates(min_node_count=3)

        # code1 and code2 should be in the same group
        assert len(duplicates) >= 1
        assert any(len(group.entries) == 2 for group in duplicates)

    def test_find_similar(self):
        index = CodeStructureIndex()

        from astrograph.ast_to_graph import CodeUnit

        existing_code = """
def process(items):
    for item in items:
        print(item)
"""
        unit = CodeUnit(
            name="process",
            code=existing_code,
            file_path="existing.py",
            line_start=1,
            line_end=4,
            unit_type="function",
        )
        index.add_code_unit(unit)

        # Search for similar code
        new_code = """
def handle(elements):
    for element in elements:
        print(element)
"""
        results = index.find_similar(new_code, min_node_count=3)

        assert len(results) > 0
        assert results[0].similarity_type == "exact"


class TestExtractCodeUnits:
    """Tests for extracting code units from source files."""

    def test_extract_functions(self):
        source = """
def func1(x):
    return x + 1

def func2(y):
    return y * 2

class MyClass:
    def method1(self):
        pass
"""
        units = list(extract_code_units(source, "test.py"))

        names = [u.name for u in units]
        assert "func1" in names
        assert "func2" in names
        assert "MyClass" in names
        assert "method1" in names

    def test_extract_nested_class_methods(self):
        source = """
class Calculator:
    def add(self, a, b):
        return a + b

    def subtract(self, a, b):
        return a - b
"""
        units = list(extract_code_units(source, "calc.py"))

        method_units = [u for u in units if u.unit_type == "method"]
        assert len(method_units) == 2
        assert all(u.parent_name == "Calculator" for u in method_units)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
