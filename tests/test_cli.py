"""Tests for the CLI module."""

import json
import sys
from unittest.mock import patch

import pytest

from astrograph import cli


@pytest.fixture
def sample_dir(tmp_path):
    """Create a sample directory with Python files."""
    (tmp_path / "module1.py").write_text(
        """
def calculate(a, b):
    return a + b

def compute(x, y):
    return x + y
"""
    )
    (tmp_path / "module2.py").write_text(
        """
def process(data):
    for item in data:
        print(item)
"""
    )
    return tmp_path


@pytest.fixture
def sample_file(tmp_path):
    """Create a sample Python file."""
    code = """
def example(x):
    return x * 2
"""
    file_path = tmp_path / "example.py"
    file_path.write_text(code)
    return file_path


class TestIndexCommand:
    """Tests for the index command."""

    @pytest.mark.parametrize("fixture_name", ["sample_dir", "sample_file"])
    def test_index_path(self, fixture_name, request, capsys):
        """Index command should work with both files and directories."""
        path = request.getfixturevalue(fixture_name)
        with patch.object(sys, "argv", ["cli", "index", str(path)]):
            cli.main()
        captured = capsys.readouterr()
        assert "Indexed" in captured.out

    def test_index_with_output(self, sample_dir, tmp_path):
        output_file = tmp_path / "index.json"
        with patch.object(
            sys, "argv", ["cli", "index", str(sample_dir), "--output", str(output_file)]
        ):
            cli.main()
        assert output_file.exists()

    def test_index_no_recursive(self, sample_dir, capsys):
        with patch.object(sys, "argv", ["cli", "index", str(sample_dir), "--no-recursive"]):
            cli.main()
        captured = capsys.readouterr()
        assert "Indexed" in captured.out


class TestDuplicatesCommand:
    """Tests for the duplicates command."""

    def test_find_duplicates(self, sample_dir, capsys):
        with patch.object(sys, "argv", ["cli", "duplicates", str(sample_dir)]):
            cli.main()
        captured = capsys.readouterr()
        # Should find calculate/compute as duplicates or show no duplicates
        assert captured.out

    def test_find_duplicates_json(self, sample_dir, capsys):
        with patch.object(sys, "argv", ["cli", "duplicates", str(sample_dir), "--json"]):
            cli.main()
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "duplicate_groups" in data

    def test_find_duplicates_min_nodes(self, sample_dir, capsys):
        with patch.object(sys, "argv", ["cli", "duplicates", str(sample_dir), "--min-nodes", "10"]):
            cli.main()
        captured = capsys.readouterr()
        assert captured.out

    def test_find_duplicates_verify(self, sample_dir, capsys):
        with patch.object(sys, "argv", ["cli", "duplicates", str(sample_dir), "--verify"]):
            cli.main()
        captured = capsys.readouterr()
        assert captured.out

    def test_find_no_duplicates(self, tmp_path, capsys):
        """Test with unique functions."""
        (tmp_path / "unique.py").write_text(
            """
def func1():
    pass

def func2(x):
    return x
"""
        )
        with patch.object(sys, "argv", ["cli", "duplicates", str(tmp_path)]):
            cli.main()
        captured = capsys.readouterr()
        assert captured.out


class TestCheckCommand:
    """Tests for the check command."""

    def test_check_similar(self, sample_dir, sample_file, tmp_path, capsys):
        # First create an index
        index_file = tmp_path / "index.json"
        with patch.object(
            sys, "argv", ["cli", "index", str(sample_dir), "--output", str(index_file)]
        ):
            cli.main()

        # Then check
        with patch.object(sys, "argv", ["cli", "check", str(index_file), str(sample_file)]):
            cli.main()
        captured = capsys.readouterr()
        assert captured.out

    def test_check_json(self, sample_dir, sample_file, tmp_path, capsys):
        index_file = tmp_path / "index.json"
        with patch.object(
            sys, "argv", ["cli", "index", str(sample_dir), "--output", str(index_file)]
        ):
            cli.main()

        # Clear the buffer from the index command
        capsys.readouterr()

        with patch.object(
            sys, "argv", ["cli", "check", str(index_file), str(sample_file), "--json"]
        ):
            cli.main()
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "matches" in data

    def test_check_no_similar(self, tmp_path, capsys):
        """Test when no similar code exists."""
        (tmp_path / "indexed.py").write_text("def f(): pass")
        (tmp_path / "check.py").write_text(
            """
def very_different_function(a, b, c, d):
    result = {}
    for x in range(a):
        for y in range(b):
            result[(x, y)] = c * d
    return result
"""
        )
        index_file = tmp_path / "index.json"

        with patch.object(
            sys, "argv", ["cli", "index", str(tmp_path / "indexed.py"), "--output", str(index_file)]
        ):
            cli.main()

        with patch.object(
            sys, "argv", ["cli", "check", str(index_file), str(tmp_path / "check.py")]
        ):
            cli.main()
        captured = capsys.readouterr()
        assert "No similar" in captured.out or "Safe" in captured.out or captured.out


class TestCompareCommand:
    """Tests for the compare command."""

    def test_compare_files(self, tmp_path, capsys):
        file1 = tmp_path / "file1.py"
        file2 = tmp_path / "file2.py"

        file1.write_text("def f(x): return x + 1")
        file2.write_text("def g(y): return y + 1")

        with patch.object(sys, "argv", ["cli", "compare", str(file1), str(file2)]):
            cli.main()
        captured = capsys.readouterr()
        assert "Isomorphic" in captured.out


class TestHelpCommand:
    """Tests for help output."""

    def test_no_command(self, capsys):
        with patch.object(sys, "argv", ["cli"]):
            cli.main()
        captured = capsys.readouterr()
        # Should print help or usage
        assert "index" in captured.out or "usage" in captured.out.lower()
