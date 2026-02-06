"""Tests for the canonical hash module."""

import networkx as nx
import pytest

from astograph.ast_to_graph import ast_to_graph
from astograph.canonical_hash import (
    compute_hierarchy_hash,
    fingerprints_compatible,
    structural_fingerprint,
    weisfeiler_leman_hash,
)


class TestWeisfeilerLemanHash:
    """Tests for WL hashing."""

    def test_empty_graph(self):
        g = nx.DiGraph()
        h = weisfeiler_leman_hash(g)
        assert h == "empty"

    def test_single_node(self):
        g = nx.DiGraph()
        g.add_node(0, label="Module")
        h = weisfeiler_leman_hash(g)
        assert h != "empty"
        assert isinstance(h, str)

    @pytest.mark.parametrize(
        "g2_node1_label,should_match",
        [
            ("B", True),  # same structure -> same hash
            ("C", False),  # different label -> different hash
        ],
        ids=["same_structure", "different_structure"],
    )
    def test_hash_comparison(self, g2_node1_label, should_match):
        """Test that same/different structures produce same/different hashes."""
        g1 = nx.DiGraph()
        g1.add_node(0, label="A")
        g1.add_node(1, label="B")
        g1.add_edge(0, 1)

        g2 = nx.DiGraph()
        g2.add_node(0, label="A")
        g2.add_node(1, label=g2_node1_label)
        g2.add_edge(0, 1)

        h1 = weisfeiler_leman_hash(g1)
        h2 = weisfeiler_leman_hash(g2)

        assert (h1 == h2) == should_match

    def test_iterations_affect_hash(self):
        g = nx.DiGraph()
        g.add_node(0, label="A")
        g.add_node(1, label="B")
        g.add_node(2, label="A")
        g.add_edge(0, 1)
        g.add_edge(1, 2)

        h1 = weisfeiler_leman_hash(g, iterations=1)
        h2 = weisfeiler_leman_hash(g, iterations=5)

        # Different iterations may produce different hashes
        # (not guaranteed, but likely for complex graphs)
        assert isinstance(h1, str)
        assert isinstance(h2, str)


class TestStructuralFingerprint:
    """Tests for structural fingerprinting."""

    def test_empty_graph(self):
        g = nx.DiGraph()
        fp = structural_fingerprint(g)
        assert fp.get("empty") is True

    def test_fingerprint_contents(self):
        g = nx.DiGraph()
        g.add_node(0, label="A")
        g.add_node(1, label="B")
        g.add_edge(0, 1)

        fp = structural_fingerprint(g)

        assert fp["n_nodes"] == 2
        assert fp["n_edges"] == 1
        assert "label_counts" in fp
        assert "in_degree_seq" in fp
        assert "out_degree_seq" in fp

    def test_label_counts(self):
        g = nx.DiGraph()
        g.add_node(0, label="A")
        g.add_node(1, label="A")
        g.add_node(2, label="B")

        fp = structural_fingerprint(g)

        assert fp["label_counts"]["A"] == 2
        assert fp["label_counts"]["B"] == 1


class TestFingerprintsCompatible:
    """Tests for fingerprint compatibility checking."""

    def test_both_empty(self):
        fp1 = {"empty": True}
        fp2 = {"empty": True}
        assert fingerprints_compatible(fp1, fp2)

    def test_one_empty(self):
        fp1 = {"empty": True}
        fp2 = {
            "n_nodes": 5,
            "n_edges": 4,
            "label_counts": {},
            "in_degree_seq": [],
            "out_degree_seq": [],
        }
        assert not fingerprints_compatible(fp1, fp2)

    def test_compatible(self):
        fp1 = {
            "n_nodes": 5,
            "n_edges": 4,
            "label_counts": {"A": 2, "B": 3},
            "in_degree_seq": [0, 1, 1, 1, 1],
            "out_degree_seq": [1, 1, 1, 1, 0],
        }
        fp2 = dict(fp1)  # Same fingerprint
        assert fingerprints_compatible(fp1, fp2)

    @pytest.mark.parametrize(
        "fp2_overrides",
        [{"n_nodes": 6}, {"n_edges": 5}],
        ids=["different_nodes", "different_edges"],
    )
    def test_different_counts_incompatible(self, fp2_overrides):
        """Different node/edge counts make fingerprints incompatible."""
        fp1 = {
            "n_nodes": 5,
            "n_edges": 4,
            "label_counts": {},
            "in_degree_seq": [],
            "out_degree_seq": [],
        }
        fp2 = {**fp1, **fp2_overrides}
        assert not fingerprints_compatible(fp1, fp2)

    def test_different_label_counts(self):
        fp1 = {
            "n_nodes": 5,
            "n_edges": 4,
            "label_counts": {"A": 2},
            "in_degree_seq": [],
            "out_degree_seq": [],
        }
        fp2 = {
            "n_nodes": 5,
            "n_edges": 4,
            "label_counts": {"A": 3},
            "in_degree_seq": [],
            "out_degree_seq": [],
        }
        assert not fingerprints_compatible(fp1, fp2)


class TestComputeHierarchyHash:
    """Tests for hierarchical hashing."""

    def test_empty_graph(self):
        g = nx.DiGraph()
        hashes = compute_hierarchy_hash(g, max_depth=3)
        assert all(h == "empty" for h in hashes)

    def test_hierarchy_depth(self):
        g = nx.DiGraph()
        g.add_node(0, label="A")
        g.add_node(1, label="B")
        g.add_node(2, label="C")
        g.add_edge(0, 1)
        g.add_edge(1, 2)

        hashes = compute_hierarchy_hash(g, max_depth=5)
        assert len(hashes) == 5

    def test_graph_without_root(self):
        # Create a cycle (no root)
        g = nx.DiGraph()
        g.add_node(0, label="A")
        g.add_node(1, label="B")
        g.add_edge(0, 1)
        g.add_edge(1, 0)

        # Should still work, picking arbitrary root
        hashes = compute_hierarchy_hash(g, max_depth=3)
        assert len(hashes) == 3

    def test_hierarchy_from_ast(self):
        code = """
def f(x):
    if x > 0:
        return x
    return 0
"""
        g = ast_to_graph(code)
        hashes = compute_hierarchy_hash(g, max_depth=5)

        assert len(hashes) == 5
        # Shallow levels should have different hashes than deeper levels
        # (as more structure is captured)


class TestASTGraphHashing:
    """Tests for hashing real AST graphs."""

    @pytest.mark.parametrize(
        "code1,code2,description",
        [
            ("def f(a, b): return a + b", "def f(a, b): return a * b", "operators"),
            ("x = 1", 'x = "1"', "constant types"),
            ("def f(x): return x < 0", "def f(x): return x > 0", "comparison operators"),
        ],
    )
    def test_different_code_produces_different_hashes(self, code1, code2, description):
        """Different {description} should produce different hashes."""
        g1 = ast_to_graph(code1)
        g2 = ast_to_graph(code2)

        h1 = weisfeiler_leman_hash(g1)
        h2 = weisfeiler_leman_hash(g2)

        assert h1 != h2, f"Expected different hashes for different {description}"
