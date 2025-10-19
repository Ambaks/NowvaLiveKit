"""
Mode Handlers for Nova AI Agent
Handles different modes: onboarding, main_menu, workout
"""

import asyncio
from typing import Optional
from agent_state import AgentState


async def speak(text: str, session=None):
    """
    Wrapper for text-to-speech output

    Args:
        text: Text to speak
        session: Optional AgentSession for voice output
    """
    print(f"\n🤖 Nova: {text}\n")

    if session:
        # Use session's TTS if available
        await session.generate_reply(instructions=f"Say exactly: {text}")
    else:
        # Fallback: just print (for testing without full agent session)
        pass


async def handle_mode_switch(state: AgentState, session=None):
    """
    Route to appropriate handler based on current mode

    Args:
        state: AgentState instance
        session: Optional AgentSession for voice interaction
    """
    mode = state.get_mode()

    print(f"\n[MODE SWITCH] Routing to: {mode}")

    if mode == "onboarding":
        await handle_onboarding(state, session)
    elif mode == "main_menu":
        await handle_main_menu(state, session)
    elif mode == "workout":
        await handle_workout(state, session)
    else:
        print(f"[ERROR] Unknown mode: {mode}")


async def handle_onboarding(state: AgentState, session=None):
    """
    Handle onboarding mode
    This function serves as a placeholder - actual onboarding logic
    is in OnboardingAgent class

    Args:
        state: AgentState instance
        session: Optional AgentSession
    """
    print("[ONBOARDING] Starting onboarding flow...")
    print("[ONBOARDING] (Actual onboarding handled by OnboardingAgent)")

    # The OnboardingAgent will call complete_onboarding() when done
    # which will transition to main_menu


async def handle_main_menu(state: AgentState, session=None):
    """
    Handle main menu mode with first-time greeting logic

    Args:
        state: AgentState instance
        session: Optional AgentSession for voice interaction
    """
    user = state.get_user()
    name = user.get("name", "there")

    # Check if this is first time in main menu
    if state.is_first_time_main_menu():
        print("[MAIN MENU] First-time visit detected")

        # Optional: Play chime or sound effect here
        # await play_chime()

        # First-time greeting
        greeting = (
            f"Welcome to Nowva AI, {name}! [breathe] "
            f"I'll be your workout partner. You can start a workout, "
            f"view your progress, or change your profile settings. "
            f"What would you like to do first?"
        )

        await speak(greeting, session)

        # Mark as visited
        state.mark_main_menu_visited()
        state.save_state()

    else:
        print("[MAIN MENU] Returning user")

        # Returning user greeting
        greeting = (
            f"Welcome back, {name}! [breathe] "
            f"Ready to start your next workout or view progress?"
        )

        await speak(greeting, session)

    # Main menu loop would continue here with user interaction
    # For now, we just show the greeting
    print("[MAIN MENU] Waiting for user input...")


async def handle_workout(state: AgentState, session=None):
    """
    Handle workout mode

    Args:
        state: AgentState instance
        session: Optional AgentSession for voice interaction
    """
    user = state.get_user()
    name = user.get("name", "there")

    print("[WORKOUT] Starting workout mode...")

    greeting = (
        f"Alright {name}, let's do this! [breathe] "
        f"I'm tracking your form and counting reps. "
        f"When you're ready, step up to the rack."
    )

    await speak(greeting, session)

    # Update workout state
    state.set("workout.active", True)
    state.save_state()

    print("[WORKOUT] Workout mode active - ready to track")


async def complete_onboarding(state: AgentState, name: str, email: str,
                              username: str, user_id: str, session=None):
    """
    Complete onboarding and transition to main menu

    This should be called by OnboardingAgent after successful onboarding

    Args:
        state: AgentState instance
        name: User's first name
        email: User's email
        username: Generated username
        user_id: Database user ID
        session: Optional AgentSession for voice interaction
    """
    print(f"\n[ONBOARDING COMPLETE] User: {name} ({email})")

    # Update state with user info
    state.update_user(
        id=user_id,
        name=name,
        email=email,
        username=username,
        created_at=asyncio.get_event_loop().time()
    )

    # Switch to main menu mode
    state.switch_mode("main_menu")
    state.save_state()

    print("[TRANSITION] Onboarding → Main Menu")

    # Small pause for natural transition (optional)
    await asyncio.sleep(0.5)

    # Immediately route to main menu handler
    await handle_mode_switch(state, session)


async def transition_to_workout(state: AgentState, session=None):
    """
    Transition from main menu to workout mode

    Args:
        state: AgentState instance
        session: Optional AgentSession
    """
    print("[TRANSITION] Main Menu → Workout")

    state.switch_mode("workout")
    state.save_state()

    # Small pause for natural transition
    await asyncio.sleep(0.3)

    # Route to workout handler
    await handle_mode_switch(state, session)


async def return_to_main_menu(state: AgentState, session=None):
    """
    Return to main menu from any mode

    Args:
        state: AgentState instance
        session: Optional AgentSession
    """
    current_mode = state.get_mode()
    print(f"[TRANSITION] {current_mode} → Main Menu")

    # Clean up current mode
    if current_mode == "workout":
        state.set("workout.active", False)

    state.switch_mode("main_menu")
    state.save_state()

    # Small pause for natural transition
    await asyncio.sleep(0.3)

    # Route to main menu handler
    await handle_mode_switch(state, session)


# Example usage and testing
if __name__ == "__main__":
    async def test_mode_transitions():
        """Test mode transitions without full agent"""
        print("=== Testing Mode Transitions ===\n")

        # Create new state (onboarding mode by default)
        state = AgentState()

        # Simulate onboarding completion
        print("1. Simulating onboarding...")
        await complete_onboarding(
            state=state,
            name="John",
            email="john@example.com",
            username="john",
            user_id="user_123"
        )

        await asyncio.sleep(2)

        # Transition to workout
        print("\n2. Starting workout...")
        await transition_to_workout(state)

        await asyncio.sleep(2)

        # Return to main menu
        print("\n3. Returning to main menu...")
        await return_to_main_menu(state)

        await asyncio.sleep(2)

        # Visit main menu again (should be returning user greeting)
        print("\n4. Visiting main menu again...")
        await handle_main_menu(state)

        print("\n=== Test Complete ===")
        print(f"Final state: {state}")

    asyncio.run(test_mode_transitions())
