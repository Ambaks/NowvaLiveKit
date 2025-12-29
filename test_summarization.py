#!/usr/bin/env python3
"""
Test script for context summarization functionality
"""
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from core.agent_state import AgentState


def test_fallback_summary():
    """Test the fallback summary generation"""
    print("Testing fallback summary generation...")

    # Import the agent
    from agents.voice_agent import NovaVoiceAgent

    # Create agent with state - start in onboarding mode to avoid prompt issues
    state = AgentState()
    # Set user data first
    state.set("user.id", 1)
    state.set("user.name", "Test User")

    agent = NovaVoiceAgent(state=state)

    # Now switch to program_creation mode and set data
    state.switch_mode("program_creation")
    state.set("program_creation.height_cm", 178)
    state.set("program_creation.weight_kg", 79)
    state.set("program_creation.age", 28)
    state.set("program_creation.sex", "male")
    state.set("program_creation.goal", "build strength")
    state.set("program_creation.experience_level", "intermediate")
    state.set("program_creation.equipment_access", "full gym")
    state.set("program_creation.days_per_week", 4)

    # Generate fallback summary
    summary = agent._build_fallback_summary()

    print(f"Generated summary: {summary}")

    # Verify it contains expected data
    assert "178" in summary, "Height should be in summary"
    assert "79" in summary, "Weight should be in summary"
    assert "28" in summary, "Age should be in summary"
    assert "male" in summary.lower(), "Sex should be in summary"

    print("✅ Fallback summary test passed!")
    return True


def test_items_to_text():
    """Test the items to text conversion"""
    print("\nTesting items to text conversion...")

    from agents.voice_agent import NovaVoiceAgent

    agent = NovaVoiceAgent()

    # Create mock chat items (simple objects with role and content attributes)
    class MockChatItem:
        def __init__(self, role, content):
            self.role = role
            self.content = content

    items = [
        MockChatItem(role="user", content="I'm 5'10 and 175 pounds"),
        MockChatItem(role="assistant", content="Got it, capturing height and weight"),
        MockChatItem(role="user", content="I'm 28 years old, male"),
        MockChatItem(role="assistant", content="Perfect, noted your age and sex"),
    ]

    # Convert to text
    text = agent._items_to_text(items)

    print(f"Generated text:\n{text}")

    # Verify format
    assert "USER:" in text, "Should contain USER role"
    assert "ASSISTANT:" in text, "Should contain ASSISTANT role"
    assert "5'10" in text or "175" in text, "Should contain user's message"

    print("✅ Items to text conversion test passed!")
    return True


def test_constants():
    """Test that constants are properly defined"""
    print("\nTesting constants...")

    from agents import voice_agent

    assert hasattr(voice_agent, 'MAX_CONTEXT_TOKENS'), "MAX_CONTEXT_TOKENS should be defined"
    assert hasattr(voice_agent, 'SUMMARY_TRIGGER_RATIO'), "SUMMARY_TRIGGER_RATIO should be defined"
    assert hasattr(voice_agent, 'SUMMARY_TRIGGER_TOKENS'), "SUMMARY_TRIGGER_TOKENS should be defined"
    assert hasattr(voice_agent, 'KEEP_LAST_TURNS'), "KEEP_LAST_TURNS should be defined"
    assert hasattr(voice_agent, 'SUMMARY_MODEL'), "SUMMARY_MODEL should be defined"

    print(f"MAX_CONTEXT_TOKENS: {voice_agent.MAX_CONTEXT_TOKENS}")
    print(f"SUMMARY_TRIGGER_RATIO: {voice_agent.SUMMARY_TRIGGER_RATIO}")
    print(f"SUMMARY_TRIGGER_TOKENS: {voice_agent.SUMMARY_TRIGGER_TOKENS}")
    print(f"KEEP_LAST_TURNS: {voice_agent.KEEP_LAST_TURNS}")
    print(f"SUMMARY_MODEL: {voice_agent.SUMMARY_MODEL}")

    assert voice_agent.MAX_CONTEXT_TOKENS == 28672, "MAX_CONTEXT_TOKENS should be 28672"
    assert voice_agent.SUMMARY_TRIGGER_RATIO == 0.70, "SUMMARY_TRIGGER_RATIO should be 0.70"
    assert voice_agent.SUMMARY_TRIGGER_TOKENS == 20070, "SUMMARY_TRIGGER_TOKENS should be ~20070"

    print("✅ Constants test passed!")
    return True


def test_state_tracking():
    """Test that state tracking variables are initialized"""
    print("\nTesting state tracking initialization...")

    from agents.voice_agent import NovaVoiceAgent

    agent = NovaVoiceAgent()

    assert hasattr(agent, '_current_token_count'), "_current_token_count should be initialized"
    assert hasattr(agent, '_is_summarizing'), "_is_summarizing should be initialized"
    assert hasattr(agent, '_summary_count'), "_summary_count should be initialized"

    assert agent._current_token_count == 0, "_current_token_count should start at 0"
    assert agent._is_summarizing == False, "_is_summarizing should start as False"
    assert agent._summary_count == 0, "_summary_count should start at 0"

    print("✅ State tracking initialization test passed!")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("CONTEXT SUMMARIZATION TESTS")
    print("=" * 60)

    try:
        test_constants()
        test_state_tracking()
        test_items_to_text()
        test_fallback_summary()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)

    except Exception as e:
        print("\n" + "=" * 60)
        print(f"❌ TEST FAILED: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        sys.exit(1)
