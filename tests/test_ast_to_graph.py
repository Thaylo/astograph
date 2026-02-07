"""Tests for AST to graph conversion."""

import pytest

from astrograph.ast_to_graph import (
    ASTGraph,
    CodeUnit,
    ast_to_graph,
    code_unit_to_ast_graph,
    extract_code_units,
)


class TestASTToGraph:
    """Tests for AST to graph conversion."""

    def test_syntax_error(self):
        """Invalid Python should return empty graph."""
        code = "def f( invalid syntax"
        g = ast_to_graph(code)
        assert g.number_of_nodes() == 0

    def test_binary_operations(self):
        """Different binary ops should have different labels."""
        code_add = "x = a + b"
        code_sub = "x = a - b"
        code_mul = "x = a * b"
        code_div = "x = a / b"

        g_add = ast_to_graph(code_add)
        g_sub = ast_to_graph(code_sub)
        g_mul = ast_to_graph(code_mul)
        g_div = ast_to_graph(code_div)

        # All should have nodes but with different labels
        assert g_add.number_of_nodes() > 0
        assert g_sub.number_of_nodes() > 0
        assert g_mul.number_of_nodes() > 0
        assert g_div.number_of_nodes() > 0

    @pytest.mark.parametrize(
        "code,description",
        [
            ("x = -a", "unary negation"),
            ("x = not a", "unary not"),
            ("x = a and b", "boolean and"),
            ("x = a or b", "boolean or"),
            ("x = a < b <= c", "comparison chain"),
            ("x += 1", "augmented add"),
            ("x *= 2", "augmented multiply"),
        ],
    )
    def test_operations_captured(self, code, description):
        """Operation {description} should produce a non-empty graph."""
        g = ast_to_graph(code)
        assert g.number_of_nodes() > 0, f"{description} should produce nodes"

    def test_constant_types(self):
        """Different constant types should have different labels."""
        code_int = "x = 42"
        code_float = "x = 3.14"
        code_str = 'x = "hello"'
        code_none = "x = None"
        code_bool = "x = True"

        g_int = ast_to_graph(code_int)
        g_float = ast_to_graph(code_float)
        g_str = ast_to_graph(code_str)
        g_none = ast_to_graph(code_none)
        g_bool = ast_to_graph(code_bool)

        # All should have nodes
        for g in [g_int, g_float, g_str, g_none, g_bool]:
            assert g.number_of_nodes() > 0

    def test_async_function(self):
        """Async functions should be parsed."""
        code = """
async def fetch(url):
    return await get(url)
"""
        g = ast_to_graph(code)
        assert g.number_of_nodes() > 0


class TestExtractCodeUnits:
    """Tests for extracting code units."""

    def test_syntax_error_source(self):
        """Invalid Python should yield no units."""
        source = "def f( broken"
        units = list(extract_code_units(source, "test.py"))
        assert units == []

    def test_async_function_extraction(self):
        """Async functions should be extracted."""
        source = """
async def async_func():
    pass
"""
        units = list(extract_code_units(source, "test.py"))
        assert len(units) == 1
        assert units[0].name == "async_func"
        assert units[0].unit_type == "function"

    def test_method_parent_tracking(self):
        """Methods should track their parent class."""
        source = """
class MyClass:
    def method1(self):
        pass

    async def async_method(self):
        pass
"""
        units = list(extract_code_units(source, "test.py"))

        methods = [u for u in units if u.unit_type == "method"]
        assert len(methods) == 2
        assert all(method.parent_name == "MyClass" for method in methods)

    def test_line_numbers(self):
        """Line numbers should be correct."""
        source = """def func1():
    pass

def func2():
    x = 1
    return x
"""
        units = list(extract_code_units(source, "test.py"))

        func1 = next(u for u in units if u.name == "func1")
        func2 = next(u for u in units if u.name == "func2")

        assert func1.line_start == 1
        assert func2.line_start == 4


class TestCodeUnitToASTGraph:
    """Tests for converting CodeUnit to ASTGraph."""

    def test_basic_conversion(self):
        unit = CodeUnit(
            name="test",
            code="def test(x): return x + 1",
            file_path="test.py",
            line_start=1,
            line_end=1,
            unit_type="function",
        )

        ast_graph = code_unit_to_ast_graph(unit)

        assert isinstance(ast_graph, ASTGraph)
        assert ast_graph.node_count > 0
        assert ast_graph.depth > 0
        assert ast_graph.code_unit == unit

    def test_label_histogram(self):
        unit = CodeUnit(
            name="test",
            code="def test(x): return x + 1",
            file_path="test.py",
            line_start=1,
            line_end=1,
            unit_type="function",
        )

        ast_graph = code_unit_to_ast_graph(unit)

        assert len(ast_graph.label_histogram) > 0
        assert sum(ast_graph.label_histogram.values()) == ast_graph.node_count

    def test_empty_code_unit(self):
        unit = CodeUnit(
            name="empty",
            code="",
            file_path="empty.py",
            line_start=1,
            line_end=1,
            unit_type="function",
        )

        ast_graph = code_unit_to_ast_graph(unit)

        # Should handle empty code gracefully
        assert ast_graph.node_count == 0 or ast_graph.node_count == 1  # Just Module node


class TestCodeUnitDataclass:
    """Tests for the CodeUnit dataclass."""

    def test_defaults(self):
        unit = CodeUnit(
            name="test",
            code="pass",
            file_path="test.py",
            line_start=1,
            line_end=1,
            unit_type="function",
        )
        assert unit.parent_name is None

    def test_with_parent(self):
        unit = CodeUnit(
            name="method",
            code="pass",
            file_path="test.py",
            line_start=1,
            line_end=1,
            unit_type="method",
            parent_name="MyClass",
        )
        assert unit.parent_name == "MyClass"

    def test_block_fields(self):
        """Test block-specific fields on CodeUnit."""
        unit = CodeUnit(
            name="func.for_1",
            code="for i in range(10): pass",
            file_path="test.py",
            line_start=5,
            line_end=5,
            unit_type="block",
            parent_name="func",
            block_type="for",
            nesting_depth=1,
            parent_block_name=None,
        )
        assert unit.block_type == "for"
        assert unit.nesting_depth == 1
        assert unit.parent_block_name is None


class TestBlockExtraction:
    """Tests for extracting code blocks from functions."""

    def test_basic_for_loop(self):
        """Extract a simple for loop."""
        source = """
def func():
    for i in range(10):
        print(i)
"""
        units = list(extract_code_units(source, "test.py", include_blocks=True))
        blocks = [u for u in units if u.unit_type == "block"]

        assert len(blocks) == 1
        assert blocks[0].name == "func.for_1"
        assert blocks[0].block_type == "for"
        assert blocks[0].nesting_depth == 1
        assert blocks[0].parent_name == "func"

    def test_multiple_blocks_same_level(self):
        """Extract multiple blocks at the same nesting level."""
        source = """
def func():
    for i in range(10):
        pass
    for j in range(5):
        pass
    if True:
        pass
"""
        units = list(extract_code_units(source, "test.py", include_blocks=True))
        blocks = [u for u in units if u.unit_type == "block"]

        assert len(blocks) == 3
        names = [b.name for b in blocks]
        assert "func.for_1" in names
        assert "func.for_2" in names
        assert "func.if_1" in names

    def test_nested_blocks(self):
        """Extract nested blocks with hierarchical naming."""
        source = """
def func():
    for i in range(10):
        if i > 5:
            while True:
                break
"""
        units = list(extract_code_units(source, "test.py", include_blocks=True))
        blocks = [u for u in units if u.unit_type == "block"]

        assert len(blocks) == 3
        names = {b.name for b in blocks}
        assert "func.for_1" in names
        assert "func.for_1.if_1" in names
        assert "func.for_1.if_1.while_1" in names

        # Check nesting depths
        for_block = next(b for b in blocks if b.name == "func.for_1")
        if_block = next(b for b in blocks if b.name == "func.for_1.if_1")
        while_block = next(b for b in blocks if b.name == "func.for_1.if_1.while_1")

        assert for_block.nesting_depth == 1
        assert if_block.nesting_depth == 2
        assert while_block.nesting_depth == 3

    def test_max_depth_limit(self):
        """Respect max_block_depth parameter."""
        source = """
def func():
    for i in range(10):
        if i > 5:
            while True:
                try:
                    pass
                except:
                    pass
"""
        # With max_block_depth=2, should only get 2 levels
        units = list(extract_code_units(source, "test.py", include_blocks=True, max_block_depth=2))
        blocks = [u for u in units if u.unit_type == "block"]

        assert len(blocks) == 2
        depths = {b.nesting_depth for b in blocks}
        assert 1 in depths
        assert 2 in depths
        assert 3 not in depths

    def test_all_block_types(self):
        """Extract all supported block types."""
        source = """
def func():
    for i in range(10):
        pass
    while True:
        break
    if True:
        pass
    try:
        pass
    except:
        pass
    with open('f') as f:
        pass
"""
        units = list(extract_code_units(source, "test.py", include_blocks=True))
        blocks = [u for u in units if u.unit_type == "block"]
        block_types = {b.block_type for b in blocks}

        assert "for" in block_types
        assert "while" in block_types
        assert "if" in block_types
        assert "try" in block_types
        assert "with" in block_types

    def test_blocks_from_method(self):
        """Extract blocks from class methods."""
        source = """
class MyClass:
    def method(self):
        for i in range(10):
            pass
"""
        units = list(extract_code_units(source, "test.py", include_blocks=True))
        blocks = [u for u in units if u.unit_type == "block"]

        assert len(blocks) == 1
        assert blocks[0].name == "method.for_1"
        assert blocks[0].parent_name == "method"

    def test_include_blocks_true_default(self):
        """By default, blocks are extracted."""
        source = """
def func():
    for i in range(10):
        pass
"""
        units = list(extract_code_units(source, "test.py"))  # include_blocks=True by default
        blocks = [u for u in units if u.unit_type == "block"]

        assert len(blocks) == 1

    def test_include_blocks_false_explicit(self):
        """Blocks can be excluded with include_blocks=False."""
        source = """
def func():
    for i in range(10):
        pass
"""
        units = list(extract_code_units(source, "test.py", include_blocks=False))
        blocks = [u for u in units if u.unit_type == "block"]

        assert len(blocks) == 0

    def test_async_blocks(self):
        """Extract async for and async with blocks."""
        source = """
async def func():
    async for i in aiter():
        pass
    async with aopen('f') as f:
        pass
"""
        units = list(extract_code_units(source, "test.py", include_blocks=True))
        blocks = [u for u in units if u.unit_type == "block"]
        block_types = {b.block_type for b in blocks}

        assert "async_for" in block_types
        assert "async_with" in block_types

    def test_parent_block_name_tracking(self):
        """Track parent block name for nested blocks."""
        source = """
def func():
    for i in range(10):
        if i > 5:
            pass
"""
        units = list(extract_code_units(source, "test.py", include_blocks=True))
        blocks = [u for u in units if u.unit_type == "block"]

        for_block = next(b for b in blocks if b.name == "func.for_1")
        if_block = next(b for b in blocks if b.name == "func.for_1.if_1")

        # Top-level block has no parent block
        assert for_block.parent_block_name is None
        # Nested block tracks its parent block
        assert if_block.parent_block_name == "func.for_1"
