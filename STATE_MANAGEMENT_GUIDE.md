# Nova AI Agent State Management Guide

## Overview

The Nova AI agent now features a comprehensive state management system that supports smooth transitions between different interaction modes and persistent user sessions.

## Architecture

### Core Components

1. **[src/core/agent_state.py](src/core/agent_state.py)** - State management class
2. **[src/agents/voice_agent.py](src/agents/voice_agent.py)** - Mode-aware voice agent with GPT-4 Realtime
3. **[src/main.py](src/main.py)** - Main orchestrator that monitors state changes

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

### State Management (`src/core/agent_state.py`)

```python
from core.agent_state import AgentState

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

### Voice Agent Integration (`src/agents/voice_agent.py`)

The voice agent automatically handles mode transitions using function calling:

```python
# Voice agent functions
@function_tool()
async def transition_to_main_menu():
    """Called after onboarding completes"""
    self.state.switch_mode("main_menu")
    self.state.save_state()
    return "Transitioning to main menu"

@function_tool()
async def start_workout():
    """Called when user wants to start workout"""
    self.state.switch_mode("workout")
    self.state.set("workout.active", True)
    self.state.save_state()
    return "Starting workout mode"

@function_tool()
async def end_workout():
    """Called when user wants to end workout"""
    self.state.switch_mode("main_menu")
    self.state.set("workout.active", False)
    self.state.save_state()
    return "Ending workout, returning to main menu"
```

### Voice Agent Integration

The voice agent automatically loads state based on user_id:

```python
from core.agent_state import AgentState
from agents.voice_agent import NovaVoiceAgent

# For new user (onboarding)
state = AgentState()  # Defaults to onboarding mode
agent = NovaVoiceAgent(state=state)

# For existing user
state = AgentState(user_id="user_123")  # Loads saved state
agent = NovaVoiceAgent(state=state)
```

## Smooth Transitions

### How It Works

1. **Onboarding Completion**:
   - Voice agent collects name and email via function calling
   - `confirm_user_info()` function creates account in database
   - `transition_to_main_menu()` function switches state to main_menu
   - Agent naturally transitions conversation to main menu
   - No delays needed - agent handles flow naturally

2. **Continuous Conversation**:
   - GPT-4 Realtime handles seamless voice transitions
   - Agent changes instructions based on current mode
   - User experiences one continuous conversation
   - No process restarts or silent gaps

### State-Based Control

The main.py orchestrator monitors state file for changes:

```python
# In main.py monitoring loop
self.state.reload_state()
current_mode = self.state.get_mode()

if current_mode == "workout" and not pose_running:
    # Start pose estimation automatically
    self.start_pose_estimation()
    pose_running = True

elif current_mode != "workout" and pose_running:
    # Stop pose estimation automatically
    self.pose_process.terminate()
    pose_running = False
```

## State Persistence

### File Storage

State is automatically saved to JSON files:
- Format: `.agent_state_{user_id}.json`
- Location: `src/` directory
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

### Test Voice Agent

Run the voice agent standalone:

```bash
cd src/agents
python voice_agent.py console
```

This will:
1. Start voice agent in console mode
2. Default to onboarding if no user state found
3. Allow full conversation testing
4. Demonstrate mode transitions

### Test Complete Flow

```bash
cd src
python main.py
```

This tests:
1. Session management
2. State loading/creation
3. Voice agent integration
4. Mode-based process control

## Integration with Main App

### In `src/main.py`

```python
from core.agent_state import AgentState
from agents.console_launcher import run_console_voice_agent

async def run():
    # Check for existing session
    user_id = session_manager.get_user_id()

    if user_id:
        # Returning user - load state
        state = AgentState(user_id=user_id)

        # Safety: Reset to main_menu on startup
        state.switch_mode("main_menu")
        state.set("workout.active", False)
        state.save_state()

        # Start voice agent for returning user
        voice_agent_process = await run_console_voice_agent(user_id=user_id)
    else:
        # New user - run onboarding
        success, voice_agent_process = await self.run_onboarding()

    # Monitor state for changes
    while True:
        state.reload_state()
        current_mode = state.get_mode()

        # Control pose estimation based on mode
        if current_mode == "workout":
            # Start pose estimation
        elif current_mode != "workout":
            # Stop pose estimation
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
- [src/agents/voice_agent.py](src/agents/voice_agent.py) - Voice agent implementation
- [src/core/agent_state.py](src/core/agent_state.py) - State class documentation
- [src/main.py](src/main.py) - State monitoring and control
- [MAIN_APP_README.md](MAIN_APP_README.md) - Complete architecture guide
