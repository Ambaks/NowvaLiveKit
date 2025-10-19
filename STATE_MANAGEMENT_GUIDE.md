# Nova AI Agent State Management Guide

## Overview

The Nova AI agent now features a comprehensive state management system that supports smooth transitions between different interaction modes and persistent user sessions.

## Architecture

### Core Components

1. **`agent_state.py`** - State management class
2. **`mode_handlers.py`** - Mode transition handlers and routing
3. **`onboarding_agent.py`** - Updated with state integration

### State Structure

```python
state = {
    "mode": "onboarding",  # Current mode
    "user": {
        "id": "user_123",
        "username": "john",
        "name": "John",
        "email": "john@example.com",
        "first_time_main_menu": True,
        "created_at": "2025-01-15T10:30:00"
    },
    "session": {
        "started_at": "2025-01-15T10:30:00",
        "last_mode_switch": {
            "from": "onboarding",
            "to": "main_menu",
            "timestamp": "2025-01-15T10:35:00"
        },
        "conversation_history": []
    },
    "workout": {
        "active": False,
        "exercise": None,
        "reps": 0,
        "sets": 0
    }
}
```

## Modes

### 1. Onboarding Mode
- **Purpose**: New user registration
- **Features**:
  - Voice-driven name and email capture
  - Confirmation with spelling
  - Database account creation
  - Automatic transition to main menu

### 2. Main Menu Mode
- **Purpose**: Primary interaction hub
- **Features**:
  - First-time welcome greeting
  - Returning user greeting
  - Access to workout, progress, and settings

### 3. Workout Mode
- **Purpose**: Active workout session
- **Features**:
  - Form tracking
  - Rep counting
  - Real-time coaching feedback

## Flow Examples

### New User Flow

```
START (mode: onboarding)
    ↓
User provides name & email
    ↓
Account created in database
    ↓
State updated with user info
    ↓
MODE SWITCH: onboarding → main_menu
    ↓
First-time greeting plays
    ↓
state.user.first_time_main_menu = False
    ↓
User interaction continues...
```

### Returning User Flow

```
START (mode: main_menu, loaded from saved state)
    ↓
Returning user greeting plays
    ↓
User can choose: workout, progress, settings
    ↓
MODE SWITCH: main_menu → workout
    ↓
Workout greeting plays
    ↓
Workout session begins...
```

## Key Functions

### State Management (`agent_state.py`)

```python
from agent_state import AgentState

# Create new state (defaults to onboarding mode)
state = AgentState()

# Load existing user state
state = AgentState(user_id="user_123")

# Get values
mode = state.get_mode()
name = state.get("user.name")

# Set values
state.set("user.name", "John")
state.update_user(name="John", email="john@example.com")

# Switch modes
state.switch_mode("main_menu")

# Save/load state
state.save_state()
state.load_state("user_123")
```

### Mode Handlers (`mode_handlers.py`)

```python
from mode_handlers import (
    handle_mode_switch,
    handle_main_menu,
    handle_workout,
    complete_onboarding,
    transition_to_workout,
    return_to_main_menu
)

# Route to appropriate handler based on current mode
await handle_mode_switch(state, session)

# Specific handlers
await handle_main_menu(state, session)
await handle_workout(state, session)

# Transitions
await complete_onboarding(
    state=state,
    name="John",
    email="john@example.com",
    username="john",
    user_id="user_123",
    session=session
)

await transition_to_workout(state, session)
await return_to_main_menu(state, session)
```

### Onboarding Integration

The `OnboardingAgent` class now accepts state and session parameters:

```python
from agent_state import AgentState

# Initialize state
state = AgentState()

# Create agent with state
agent = OnboardingAgent(state=state, session_ref=session)
```

## Smooth Transitions

### How It Works

1. **Onboarding Completion**:
   ```python
   # In confirm_email_correct():
   # 1. Create user account
   # 2. Update state with user info
   # 3. Schedule async transition (2 second delay)
   # 4. Play completion message
   # 5. Transition executes → calls complete_onboarding()
   # 6. Main menu handler plays first-time greeting
   ```

2. **No Silence/Gaps**:
   - Final onboarding message plays immediately
   - 2-second delay allows message to complete
   - Main menu greeting starts seamlessly
   - User experiences continuous conversation

### Timing Configuration

Adjust transition delay in `onboarding_agent.py`:

```python
async def _transition_to_main_menu(self, user_id: str, username: str):
    # Adjust this delay based on typical message length
    await asyncio.sleep(2.0)  # Default: 2 seconds

    await complete_onboarding(...)
```

## State Persistence

### File Storage

State is automatically saved to JSON files:
- Format: `.agent_state_{user_id}.json`
- Location: Project root directory
- Content: Full state dictionary

### Loading Saved State

```python
# At startup, check if user has saved state
user_id = get_user_id_from_session()  # Your session logic

if user_id:
    state = AgentState(user_id=user_id)
    # State automatically loaded
    # User skips onboarding, goes to main menu
else:
    state = AgentState()
    # New user, starts at onboarding
```

## Voice Integration

### First-Time Main Menu Greeting

When a user completes onboarding:

```
Nova: "Welcome to Nowva AI, John! [breathe] I'll be your workout partner.
You can start a workout, view your progress, or change your profile settings.
What would you like to do first?"
```

### Returning User Greeting

When a returning user starts:

```
Nova: "Welcome back, John! [breathe] Ready to start your next workout or view progress?"
```

### Workout Start Greeting

When transitioning to workout mode:

```
Nova: "Alright John, let's do this! [breathe] I'm tracking your form and counting reps.
When you're ready, step up to the rack."
```

## Testing

### Test Mode Transitions

Run the built-in test:

```bash
python src/mode_handlers.py
```

This will simulate:
1. Onboarding completion
2. Transition to main menu (first-time greeting)
3. Transition to workout
4. Return to main menu (returning user greeting)

### Test Onboarding Flow

```bash
python src/onboarding_agent.py
```

This will start the full onboarding agent with state management.

## Integration with Main App

### In `main.py`

```python
from agent_state import AgentState
from mode_handlers import handle_mode_switch

async def run_app():
    # Check for existing session
    user_id = session_manager.get_user_id()

    if user_id:
        # Returning user
        state = AgentState(user_id=user_id)
        state.switch_mode("main_menu")
    else:
        # New user
        state = AgentState()
        state.switch_mode("onboarding")

    # Start appropriate mode
    await handle_mode_switch(state, session)
```

## Best Practices

1. **Always use state methods**: Don't directly modify `state.state` dictionary
2. **Save state after important changes**: Call `state.save_state()` after mode switches
3. **Handle errors gracefully**: Database failures shouldn't prevent mode transitions
4. **Adjust timing**: Test transition delays with actual voice output
5. **Log transitions**: Use print statements for debugging mode switches

## Future Enhancements

- [ ] Database-backed state storage (instead of JSON files)
- [ ] State synchronization across multiple devices
- [ ] Advanced conversation history tracking
- [ ] Workout session resumption
- [ ] Progress tracking integration
- [ ] Multi-user support (family accounts)

## Troubleshooting

### Issue: Silent gaps between modes
**Solution**: Reduce delay in `_transition_to_main_menu()`

### Issue: State not persisting
**Solution**: Check file permissions and ensure `save_state()` is called

### Issue: First-time greeting plays every time
**Solution**: Verify `mark_main_menu_visited()` is called and state is saved

### Issue: Mode switch not happening
**Solution**: Check async task creation and ensure session reference is valid

## Support

For questions or issues with state management, see:
- [onboarding_agent.py](src/onboarding_agent.py) - Implementation details
- [agent_state.py](src/agent_state.py) - State class documentation
- [mode_handlers.py](src/mode_handlers.py) - Handler examples
