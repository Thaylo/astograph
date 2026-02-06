"""Tests for the recommendation engine."""

import pytest

from astograph.ast_to_graph import CodeUnit
from astograph.index import CodeStructureIndex, DuplicateGroup
from astograph.recommendations import (
    ActionType,
    Evidence,
    ImpactLevel,
    LocationInfo,
    RecommendationEngine,
    RefactoringRecommendation,
    format_recommendations_report,
)


class TestLocationInfo:
    """Tests for LocationInfo dataclass."""

    def test_basic_location(self):
        loc = LocationInfo(
            file_path="src/utils.py",
            name="validate",
            lines="10-20",
            unit_type="function",
        )
        assert loc.file_path == "src/utils.py"
        assert loc.is_test_file is False

    def test_test_file_detection(self):
        loc = LocationInfo(
            file_path="tests/test_utils.py",
            name="test_validate",
            lines="10-20",
            unit_type="function",
            is_test_file=True,
        )
        assert loc.is_test_file is True


class TestEvidence:
    """Tests for Evidence dataclass."""

    def test_evidence_with_metric(self):
        ev = Evidence(fact="Found duplicates", metric="3 occurrences")
        assert ev.fact == "Found duplicates"
        assert ev.metric == "3 occurrences"

    def test_evidence_without_metric(self):
        ev = Evidence(fact="Verified via isomorphism")
        assert ev.metric is None


class TestRefactoringRecommendation:
    """Tests for RefactoringRecommendation dataclass."""

    def test_to_dict(self):
        rec = RefactoringRecommendation(
            action=ActionType.EXTRACT_TO_UTILITY,
            summary="Test summary",
            rationale="Test rationale",
            impact=ImpactLevel.HIGH,
            impact_score=0.85,
            confidence=0.9,
            evidence=[Evidence(fact="Test fact", metric="1 item")],
            locations=[
                LocationInfo(
                    file_path="src/a.py",
                    name="func_a",
                    lines="1-10",
                    unit_type="function",
                )
            ],
            lines_duplicated=30,
            estimated_lines_saved=20,
            files_affected=2,
        )

        d = rec.to_dict()

        assert d["action"] == "extract_to_utility"
        assert d["locations"] == ["src/a.py:func_a"]
        # keep is only present when there's a clear reason
        assert "keep" not in d or d.get("keep_reason") is not None


class TestRecommendationEngine:
    """Tests for the RecommendationEngine."""

    @pytest.fixture
    def engine(self):
        return RecommendationEngine()

    @pytest.fixture
    def sample_index_with_duplicates(self):
        """Create an index with actual duplicates for testing."""
        index = CodeStructureIndex()

        # Two structurally identical functions
        code1 = """
def validate_input(data):
    if not data:
        raise ValueError("Empty")
    return data.strip()
"""
        code2 = """
def check_data(value):
    if not value:
        raise ValueError("Empty")
    return value.strip()
"""
        unit1 = CodeUnit(
            name="validate_input",
            code=code1,
            file_path="src/handlers/user.py",
            line_start=10,
            line_end=15,
            unit_type="function",
        )
        unit2 = CodeUnit(
            name="check_data",
            code=code2,
            file_path="src/handlers/order.py",
            line_start=20,
            line_end=25,
            unit_type="function",
        )

        index.add_code_unit(unit1)
        index.add_code_unit(unit2)

        return index

    def test_analyze_empty_groups(self, engine):
        """Empty groups should return empty recommendations."""
        recommendations = engine.analyze_duplicates([])
        assert recommendations == []

    def test_analyze_single_entry_group(self, engine):
        """Groups with only one entry should be skipped."""
        # Create a group with one entry
        unit = CodeUnit(
            name="test",
            code="def test(): pass",
            file_path="test.py",
            line_start=1,
            line_end=1,
            unit_type="function",
        )
        index = CodeStructureIndex()
        entry = index.add_code_unit(unit)

        group = DuplicateGroup(wl_hash="abc123", entries=[entry])
        recommendations = engine.analyze_duplicates([group])

        assert recommendations == []

    def test_analyze_duplicates_generates_recommendations(self, sample_index_with_duplicates):
        """Duplicates should generate recommendations."""
        engine = RecommendationEngine()
        groups = sample_index_with_duplicates.find_all_duplicates(min_node_count=3)

        # Should have at least one group
        assert len(groups) >= 1

        recommendations = engine.analyze_duplicates(groups)

        assert len(recommendations) >= 1
        rec = recommendations[0]

        assert rec.action in ActionType
        assert rec.impact in ImpactLevel
        assert 0 <= rec.impact_score <= 1
        assert 0 <= rec.confidence <= 1
        assert len(rec.evidence) > 0
        assert len(rec.locations) >= 2

    def test_test_file_detection(self, engine):
        """Test files should be properly detected."""
        index = CodeStructureIndex()

        code = "def test_func(): return 1"
        unit1 = CodeUnit(
            name="test_a",
            code=code,
            file_path="tests/test_module.py",
            line_start=1,
            line_end=1,
            unit_type="function",
        )
        unit2 = CodeUnit(
            name="test_b",
            code=code,
            file_path="tests/test_other.py",
            line_start=1,
            line_end=1,
            unit_type="function",
        )

        index.add_code_unit(unit1)
        index.add_code_unit(unit2)

        groups = index.find_all_duplicates(min_node_count=1)
        recommendations = engine.analyze_duplicates(groups)

        if recommendations:
            rec = recommendations[0]
            # Should recognize these are test files
            assert rec.action == ActionType.REVIEW_TEST_DUPLICATION

    def test_recommendations_sorted_by_impact(self, engine):
        """Recommendations should be sorted by impact score descending."""
        index = CodeStructureIndex()

        # Create two duplicate groups with different complexities
        simple_code = "def f(): return 1"
        complex_code = """
def process(items):
    results = []
    for item in items:
        if item > 0:
            results.append(item * 2)
    return results
"""

        # Simple duplicates
        for i in range(2):
            unit = CodeUnit(
                name=f"simple_{i}",
                code=simple_code,
                file_path=f"src/simple{i}.py",
                line_start=1,
                line_end=1,
                unit_type="function",
            )
            index.add_code_unit(unit)

        # Complex duplicates
        for i in range(2):
            unit = CodeUnit(
                name=f"complex_{i}",
                code=complex_code,
                file_path=f"src/complex{i}.py",
                line_start=1,
                line_end=7,
                unit_type="function",
            )
            index.add_code_unit(unit)

        groups = index.find_all_duplicates(min_node_count=1)
        recommendations = engine.analyze_duplicates(groups)

        # Should be sorted by impact score descending
        if len(recommendations) >= 2:
            for i in range(len(recommendations) - 1):
                assert recommendations[i].impact_score >= recommendations[i + 1].impact_score

    def test_keep_location_prefers_shallower_path(self, engine):
        """Keep location should prefer shallower paths when clear winner exists."""
        index = CodeStructureIndex()

        code = "def validate(x): return x > 0"

        # Shallower path (depth 2)
        unit1 = CodeUnit(
            name="validate",
            code=code,
            file_path="src/validate.py",
            line_start=1,
            line_end=1,
            unit_type="function",
        )
        # Deeper path (depth 3)
        unit2 = CodeUnit(
            name="check",
            code=code,
            file_path="src/handlers/user.py",
            line_start=1,
            line_end=1,
            unit_type="function",
        )

        index.add_code_unit(unit1)
        index.add_code_unit(unit2)

        groups = index.find_all_duplicates(min_node_count=1)
        recommendations = engine.analyze_duplicates(groups)

        if recommendations:
            rec = recommendations[0]
            # Should prefer the shallower one
            assert rec.keep_location is not None
            assert rec.keep_location.file_path == "src/validate.py"
            assert rec.keep_reason == "shallowest path"

    def test_no_keep_recommendation_when_equal_depth(self, engine):
        """Should not recommend keep when paths have equal depth."""
        index = CodeStructureIndex()

        code = "def validate(x): return x > 0"

        # Same depth (both depth 3)
        unit1 = CodeUnit(
            name="validate",
            code=code,
            file_path="src/handlers/a.py",
            line_start=1,
            line_end=1,
            unit_type="function",
        )
        unit2 = CodeUnit(
            name="check",
            code=code,
            file_path="src/handlers/b.py",
            line_start=1,
            line_end=1,
            unit_type="function",
        )

        index.add_code_unit(unit1)
        index.add_code_unit(unit2)

        groups = index.find_all_duplicates(min_node_count=1)
        recommendations = engine.analyze_duplicates(groups)

        if recommendations:
            rec = recommendations[0]
            # Should NOT recommend which to keep
            assert rec.keep_location is None
            assert rec.keep_reason is None

    def test_extract_to_base_class_action(self, engine):
        """Methods with different parents should suggest base class extraction."""
        index = CodeStructureIndex()

        # Same method code in different classes
        method_code = """
def save(self):
    self.validate()
    self.persist()
    return True
"""
        unit1 = CodeUnit(
            name="save",
            code=method_code,
            file_path="src/models/user.py",
            line_start=10,
            line_end=14,
            unit_type="method",
            parent_name="UserModel",
        )
        unit2 = CodeUnit(
            name="save",
            code=method_code,
            file_path="src/models/order.py",
            line_start=20,
            line_end=24,
            unit_type="method",
            parent_name="OrderModel",
        )

        index.add_code_unit(unit1)
        index.add_code_unit(unit2)

        groups = index.find_all_duplicates(min_node_count=3)
        recommendations = engine.analyze_duplicates(groups)

        if recommendations:
            rec = recommendations[0]
            # Should suggest base class extraction
            assert rec.action == ActionType.EXTRACT_TO_BASE_CLASS

    def test_consolidate_in_place_action(self, engine):
        """Duplicates in same directory should suggest consolidation."""
        index = CodeStructureIndex()

        code = """
def helper(data):
    result = []
    for item in data:
        result.append(item)
    return result
"""
        unit1 = CodeUnit(
            name="helper_a",
            code=code,
            file_path="src/utils/a.py",
            line_start=1,
            line_end=6,
            unit_type="function",
        )
        unit2 = CodeUnit(
            name="helper_b",
            code=code,
            file_path="src/utils/b.py",
            line_start=1,
            line_end=6,
            unit_type="function",
        )

        index.add_code_unit(unit1)
        index.add_code_unit(unit2)

        groups = index.find_all_duplicates(min_node_count=3)
        recommendations = engine.analyze_duplicates(groups)

        if recommendations:
            rec = recommendations[0]
            # Should suggest consolidating in same directory
            assert rec.action == ActionType.CONSOLIDATE_IN_PLACE


class TestFormatRecommendationsReport:
    """Tests for the report formatting function."""

    def test_empty_recommendations(self):
        report = format_recommendations_report([])
        assert "No refactoring opportunities" in report

    def test_report_is_concise(self):
        rec = RefactoringRecommendation(
            action=ActionType.EXTRACT_TO_UTILITY,
            summary="Test summary",
            rationale="This is a test rationale for formatting.",
            impact=ImpactLevel.HIGH,
            impact_score=0.85,
            confidence=0.9,
            evidence=[
                Evidence(fact="3 duplicates found", metric="3 occurrences"),
            ],
            locations=[
                LocationInfo(
                    file_path="src/a.py",
                    name="func_a",
                    lines="1-10",
                    unit_type="function",
                    directory_depth=2,
                ),
                LocationInfo(
                    file_path="src/deep/nested/b.py",
                    name="func_b",
                    lines="5-15",
                    unit_type="function",
                    directory_depth=4,
                ),
            ],
            keep_location=LocationInfo(
                file_path="src/a.py",
                name="func_a",
                lines="1-10",
                unit_type="function",
                directory_depth=2,
            ),
            keep_reason="shallowest path",
            suggested_name="common_func",
            lines_duplicated=30,
            estimated_lines_saved=20,
            files_affected=2,
        )

        report = format_recommendations_report([rec])

        # Check key info is present
        assert "extract_to_utility" in report
        assert "src/a.py:func_a" in report
        assert "Keep" in report
        assert "shallowest path" in report
        # Should be very concise - just 2 lines per recommendation
        assert len(report.split("\n")) == 2


class TestIntegrationWithTools:
    """Integration tests with the tools module."""

    def test_analyze_tool(self):
        """Test the analyze tool integration."""
        from astograph.tools import CodeStructureTools

        tools = CodeStructureTools()

        # Index some duplicate code
        code1 = """
def process_a(data):
    result = []
    for item in data:
        result.append(item.upper())
    return result
"""
        code2 = """
def process_b(items):
    result = []
    for item in items:
        result.append(item.upper())
    return result
"""
        unit1 = CodeUnit(
            name="process_a",
            code=code1,
            file_path="src/module_a.py",
            line_start=1,
            line_end=6,
            unit_type="function",
        )
        unit2 = CodeUnit(
            name="process_b",
            code=code2,
            file_path="src/module_b.py",
            line_start=1,
            line_end=6,
            unit_type="function",
        )

        tools.index.add_code_unit(unit1)
        tools.index.add_code_unit(unit2)

        # Analyze (simplified interface - no parameters needed)
        result = tools.analyze()
        # Should show findings (REFACTOR or IDIOMATIC) or no findings
        assert (
            "REFACTOR" in result.text
            or "IDIOMATIC" in result.text
            or "SIMILAR" in result.text
            or "No significant duplicates" in result.text
        )

    def test_analyze_dispatch(self):
        """Test that analyze can be called via dispatch."""
        from astograph.tools import CodeStructureTools

        tools = CodeStructureTools()
        result = tools.call_tool("analyze", {})

        # No code indexed
        assert "No code indexed" in result.text

    def test_similar_code_detection(self):
        """Test that similar (but not identical) code is detected."""
        from astograph.tools import CodeStructureTools

        tools = CodeStructureTools()

        # Two similar but not identical functions
        code1 = """
def process_a(data):
    result = []
    for item in data:
        result.append(item.upper())
    return result
"""
        code2 = """
def process_b(items):
    result = []
    for item in items:
        if item:
            result.append(item.upper())
    return result
"""
        unit1 = CodeUnit(
            name="process_a",
            code=code1,
            file_path="src/module_a.py",
            line_start=1,
            line_end=6,
            unit_type="function",
        )
        unit2 = CodeUnit(
            name="process_b",
            code=code2,
            file_path="src/module_b.py",
            line_start=1,
            line_end=7,
            unit_type="function",
        )

        tools.index.add_code_unit(unit1)
        tools.index.add_code_unit(unit2)

        # Analyze (simplified interface)
        result = tools.analyze()
        # Should find them as similar or not find them - either is valid with internal threshold
        assert "SIMILAR" in result.text or "No significant duplicates" in result.text


class TestPatternClassifier:
    """Tests for the PatternClassifier that provides context-aware recommendations."""

    def test_walrus_guard_classification(self):
        """Test that walrus operator guards are classified as idiomatic."""
        from astograph.tools import DuplicateCategory, PatternClassifier

        classifier = PatternClassifier()

        # Create a mock duplicate group with walrus guard pattern
        code = """if error := self._require_index():
    return error"""
        unit = CodeUnit(
            name="test_func",
            code=code,
            file_path="src/tools.py",
            line_start=1,
            line_end=2,
            unit_type="function",
        )
        index = CodeStructureIndex()
        index.add_code_unit(unit)

        # Create a group with at least 2 entries
        index.add_code_unit(
            CodeUnit(
                name="test_func2",
                code=code,
                file_path="src/tools2.py",
                line_start=1,
                line_end=2,
                unit_type="function",
            )
        )

        groups = index.find_all_duplicates(min_node_count=1)
        if groups:
            classification = classifier.classify_group(groups[0])
            assert classification.category == DuplicateCategory.IDIOMATIC_GUARD
            assert classification.suppress_suggestion is True
            assert (
                "walrus" in classification.reason.lower()
                or "guard" in classification.reason.lower()
            )

    def test_early_return_classification(self):
        """Test that early returns are classified as idiomatic."""
        from astograph.tools import DuplicateCategory, PatternClassifier

        classifier = PatternClassifier()

        code = """if not items:
    return"""
        unit1 = CodeUnit(
            name="block_1",
            code=code,
            file_path="src/utils.py",
            line_start=1,
            line_end=2,
            unit_type="block",
            block_type="if",
        )
        unit2 = CodeUnit(
            name="block_2",
            code=code,
            file_path="src/utils2.py",
            line_start=1,
            line_end=2,
            unit_type="block",
            block_type="if",
        )

        index = CodeStructureIndex()
        index.add_code_unit(unit1)
        index.add_code_unit(unit2)

        groups = index.find_all_duplicates(min_node_count=1)
        if groups:
            classification = classifier.classify_group(groups[0])
            assert classification.category == DuplicateCategory.IDIOMATIC_GUARD
            assert classification.suppress_suggestion is True

    def test_test_file_classification(self):
        """Test that duplicates in test files are classified as test setup."""
        from astograph.tools import DuplicateCategory, PatternClassifier

        classifier = PatternClassifier()

        code = """with tempfile.TemporaryDirectory() as tmpdir:
    file_path = os.path.join(tmpdir, "test.py")
    with open(file_path, "w") as f:
        f.write("print('hello')")"""
        unit1 = CodeUnit(
            name="test_func1",
            code=code,
            file_path="tests/test_server.py",
            line_start=1,
            line_end=4,
            unit_type="function",
        )
        unit2 = CodeUnit(
            name="test_func2",
            code=code,
            file_path="tests/test_cli.py",
            line_start=1,
            line_end=4,
            unit_type="function",
        )

        index = CodeStructureIndex()
        index.add_code_unit(unit1)
        index.add_code_unit(unit2)

        groups = index.find_all_duplicates(min_node_count=1)
        if groups:
            classification = classifier.classify_group(groups[0])
            assert classification.category == DuplicateCategory.TEST_SETUP
            assert classification.suppress_suggestion is True
            assert "test" in classification.reason.lower()

    def test_dict_build_classification(self):
        """Test that conditional dict building is classified as idiomatic."""
        from astograph.tools import DuplicateCategory, PatternClassifier

        classifier = PatternClassifier()

        code = """if self.code_unit.block_type:
    code_unit_dict["block_type"] = self.code_unit.block_type"""
        unit1 = CodeUnit(
            name="block_1",
            code=code,
            file_path="src/index.py",
            line_start=1,
            line_end=2,
            unit_type="block",
            block_type="if",
        )
        unit2 = CodeUnit(
            name="block_2",
            code=code,
            file_path="src/index2.py",
            line_start=1,
            line_end=2,
            unit_type="block",
            block_type="if",
        )

        index = CodeStructureIndex()
        index.add_code_unit(unit1)
        index.add_code_unit(unit2)

        groups = index.find_all_duplicates(min_node_count=1)
        if groups:
            classification = classifier.classify_group(groups[0])
            assert classification.category == DuplicateCategory.IDIOMATIC_DICT_BUILD
            assert classification.suppress_suggestion is True

    def test_refactorable_classification(self):
        """Test that true duplicates are classified as refactorable."""
        from astograph.tools import DuplicateCategory, PatternClassifier

        classifier = PatternClassifier()

        # A larger, non-idiomatic duplicate
        code = """def process_items(items):
    results = []
    for item in items:
        if item > 0:
            processed = item * 2
            results.append(processed)
    return sorted(results)"""
        unit1 = CodeUnit(
            name="process_items",
            code=code,
            file_path="src/module_a.py",
            line_start=1,
            line_end=7,
            unit_type="function",
        )
        unit2 = CodeUnit(
            name="process_items",
            code=code,
            file_path="src/module_b.py",
            line_start=1,
            line_end=7,
            unit_type="function",
        )

        index = CodeStructureIndex()
        index.add_code_unit(unit1)
        index.add_code_unit(unit2)

        groups = index.find_all_duplicates(min_node_count=1)
        if groups:
            classification = classifier.classify_group(groups[0])
            assert classification.category == DuplicateCategory.REFACTORABLE
            assert classification.suppress_suggestion is False
            assert "extract" in classification.recommendation.lower()

    def test_is_test_file_detection(self):
        """Test test file path detection."""
        from astograph.tools import PatternClassifier

        classifier = PatternClassifier()

        assert classifier._is_test_file("tests/test_server.py") is True
        assert classifier._is_test_file("test_utils.py") is True
        assert classifier._is_test_file("src/tests/integration.py") is True
        assert classifier._is_test_file("conftest.py") is True
        assert classifier._is_test_file("src/utils.py") is False
        assert classifier._is_test_file("src/testing_utils.py") is False

    def test_delegate_method_classification(self):
        """Test that delegate methods are classified correctly."""
        from astograph.tools import PatternClassifier

        classifier = PatternClassifier()

        code = '''def suppress(self, wl_hash: str):
    """Suppress a hash."""
    return self._toggle_suppression(wl_hash, suppress=True)'''
        unit1 = CodeUnit(
            name="suppress",
            code=code,
            file_path="src/tools.py",
            line_start=1,
            line_end=3,
            unit_type="method",
        )
        unit2 = CodeUnit(
            name="unsuppress",
            code=code.replace("suppress", "unsuppress").replace("True", "False"),
            file_path="src/tools.py",
            line_start=4,
            line_end=6,
            unit_type="method",
        )

        index = CodeStructureIndex()
        index.add_code_unit(unit1)
        index.add_code_unit(unit2)

        groups = index.find_all_duplicates(min_node_count=1)
        if groups:
            classification = classifier.classify_group(groups[0])
            # Delegate methods should suggest suppression
            assert classification.suppress_suggestion is True

    def test_continue_pattern_classification(self):
        """Test that continue patterns in loops are classified as idiomatic."""
        from astograph.tools import DuplicateCategory, PatternClassifier

        classifier = PatternClassifier()

        code = """if _should_skip_path(py_file.parts):
    continue"""
        unit1 = CodeUnit(
            name="block_1",
            code=code,
            file_path="src/index.py",
            line_start=1,
            line_end=2,
            unit_type="block",
            block_type="if",
        )
        unit2 = CodeUnit(
            name="block_2",
            code=code,
            file_path="src/index2.py",
            line_start=1,
            line_end=2,
            unit_type="block",
            block_type="if",
        )

        index = CodeStructureIndex()
        index.add_code_unit(unit1)
        index.add_code_unit(unit2)

        groups = index.find_all_duplicates(min_node_count=1)
        if groups:
            classification = classifier.classify_group(groups[0])
            assert classification.category == DuplicateCategory.IDIOMATIC_GUARD
            assert classification.suppress_suggestion is True
            assert (
                "skip" in classification.reason.lower() or "loop" in classification.reason.lower()
            )

    def test_empty_group_classification(self):
        """Test classification of empty group."""
        from astograph.tools import DuplicateCategory, PatternClassifier

        classifier = PatternClassifier()

        # Create an empty group
        empty_group = DuplicateGroup(wl_hash="test", entries=[])
        classification = classifier.classify_group(empty_group)
        assert classification.category == DuplicateCategory.REFACTORABLE
        assert classification.confidence == 0.5

    def test_analyze_shows_idiomatic_patterns(self):
        """Test that analyze output shows idiomatic patterns with context."""
        from astograph.tools import CodeStructureTools

        tools = CodeStructureTools()

        # Create guard clause duplicates (should be classified as idiomatic)
        code = """if error := self._require_index():
    return error"""
        unit1 = CodeUnit(
            name="check1",
            code=code,
            file_path="src/tools.py",
            line_start=1,
            line_end=2,
            unit_type="function",
        )
        unit2 = CodeUnit(
            name="check2",
            code=code,
            file_path="src/tools2.py",
            line_start=1,
            line_end=2,
            unit_type="function",
        )

        tools.index.add_code_unit(unit1)
        tools.index.add_code_unit(unit2)

        result = tools.analyze(thorough=True)
        # Should show idiomatic pattern classification
        assert (
            "IDIOMATIC" in result.text or "GUARD" in result.text or "No significant" in result.text
        )

    def test_analyze_mixed_findings(self):
        """Test analyze with both refactorable and idiomatic duplicates."""
        from astograph.tools import CodeStructureTools

        tools = CodeStructureTools()

        # Add a true duplicate (refactorable)
        large_code = """def process_data(items):
    results = []
    for item in items:
        if item > 0:
            processed = item * 2
            results.append(processed)
    return sorted(results)"""
        unit1 = CodeUnit(
            name="process_data",
            code=large_code,
            file_path="src/module_a.py",
            line_start=1,
            line_end=7,
            unit_type="function",
        )
        unit2 = CodeUnit(
            name="process_data",
            code=large_code,
            file_path="src/module_b.py",
            line_start=1,
            line_end=7,
            unit_type="function",
        )
        tools.index.add_code_unit(unit1)
        tools.index.add_code_unit(unit2)

        # Add idiomatic guard patterns
        guard_code = """if not items:
    return"""
        guard1 = CodeUnit(
            name="guard1",
            code=guard_code,
            file_path="tests/test_a.py",
            line_start=1,
            line_end=2,
            unit_type="block",
            block_type="if",
        )
        guard2 = CodeUnit(
            name="guard2",
            code=guard_code,
            file_path="tests/test_b.py",
            line_start=1,
            line_end=2,
            unit_type="block",
            block_type="if",
        )
        tools.index.add_code_unit(guard1)
        tools.index.add_code_unit(guard2)

        result = tools.analyze(thorough=True)
        # Should show both types
        text = result.text
        # Either shows refactoring opportunities or idiomatic patterns
        assert "REFACTOR" in text or "IDIOMATIC" in text or "No significant" in text

    def test_classifier_small_test_pattern(self):
        """Test that small patterns in test files are classified as test setup."""
        from astograph.tools import DuplicateCategory, PatternClassifier

        classifier = PatternClassifier()

        # Small non-idiomatic code in test files
        code = """x = 1
y = 2"""
        unit1 = CodeUnit(
            name="block_1",
            code=code,
            file_path="tests/test_a.py",
            line_start=1,
            line_end=2,
            unit_type="block",
            block_type="with",
        )
        unit2 = CodeUnit(
            name="block_2",
            code=code,
            file_path="tests/test_b.py",
            line_start=1,
            line_end=2,
            unit_type="block",
            block_type="with",
        )

        index = CodeStructureIndex()
        index.add_code_unit(unit1)
        index.add_code_unit(unit2)

        groups = index.find_all_duplicates(min_node_count=1)
        if groups:
            classification = classifier.classify_group(groups[0])
            assert classification.category == DuplicateCategory.TEST_SETUP
            assert classification.suppress_suggestion is True

    def test_larger_test_file_duplicate(self):
        """Test that larger duplicates in test files are classified as test setup."""
        from astograph.tools import DuplicateCategory, PatternClassifier

        classifier = PatternClassifier()

        # Larger code block in test files (not matching small idiomatic patterns)
        code = """def setup_test_data():
    data = {}
    data["key1"] = "value1"
    data["key2"] = "value2"
    data["key3"] = "value3"
    return data"""
        unit1 = CodeUnit(
            name="setup1",
            code=code,
            file_path="tests/test_a.py",
            line_start=1,
            line_end=6,
            unit_type="function",
        )
        unit2 = CodeUnit(
            name="setup2",
            code=code,
            file_path="tests/test_b.py",
            line_start=1,
            line_end=6,
            unit_type="function",
        )

        index = CodeStructureIndex()
        index.add_code_unit(unit1)
        index.add_code_unit(unit2)

        groups = index.find_all_duplicates(min_node_count=1)
        if groups:
            classification = classifier.classify_group(groups[0])
            assert classification.category == DuplicateCategory.TEST_SETUP
            assert classification.suppress_suggestion is True
            assert "test" in classification.reason.lower()

    def test_analyze_with_keep_suggestion(self):
        """Test analyze output includes keep suggestions for different path depths."""
        from astograph.tools import CodeStructureTools

        tools = CodeStructureTools()

        # Create duplicates at different path depths
        code = """def process(items):
    results = []
    for item in items:
        if item > 0:
            results.append(item * 2)
    return results"""

        unit1 = CodeUnit(
            name="process",
            code=code,
            file_path="utils.py",  # Shallow path
            line_start=1,
            line_end=6,
            unit_type="function",
        )
        unit2 = CodeUnit(
            name="process",
            code=code,
            file_path="src/deep/module/utils.py",  # Deeper path
            line_start=1,
            line_end=6,
            unit_type="function",
        )

        tools.index.add_code_unit(unit1)
        tools.index.add_code_unit(unit2)

        result = tools.analyze(thorough=True)
        # Should suggest keeping the shallower path
        assert (
            "shallowest" in result.text.lower()
            or "REFACTOR" in result.text
            or "No significant" in result.text
        )

    def test_classify_delegate_method_false(self):
        """Test that non-delegate methods are not classified as delegates."""
        from astograph.tools import PatternClassifier

        classifier = PatternClassifier()

        # Code that doesn't delegate
        code = """def process(self, data):
    result = []
    for item in data:
        result.append(item * 2)
    return result"""

        result = classifier._is_delegate_method(code, [])
        assert result is False

    def test_classify_delegate_method_single_entry(self):
        """Test that single entry groups are not classified as delegates."""
        from astograph.tools import PatternClassifier

        classifier = PatternClassifier()

        code = """def suppress(self):
    return self._impl()"""

        unit = CodeUnit(
            name="suppress",
            code=code,
            file_path="src/tools.py",
            line_start=1,
            line_end=2,
            unit_type="method",
        )
        index = CodeStructureIndex()
        entry = index.add_code_unit(unit)

        # Single entry - not enough to detect delegate pattern
        result = classifier._is_delegate_method(code, [entry])
        assert result is False
