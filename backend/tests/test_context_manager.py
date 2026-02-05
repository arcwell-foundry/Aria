"""Tests for skill context manager."""

import pytest


def test_summary_verbosity_enum_has_three_levels() -> None:
    """Test SummaryVerbosity enum has MINIMAL, STANDARD, DETAILED."""
    from src.skills.context_manager import SummaryVerbosity

    assert SummaryVerbosity.MINIMAL.value == "minimal"
    assert SummaryVerbosity.STANDARD.value == "standard"
    assert SummaryVerbosity.DETAILED.value == "detailed"
    assert len(SummaryVerbosity) == 3


def test_summary_verbosity_minimal_has_token_target() -> None:
    """Test MINIMAL verbosity has 300 token target."""
    from src.skills.context_manager import SummaryVerbosity

    assert SummaryVerbosity.MINIMAL.token_target == 300


def test_summary_verbosity_standard_has_token_target() -> None:
    """Test STANDARD verbosity has 800 token target."""
    from src.skills.context_manager import SummaryVerbosity

    assert SummaryVerbosity.STANDARD.token_target == 800


def test_summary_verbosity_detailed_has_token_target() -> None:
    """Test DETAILED verbosity has 1500 token target."""
    from src.skills.context_manager import SummaryVerbosity

    assert SummaryVerbosity.DETAILED.token_target == 1500


def test_context_allocation_dataclass_initializes() -> None:
    """Test ContextAllocation initializes with all fields."""
    from src.skills.context_manager import ContextAllocation

    allocation = ContextAllocation(
        component="skill_index",
        allocated_tokens=600,
        used_tokens=450,
        content="# Skill summaries\n...",
    )

    assert allocation.component == "skill_index"
    assert allocation.allocated_tokens == 600
    assert allocation.used_tokens == 450
    assert allocation.content == "# Skill summaries\n..."


def test_context_allocation_has_remaining_tokens_property() -> None:
    """Test ContextAllocation.remaining_tokens returns correct value."""
    from src.skills.context_manager import ContextAllocation

    allocation = ContextAllocation(
        component="working_memory",
        allocated_tokens=800,
        used_tokens=350,
        content="Some content",
    )

    assert allocation.remaining_tokens == 450


def test_context_allocation_remaining_tokens_when_over() -> None:
    """Test remaining_tokens returns 0 when over budget."""
    from src.skills.context_manager import ContextAllocation

    allocation = ContextAllocation(
        component="over_budget",
        allocated_tokens=100,
        used_tokens=150,
        content="Too much content",
    )

    assert allocation.remaining_tokens == 0


def test_context_allocation_is_over_budget_property() -> None:
    """Test is_over_budget returns correct boolean."""
    from src.skills.context_manager import ContextAllocation

    under = ContextAllocation(
        component="under",
        allocated_tokens=100,
        used_tokens=50,
        content="OK",
    )

    over = ContextAllocation(
        component="over",
        allocated_tokens=100,
        used_tokens=150,
        content="Too much",
    )

    assert under.is_over_budget is False
    assert over.is_over_budget is True


def test_skill_context_manager_initializes() -> None:
    """Test SkillContextManager initializes with default budgets."""
    from src.skills.context_manager import SkillContextManager

    manager = SkillContextManager()

    assert manager.orchestrator_budget == 2000
    assert manager.skill_index_budget == 600
    assert manager.working_memory_budget == 800
    assert manager.subagent_budget == 6000


def test_skill_context_manager_accepts_custom_budgets() -> None:
    """Test SkillContextManager accepts custom budget values."""
    from src.skills.context_manager import SkillContextManager

    manager = SkillContextManager(
        orchestrator_budget=5000,
        skill_index_budget=1000,
        working_memory_budget=2000,
        subagent_budget=10000,
    )

    assert manager.orchestrator_budget == 5000
    assert manager.skill_index_budget == 1000
    assert manager.working_memory_budget == 2000
    assert manager.subagent_budget == 10000


def test_estimate_tokens_simple_text() -> None:
    """Test estimate_tokens returns approximate count for simple text."""
    from src.skills.context_manager import SkillContextManager

    manager = SkillContextManager()

    # "Hello world" is 11 chars, approximately 3 tokens
    result = manager.estimate_tokens("Hello world")
    assert result == 2  # 11 // 4 = 2


def test_estimate_tokens_empty_string() -> None:
    """Test estimate_tokens returns 0 for empty string."""
    from src.skills.context_manager import SkillContextManager

    manager = SkillContextManager()

    result = manager.estimate_tokens("")
    assert result == 0


def test_estimate_tokens_longer_text() -> None:
    """Test estimate_tokens scales with longer text."""
    from src.skills.context_manager import SkillContextManager

    manager = SkillContextManager()

    # 400 characters should be approximately 100 tokens
    text = "x" * 400
    result = manager.estimate_tokens(text)
    assert result == 100  # 400 // 4 = 100


def test_estimate_tokens_unicode() -> None:
    """Test estimate_tokens handles unicode characters."""
    from src.skills.context_manager import SkillContextManager

    manager = SkillContextManager()

    # Unicode characters should still count as characters
    text = "Hello 世界 🌍"
    result = manager.estimate_tokens(text)
    # "Hello 世界 🌍" is 10 chars (len() counts codepoints)
    # 10 // 4 = 2
    assert result == 2


def test_compact_if_needed_returns_original_when_under_budget() -> None:
    """Test compact_if_needed returns original when under max_tokens."""
    from src.skills.context_manager import SkillContextManager

    manager = SkillContextManager()

    # Short text, well under budget
    context = "This is short"
    result = manager.compact_if_needed(context, max_tokens=100)

    assert result == "This is short"


def test_compact_if_needed_returns_original_when_exactly_at_budget() -> None:
    """Test compact_if_needed returns original when exactly at max_tokens."""
    from src.skills.context_manager import SkillContextManager

    manager = SkillContextManager()

    # Text that's exactly at budget
    context = "x" * 400  # 400 chars ≈ 100 tokens
    result = manager.compact_if_needed(context, max_tokens=100)

    assert result == context


def test_compact_if_needed_truncates_when_over_budget() -> None:
    """Test compact_if_needed truncates and adds ... when over budget."""
    from src.skills.context_manager import SkillContextManager

    manager = SkillContextManager()

    # Long text over budget
    context = "x" * 800  # 800 chars ≈ 200 tokens, but budget is 100
    result = manager.compact_if_needed(context, max_tokens=100)

    # Should be truncated to fit budget with "..." indicator
    assert result.endswith("...")
    # Result should be shorter than original
    assert len(result) < len(context)
    # Should not exceed budget significantly
    estimated_tokens = manager.estimate_tokens(result)
    assert estimated_tokens <= 100


def test_compact_if_needed_handles_empty_string() -> None:
    """Test compact_if_needed handles empty string."""
    from src.skills.context_manager import SkillContextManager

    manager = SkillContextManager()

    result = manager.compact_if_needed("", max_tokens=100)

    assert result == ""


def test_prepare_orchestrator_context_builds_three_sections() -> None:
    """Test prepare_orchestrator_context builds context with three sections."""
    from src.skills.context_manager import SkillContextManager

    manager = SkillContextManager()

    skill_index = "## Available Skills\n- pdf: Process PDF files\n- docx: Process Word documents"
    plan = "## Execution Plan\n1. Extract text from PDF\n2. Summarize content"
    working_memory = "## Working Memory\n- Previous step completed"

    result = manager.prepare_orchestrator_context(
        skill_index=skill_index,
        plan=plan,
        working_memory=working_memory,
    )

    # Should contain all three sections
    assert "## Available Skills" in result
    assert "## Execution Plan" in result
    assert "## Working Memory" in result


def test_prepare_orchestrator_context_compacts_over_budget_sections() -> None:
    """Test prepare_orchestrator_context compacts sections when over budget."""
    from src.skills.context_manager import SkillContextManager

    # Use very small budgets to force compaction
    manager = SkillContextManager(
        skill_index_budget=10,  # Very small
        working_memory_budget=10,  # Very small
    )

    # Create content that exceeds budgets
    skill_index = "## Available Skills\n" + "x" * 1000
    plan = "## Execution Plan\n1. Step one"
    working_memory = "## Working Memory\n" + "y" * 1000

    result = manager.prepare_orchestrator_context(
        skill_index=skill_index,
        plan=plan,
        working_memory=working_memory,
    )

    # Should still have sections but truncated
    assert "## Available Skills" in result
    assert "## Execution Plan" in result
    assert "## Working Memory" in result
    # Result should be reasonably sized (under orchestrator budget)
    estimated_tokens = manager.estimate_tokens(result)
    assert estimated_tokens <= manager.orchestrator_budget + 100  # Small fudge factor


def test_prepare_orchestrator_context_handles_empty_inputs() -> None:
    """Test prepare_orchestrator_context handles empty inputs gracefully."""
    from src.skills.context_manager import SkillContextManager

    manager = SkillContextManager()

    result = manager.prepare_orchestrator_context(
        skill_index="",
        plan="",
        working_memory="",
    )

    # Should still return structured context with empty sections
    assert "## Available Skills" in result
    assert "## Execution Plan" in result
    assert "## Working Memory" in result


def test_prepare_orchestrator_context_respects_section_order() -> None:
    """Test prepare_orchestrator_context maintains section order."""
    from src.skills.context_manager import SkillContextManager

    manager = SkillContextManager()

    skill_index = "## Available Skills\n- pdf"
    plan = "## Execution Plan\n1. Step"
    working_memory = "## Working Memory\n- Done"

    result = manager.prepare_orchestrator_context(
        skill_index=skill_index,
        plan=plan,
        working_memory=working_memory,
    )

    # Check order: Skills first, then Plan, then Working Memory
    skills_pos = result.find("## Available Skills")
    plan_pos = result.find("## Execution Plan")
    memory_pos = result.find("## Working Memory")

    assert skills_pos < plan_pos < memory_pos


def test_prepare_subagent_context_builds_three_sections() -> None:
    """Test prepare_subagent_context builds context with three sections."""
    from src.skills.context_manager import SkillContextManager

    manager = SkillContextManager()

    task_briefing = "Extract key insights from the PDF"
    skill_content = "## PDF Skill\nProcess PDF files to extract text and metadata"
    input_data = '{"file_path": "/path/to/document.pdf"}'

    result = manager.prepare_subagent_context(
        task_briefing=task_briefing,
        skill_content=skill_content,
        input_data=input_data,
    )

    # Should contain all three sections
    assert "## Task" in result
    assert "## Skill Instructions" in result
    assert "## Input Data" in result


def test_prepare_subagent_context_compacts_over_budget_content() -> None:
    """Test prepare_subagent_context compacts content when over budget."""
    from src.skills.context_manager import SkillContextManager

    # Use moderate subagent budget to force compaction but keep structure
    manager = SkillContextManager(subagent_budget=200)

    task_briefing = "Process this file"
    skill_content = "## Skill Instructions\n" + "x" * 1000
    input_data = '{"data": "' + "y" * 1000 + '"}'

    result = manager.prepare_subagent_context(
        task_briefing=task_briefing,
        skill_content=skill_content,
        input_data=input_data,
    )

    # Should have at least the first section
    assert "## Task" in result
    # Should be reasonably sized
    estimated_tokens = manager.estimate_tokens(result)
    assert estimated_tokens <= manager.subagent_budget + 50  # Small fudge factor
    # Result should be shorter than input
    assert len(result) < len(task_briefing) + len(skill_content) + len(input_data)


def test_prepare_subagent_context_handles_empty_inputs() -> None:
    """Test prepare_subagent_context handles empty inputs gracefully."""
    from src.skills.context_manager import SkillContextManager

    manager = SkillContextManager()

    result = manager.prepare_subagent_context(
        task_briefing="",
        skill_content="",
        input_data="",
    )

    # Should still return structured context with empty sections
    assert "## Task" in result
    assert "## Skill Instructions" in result
    assert "## Input Data" in result


def test_prepare_subagent_context_respects_section_order() -> None:
    """Test prepare_subagent_context maintains section order."""
    from src.skills.context_manager import SkillContextManager

    manager = SkillContextManager()

    task_briefing = "Do the task"
    skill_content = "## Skill\nInstructions here"
    input_data = '{"input": "value"}'

    result = manager.prepare_subagent_context(
        task_briefing=task_briefing,
        skill_content=skill_content,
        input_data=input_data,
    )

    # Check order: Task first, then Skill, then Input Data
    task_pos = result.find("## Task")
    skill_pos = result.find("## Skill Instructions")
    input_pos = result.find("## Input Data")

    assert task_pos < skill_pos < input_pos
