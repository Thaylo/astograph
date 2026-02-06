"""
Recommendation engine for code refactoring suggestions.

Generates evidence-based recommendations from duplicate detection results.
All recommendations are suggestions with supporting evidence - the agent
decides whether to act on them.
"""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .index import DuplicateGroup, IndexEntry


class ActionType(Enum):
    """Types of refactoring actions that can be recommended."""

    EXTRACT_TO_UTILITY = "extract_to_utility"
    CONSOLIDATE_IN_PLACE = "consolidate_in_place"
    EXTRACT_TO_BASE_CLASS = "extract_to_base_class"
    REVIEW_TEST_DUPLICATION = "review_test_duplication"
    NO_ACTION = "no_action"


class ImpactLevel(Enum):
    """Impact level of a recommendation."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    TRIVIAL = "trivial"


@dataclass
class Evidence:
    """A piece of evidence supporting a recommendation."""

    fact: str
    metric: str | None = None  # e.g., "45 lines", "3 occurrences"


@dataclass
class LocationInfo:
    """Information about a code location."""

    file_path: str
    name: str
    lines: str
    unit_type: str
    parent_name: str | None = None
    is_test_file: bool = False
    directory_depth: int = 0


@dataclass
class RefactoringRecommendation:
    """A recommendation for refactoring duplicate code."""

    # Core recommendation
    action: ActionType
    summary: str
    rationale: str

    # Scoring
    impact: ImpactLevel
    impact_score: float  # 0.0 - 1.0
    confidence: float  # 0.0 - 1.0

    # Evidence
    evidence: list[Evidence] = field(default_factory=list)

    # Locations involved
    locations: list[LocationInfo] = field(default_factory=list)
    keep_location: LocationInfo | None = None
    keep_reason: str | None = None
    remove_locations: list[LocationInfo] = field(default_factory=list)

    # Suggested name (based on common tokens in existing names)
    suggested_name: str | None = None

    # Estimated benefit
    lines_duplicated: int = 0
    estimated_lines_saved: int = 0
    files_affected: int = 0

    def to_dict(self) -> dict:
        """Convert to compact dictionary for JSON serialization."""
        result = {
            "action": self.action.value,
            "locations": [f"{loc.file_path}:{loc.name}" for loc in self.locations],
        }
        if self.keep_location and self.keep_reason:
            result["keep"] = f"{self.keep_location.file_path}:{self.keep_location.name}"
            result["keep_reason"] = self.keep_reason
        return result


class RecommendationEngine:
    """
    Generates refactoring recommendations from duplicate detection results.

    All outputs are framed as suggestions with evidence, allowing the
    consuming agent to make the final decision.
    """

    # Patterns that indicate test files
    TEST_PATTERNS = ("test_", "_test.py", "tests/", "test/", "spec_", "_spec.py")

    def __init__(self) -> None:
        pass

    def analyze_duplicates(
        self,
        groups: list[DuplicateGroup],
        verify_func: Callable[[IndexEntry, IndexEntry], bool] | None = None,
    ) -> list[RefactoringRecommendation]:
        """
        Analyze duplicate groups and generate recommendations.

        Args:
            groups: Duplicate groups from the index
            verify_func: Optional function to verify isomorphism

        Returns:
            List of recommendations sorted by impact score
        """
        recommendations = []

        for group in groups:
            if len(group.entries) < 2:
                continue

            recommendation = self._analyze_group(group, verify_func)
            if recommendation.action != ActionType.NO_ACTION:
                recommendations.append(recommendation)

        # Sort by impact score descending
        recommendations.sort(key=lambda r: r.impact_score, reverse=True)
        return recommendations

    def _analyze_group(
        self,
        group: DuplicateGroup,
        verify_func: Callable[[IndexEntry, IndexEntry], bool] | None = None,
    ) -> RefactoringRecommendation:
        """Analyze a single duplicate group and generate a recommendation."""
        entries = group.entries
        locations = [self._extract_location_info(e) for e in entries]

        # Gather evidence
        evidence = []
        is_verified = group.is_verified

        # Verify if function provided and not already verified
        if verify_func and not is_verified and len(entries) >= 2:
            is_verified = verify_func(entries[0], entries[1])

        # Basic facts
        evidence.append(
            Evidence(
                fact=f"{len(entries)} structurally identical code units detected",
                metric=f"{len(entries)} occurrences",
            )
        )

        # Calculate total duplicated lines
        total_lines = sum(self._count_lines(e) for e in entries)
        avg_lines = total_lines // len(entries) if entries else 0
        evidence.append(
            Evidence(
                fact=f"Each instance contains approximately {avg_lines} lines",
                metric=f"{avg_lines} lines each",
            )
        )

        # Node complexity
        avg_nodes = sum(e.node_count for e in entries) // len(entries)
        evidence.append(
            Evidence(
                fact=f"AST complexity: {avg_nodes} nodes per instance",
                metric=f"{avg_nodes} AST nodes",
            )
        )

        # Verification status
        if is_verified:
            evidence.append(
                Evidence(fact="Structural equivalence verified via VF2 graph isomorphism")
            )
        else:
            evidence.append(
                Evidence(fact="Structural equivalence indicated by matching Weisfeiler-Leman hash")
            )

        # Test file analysis
        test_locations = [loc for loc in locations if loc.is_test_file]
        prod_locations = [loc for loc in locations if not loc.is_test_file]

        if test_locations and prod_locations:
            evidence.append(
                Evidence(
                    fact="Duplication spans test and production code",
                    metric=f"{len(prod_locations)} prod, {len(test_locations)} test",
                )
            )
        elif test_locations:
            evidence.append(
                Evidence(
                    fact="All instances are in test files",
                    metric=f"{len(test_locations)} test files",
                )
            )
        else:
            evidence.append(
                Evidence(
                    fact="All instances are in production code",
                    metric=f"{len(prod_locations)} production files",
                )
            )

        # Determine action type
        action = self._determine_action(locations, entries)

        # Calculate scores
        impact_score = self._calculate_impact_score(entries, locations)
        confidence = self._calculate_confidence(entries, is_verified, locations)
        impact_level = self._score_to_impact_level(impact_score)

        # Determine which location to keep (only if there's a clear reason)
        keep_location, keep_reason = self._select_keep_location(locations, entries)
        remove_locations = (
            [loc for loc in locations if loc != keep_location] if keep_location else []
        )

        # Suggest name
        suggested_name = self._suggest_name(entries)

        # Calculate benefit
        lines_duplicated = total_lines
        estimated_saved = total_lines - avg_lines  # Keep one copy

        # Generate summary and rationale
        summary, rationale = self._generate_summary(
            action, len(entries), avg_lines, impact_level, locations
        )

        return RefactoringRecommendation(
            action=action,
            summary=summary,
            rationale=rationale,
            impact=impact_level,
            impact_score=impact_score,
            confidence=confidence,
            evidence=evidence,
            locations=locations,
            keep_location=keep_location,
            keep_reason=keep_reason,
            remove_locations=remove_locations,
            suggested_name=suggested_name,
            lines_duplicated=lines_duplicated,
            estimated_lines_saved=estimated_saved,
            files_affected=len({loc.file_path for loc in locations}),
        )

    def _extract_location_info(self, entry: IndexEntry) -> LocationInfo:
        """Extract location information from an index entry."""
        file_path = entry.code_unit.file_path
        is_test = any(pattern in file_path.lower() for pattern in self.TEST_PATTERNS)
        depth = len(Path(file_path).parts)

        return LocationInfo(
            file_path=file_path,
            name=entry.code_unit.name,
            lines=f"{entry.code_unit.line_start}-{entry.code_unit.line_end}",
            unit_type=entry.code_unit.unit_type,
            parent_name=entry.code_unit.parent_name,
            is_test_file=is_test,
            directory_depth=depth,
        )

    def _count_lines(self, entry: IndexEntry) -> int:
        """Count lines in a code unit."""
        return entry.code_unit.line_end - entry.code_unit.line_start + 1

    def _score_by_thresholds(
        self, value: float, thresholds: list[tuple[float, float]], default: float
    ) -> float:
        """Return score based on threshold ranges (thresholds checked high to low)."""
        for threshold, score in thresholds:
            if value >= threshold:
                return score
        return default

    def _determine_action(
        self, locations: list[LocationInfo], entries: list[IndexEntry]
    ) -> ActionType:
        """Determine the recommended action type based on context."""
        test_count = sum(1 for loc in locations if loc.is_test_file)
        prod_count = len(locations) - test_count

        # All in test files - might be intentional
        if prod_count == 0:
            return ActionType.REVIEW_TEST_DUPLICATION

        # All methods with same parent structure - might benefit from base class
        if all(e.code_unit.unit_type == "method" for e in entries):
            parent_names = {e.code_unit.parent_name for e in entries}
            if len(parent_names) > 1 and all(parent_names):
                return ActionType.EXTRACT_TO_BASE_CLASS

        # Check if files are in same directory
        directories = {str(Path(loc.file_path).parent) for loc in locations}
        if len(directories) == 1:
            return ActionType.CONSOLIDATE_IN_PLACE

        # Default: extract to utility
        return ActionType.EXTRACT_TO_UTILITY

    def _calculate_impact_score(
        self, entries: list[IndexEntry], locations: list[LocationInfo]
    ) -> float:
        """
        Calculate impact score (0.0 - 1.0).

        Factors:
        - Number of duplicates (more = higher impact)
        - Code complexity (more nodes = higher impact)
        - Location (production code = higher impact)
        - Lines of code
        """
        score = 0.0

        # Frequency factor (2 occurrences = 0.2, 5+ = 0.3)
        freq_score = min(0.3, 0.1 + (len(entries) - 1) * 0.05)
        score += freq_score

        # Complexity factor (based on node count)
        avg_nodes = sum(e.node_count for e in entries) / len(entries)
        score += self._score_by_thresholds(avg_nodes, [(50, 0.3), (20, 0.25), (10, 0.15)], 0.05)

        # Production code factor
        prod_count = sum(1 for loc in locations if not loc.is_test_file)
        prod_ratio = prod_count / len(locations)
        score += prod_ratio * 0.25

        # Lines factor
        avg_lines = sum(self._count_lines(e) for e in entries) / len(entries)
        score += self._score_by_thresholds(avg_lines, [(30, 0.15), (15, 0.1), (5, 0.05)], 0.0)

        return min(1.0, score)

    def _calculate_confidence(
        self, entries: list[IndexEntry], is_verified: bool, locations: list[LocationInfo]
    ) -> float:
        """
        Calculate confidence score (0.0 - 1.0).

        Higher confidence when:
        - Isomorphism is verified
        - Code is non-trivial
        - Duplicates are in production code
        """
        score = 0.5  # Base confidence

        # Verification bonus
        if is_verified:
            score += 0.25
        else:
            score += 0.1  # WL hash still provides confidence

        # Complexity bonus (trivial code = less confident it's worth refactoring)
        avg_nodes = sum(e.node_count for e in entries) / len(entries)
        if avg_nodes >= 15:
            score += 0.15
        elif avg_nodes >= 8:
            score += 0.1
        else:
            score += 0.0

        # Production code bonus
        prod_count = sum(1 for loc in locations if not loc.is_test_file)
        if prod_count == len(locations):
            score += 0.1
        elif prod_count > 0:
            score += 0.05

        return min(1.0, score)

    def _score_to_impact_level(self, score: float) -> ImpactLevel:
        """Convert numeric score to impact level."""
        if score >= 0.7:
            return ImpactLevel.HIGH
        elif score >= 0.45:
            return ImpactLevel.MEDIUM
        elif score >= 0.25:
            return ImpactLevel.LOW
        else:
            return ImpactLevel.TRIVIAL

    def _select_keep_location(
        self, locations: list[LocationInfo], _entries: list[IndexEntry]
    ) -> tuple[LocationInfo | None, str | None]:
        """
        Select which location to keep based on path depth.

        Returns (location, reason) or (None, None) if no clear winner.
        Only recommends if there's a clear reason.
        """
        if not locations:
            return None, None

        # Sort by depth (shallowest first)
        sorted_locs = sorted(locations, key=lambda loc: loc.directory_depth)
        shallowest = sorted_locs[0]

        # Check if there's a clear winner (unique shallowest)
        shallowest_count = sum(
            1 for loc in locations if loc.directory_depth == shallowest.directory_depth
        )

        if shallowest_count == 1:
            return shallowest, "shallowest path"

        # No clear winner
        return None, None

    def _suggest_name(self, entries: list[IndexEntry]) -> str:
        """Suggest a name for the extracted function based on existing names."""
        names = [e.code_unit.name for e in entries]

        # Find common tokens
        all_tokens: list[list[str]] = []
        for name in names:
            # Split by underscore and camelCase
            tokens = []
            current = ""
            for char in name:
                if char == "_":
                    if current:
                        tokens.append(current.lower())
                    current = ""
                elif char.isupper() and current:
                    tokens.append(current.lower())
                    current = char
                else:
                    current += char
            if current:
                tokens.append(current.lower())
            all_tokens.append(tokens)

        # Count token frequency
        token_counts: Counter[str] = Counter()
        for tokens in all_tokens:
            token_counts.update(tokens)

        # Find tokens that appear in majority of names
        threshold = len(names) // 2 + 1
        common_tokens = [t for t, c in token_counts.most_common() if c >= threshold]

        if common_tokens:
            return "_".join(common_tokens[:3])  # Limit to 3 tokens

        # Fallback: return shortest name
        return min(names, key=len)

    def _generate_summary(
        self,
        action: ActionType,
        count: int,
        avg_lines: int,
        _impact: ImpactLevel,
        locations: list[LocationInfo],
    ) -> tuple[str, str]:
        """Generate human-readable summary and rationale."""
        files_affected = len({loc.file_path for loc in locations})

        if action == ActionType.EXTRACT_TO_UTILITY:
            summary = f"Consider extracting {count} duplicate implementations to a shared utility"
            rationale = (
                f"Found {count} structurally identical code blocks (~{avg_lines} lines each) "
                f"across {files_affected} files. Extracting to a shared utility would reduce "
                f"maintenance burden and ensure consistent behavior."
            )
        elif action == ActionType.CONSOLIDATE_IN_PLACE:
            summary = f"Consider consolidating {count} duplicates within the same directory"
            rationale = (
                f"Found {count} identical implementations in the same directory. "
                f"Consolidating into a single local function would improve maintainability."
            )
        elif action == ActionType.EXTRACT_TO_BASE_CLASS:
            summary = f"Consider extracting {count} duplicate methods to a base class"
            rationale = (
                f"Found {count} identical methods across different classes. "
                f"A base class or mixin could eliminate this duplication while preserving "
                f"the object-oriented design."
            )
        elif action == ActionType.REVIEW_TEST_DUPLICATION:
            summary = f"Review {count} similar test implementations"
            rationale = (
                f"Found {count} structurally identical code blocks in test files. "
                f"This may be intentional (test isolation) or could benefit from "
                f"test fixtures/helpers. Review to determine if consolidation is appropriate."
            )
        else:
            summary = "No action recommended"
            rationale = "The detected similarity does not warrant refactoring."

        return summary, rationale


def format_recommendations_report(recommendations: list[RefactoringRecommendation]) -> str:
    """Format recommendations concisely for AI agent consumption."""
    if not recommendations:
        return "No refactoring opportunities identified."

    lines = []
    for i, rec in enumerate(recommendations, 1):
        locs = ", ".join(f"{loc.file_path}:{loc.name}" for loc in rec.locations)
        lines.append(f"{i}. {rec.action.value}: {locs}")

        if rec.keep_location and rec.keep_reason:
            keep = f"{rec.keep_location.file_path}:{rec.keep_location.name}"
            lines.append(f"   -> Keep {keep} ({rec.keep_reason})")

    return "\n".join(lines)
