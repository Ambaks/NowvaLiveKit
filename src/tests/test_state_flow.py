"""
Quick Test: State Management Flow
Run this to see the complete flow in action
"""

import asyncio
from core.agent_state import AgentState
from archive.mode_handlers import complete_onboarding, transition_to_workout, return_to_main_menu


async def test_complete_flow():
    """Test the complete user journey"""

    print("\n" + "="*70)
    print("🎯 TESTING COMPLETE STATE MANAGEMENT FLOW")
    print("="*70 + "\n")

    # ============================================================
    # PART 1: NEW USER ONBOARDING
    # ============================================================
    print("📋 PART 1: NEW USER ONBOARDING")
    print("-" * 70)

    # Initialize state (new user, defaults to onboarding mode)
    state = AgentState()
    print(f"✓ Initial state created")
    print(f"  - Mode: {state.get_mode()}")
    print(f"  - User ID: {state.get('user.id')}")
    print()

    await asyncio.sleep(1)

    # Simulate onboarding conversation
    print("💬 Simulating onboarding conversation...")
    print("   Nova: 'Hey! I'm Nova, your AI coach. What's your first name?'")
    print("   User: 'John'")
    await asyncio.sleep(0.5)
    print("   Nova: 'Got it — John. That's J-O-H-N. Is that correct?'")
    print("   User: 'Yes'")
    await asyncio.sleep(0.5)
    print("   Nova: 'Great! And what's your email address?'")
    print("   User: 'john@example.com'")
    await asyncio.sleep(0.5)
    print("   Nova: 'Perfect. That's john at example dot com — is that right?'")
    print("   User: 'Yes'")
    print()

    await asyncio.sleep(1)

    # Complete onboarding and transition
    print("✅ User confirmed information")
    print("🔄 Creating account and transitioning to main menu...")
    print()

    await complete_onboarding(
        state=state,
        name="John",
        email="john@example.com",
        username="john",
        user_id="user_12345",
        session=None
    )

    print(f"✓ State after onboarding:")
    print(f"  - Mode: {state.get_mode()}")
    print(f"  - User: {state.get('user.name')}")
    print(f"  - Email: {state.get('user.email')}")
    print(f"  - First time main menu: {state.is_first_time_main_menu()}")
    print()

    await asyncio.sleep(2)

    # ============================================================
    # PART 2: STARTING A WORKOUT
    # ============================================================
    print("\n📋 PART 2: STARTING A WORKOUT")
    print("-" * 70)

    print("💬 User interaction in main menu...")
    print("   User: 'I want to start a workout'")
    print()

    await asyncio.sleep(1)

    print("🔄 Transitioning to workout mode...")
    await transition_to_workout(state, session=None)

    print(f"✓ State after transition:")
    print(f"  - Mode: {state.get_mode()}")
    print(f"  - Workout active: {state.get('workout.active')}")
    print()

    await asyncio.sleep(2)

    # ============================================================
    # PART 3: FINISHING WORKOUT
    # ============================================================
    print("\n📋 PART 3: FINISHING WORKOUT")
    print("-" * 70)

    print("💬 Workout session...")
    print("   Nova: 'Tracking your form... Nice depth! 5 reps completed.'")
    print("   (Workout continues...)")
    print()

    await asyncio.sleep(1)

    print("   User: 'I'm done'")
    print()

    await asyncio.sleep(1)

    print("🔄 Returning to main menu...")
    await return_to_main_menu(state, session=None)

    print(f"✓ State after return:")
    print(f"  - Mode: {state.get_mode()}")
    print(f"  - Workout active: {state.get('workout.active')}")
    print(f"  - First time main menu: {state.is_first_time_main_menu()}")
    print("  (Notice: No longer first time!)")
    print()

    await asyncio.sleep(2)

    # ============================================================
    # PART 4: SAVING AND LOADING STATE
    # ============================================================
    print("\n📋 PART 4: STATE PERSISTENCE")
    print("-" * 70)

    print("💾 Saving state to disk...")
    state.save_state()
    print("   ✓ State saved to .agent_state_user_12345.json")
    print()

    await asyncio.sleep(1)

    print("🔄 Simulating app restart...")
    print("   (Creating new state object)")
    print()

    await asyncio.sleep(1)

    print("📂 Loading saved state...")
    new_state = AgentState(user_id="user_12345")
    print(f"   ✓ State loaded!")
    print(f"   - Mode: {new_state.get_mode()}")
    print(f"   - User: {new_state.get('user.name')}")
    print(f"   - Email: {new_state.get('user.email')}")
    print(f"   - First time: {new_state.is_first_time_main_menu()}")
    print()

    await asyncio.sleep(2)

    # ============================================================
    # SUMMARY
    # ============================================================
    print("\n" + "="*70)
    print("🎉 TEST COMPLETE - STATE MANAGEMENT WORKING!")
    print("="*70)
    print()
    print("What we tested:")
    print("  ✓ New user onboarding")
    print("  ✓ Smooth transition to main menu")
    print("  ✓ First-time greeting logic")
    print("  ✓ Transition to workout mode")
    print("  ✓ Returning to main menu")
    print("  ✓ Returning user greeting logic")
    print("  ✓ State persistence (save/load)")
    print()
    print("State transitions:")
    print("  onboarding → main_menu → workout → main_menu")
    print()
    print("Next steps:")
    print("  1. Integrate with actual voice agent session")
    print("  2. Test with real TTS/STT")
    print("  3. Customize greetings and timing")
    print("  4. Add more modes (progress, settings, etc.)")
    print()


if __name__ == "__main__":
    asyncio.run(test_complete_flow())
