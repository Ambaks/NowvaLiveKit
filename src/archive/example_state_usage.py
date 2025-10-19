"""
Example: Complete State Management Integration
Demonstrates how to use the state management system with the Nova AI agent
"""

import asyncio
from agent_state import AgentState
from mode_handlers import (
    handle_mode_switch,
    complete_onboarding,
    transition_to_workout,
    return_to_main_menu
)


async def example_new_user_flow():
    """
    Example: New user complete flow
    Demonstrates onboarding → main menu → workout transitions
    """
    print("\n" + "="*70)
    print("EXAMPLE 1: NEW USER FLOW")
    print("="*70 + "\n")

    # Step 1: Create new state (defaults to onboarding mode)
    print("Step 1: Initialize new user state")
    state = AgentState()
    print(f"  Mode: {state.get_mode()}")
    print(f"  User: {state.get_user()}")
    print()

    await asyncio.sleep(1)

    # Step 2: Simulate onboarding completion
    print("Step 2: User completes onboarding")
    print("  - User provides name: John")
    print("  - User provides email: john@example.com")
    print("  - Account created in database")
    print()

    await asyncio.sleep(1)

    # Step 3: Transition to main menu (with first-time greeting)
    print("Step 3: Transition to main menu")
    await complete_onboarding(
        state=state,
        name="John",
        email="john@example.com",
        username="john",
        user_id="user_123",
        session=None  # No actual voice session for this example
    )
    print(f"  Mode: {state.get_mode()}")
    print(f"  First-time main menu: {state.is_first_time_main_menu()}")
    print()

    await asyncio.sleep(2)

    # Step 4: Transition to workout
    print("Step 4: User starts a workout")
    await transition_to_workout(state, session=None)
    print(f"  Mode: {state.get_mode()}")
    print(f"  Workout active: {state.get('workout.active')}")
    print()

    await asyncio.sleep(2)

    # Step 5: Return to main menu
    print("Step 5: User finishes workout, returns to main menu")
    await return_to_main_menu(state, session=None)
    print(f"  Mode: {state.get_mode()}")
    print(f"  First-time main menu: {state.is_first_time_main_menu()}")
    print("  (Notice: No longer first time, greeting will be different)")
    print()

    # Step 6: Save state
    print("Step 6: Save state to disk")
    state.save_state()
    print("  State saved!")
    print()


async def example_returning_user_flow():
    """
    Example: Returning user flow
    Demonstrates loading saved state and different greeting
    """
    print("\n" + "="*70)
    print("EXAMPLE 2: RETURNING USER FLOW")
    print("="*70 + "\n")

    # Step 1: Load existing user state
    print("Step 1: Load saved user state")
    state = AgentState(user_id="user_123")
    print(f"  Mode: {state.get_mode()}")
    print(f"  User: {state.get('user.name')}")
    print(f"  First-time main menu: {state.is_first_time_main_menu()}")
    print()

    await asyncio.sleep(1)

    # Step 2: Since mode is already main_menu, just call handler
    print("Step 2: Show main menu (returning user greeting)")
    await handle_mode_switch(state, session=None)
    print()


async def example_state_operations():
    """
    Example: Basic state operations
    Demonstrates get/set operations with dot notation
    """
    print("\n" + "="*70)
    print("EXAMPLE 3: STATE OPERATIONS")
    print("="*70 + "\n")

    state = AgentState()

    # Get values
    print("Get values:")
    print(f"  Current mode: {state.get_mode()}")
    print(f"  User name: {state.get('user.name')}")
    print(f"  User email: {state.get('user.email', 'Not set')}")
    print()

    # Set values
    print("Set values:")
    state.set("user.name", "Jane")
    state.set("user.email", "jane@example.com")
    print(f"  User name: {state.get('user.name')}")
    print(f"  User email: {state.get('user.email')}")
    print()

    # Update multiple user fields
    print("Update multiple user fields:")
    state.update_user(
        name="Jane Doe",
        username="janedoe",
        email="jane.doe@example.com"
    )
    print(f"  User: {state.get_user()}")
    print()

    # Mode switches
    print("Mode switches:")
    print(f"  Current mode: {state.get_mode()}")
    state.switch_mode("workout")
    print(f"  New mode: {state.get_mode()}")
    print(f"  Last switch: {state.get('session.last_mode_switch')}")
    print()


async def example_custom_mode_handler():
    """
    Example: Creating a custom mode handler
    Shows how to extend the system with new modes
    """
    print("\n" + "="*70)
    print("EXAMPLE 4: CUSTOM MODE HANDLER")
    print("="*70 + "\n")

    async def handle_progress_mode(state, session=None):
        """Custom handler for viewing progress"""
        user = state.get_user()
        name = user.get("name", "there")

        print(f"\n🤖 Nova: Hey {name}! Let's look at your progress.")
        print("   (This would show workout history, PRs, trends, etc.)")
        print()

    # Create state and switch to custom mode
    state = AgentState()
    state.update_user(name="Alex")
    state.switch_mode("progress")  # Custom mode

    print("Switched to custom 'progress' mode")
    await handle_progress_mode(state)


async def example_error_handling():
    """
    Example: Error handling in state management
    Shows graceful handling of errors
    """
    print("\n" + "="*70)
    print("EXAMPLE 5: ERROR HANDLING")
    print("="*70 + "\n")

    state = AgentState()

    # Try to get non-existent key
    print("Get non-existent key:")
    result = state.get("user.nonexistent", default="DEFAULT_VALUE")
    print(f"  Result: {result}")
    print()

    # Try to load non-existent state
    print("Load non-existent state:")
    state.load_state("nonexistent_user")
    print("  (Handled gracefully, state remains intact)")
    print()

    # Database failure during onboarding (simulated)
    print("Simulating database failure during onboarding:")
    print("  - User provides valid info")
    print("  - Database creation fails")
    print("  - System continues with mode transition")
    print("  - User can retry database creation later")
    print()


async def main():
    """Run all examples"""
    print("\n" + "="*70)
    print("NOVA AI STATE MANAGEMENT - EXAMPLES")
    print("="*70)

    # Run examples sequentially
    await example_new_user_flow()
    await asyncio.sleep(1)

    await example_returning_user_flow()
    await asyncio.sleep(1)

    await example_state_operations()
    await asyncio.sleep(1)

    await example_custom_mode_handler()
    await asyncio.sleep(1)

    await example_error_handling()

    print("\n" + "="*70)
    print("ALL EXAMPLES COMPLETE")
    print("="*70 + "\n")

    print("Next steps:")
    print("1. Integrate with your voice agent session")
    print("2. Add real TTS/STT for voice interaction")
    print("3. Connect to your database")
    print("4. Customize greetings and transitions")
    print("5. Add more modes (progress, settings, etc.)")
    print()


if __name__ == "__main__":
    asyncio.run(main())
