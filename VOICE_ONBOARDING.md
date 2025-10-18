# Voice Onboarding

The Nowva application now supports full voice-based onboarding using LiveKit and AI.

## Overview

When a user runs the application for the first time (no session detected), they can complete the onboarding process entirely through voice conversation with the Nova AI agent.

## How It Works

### Architecture

```
┌─────────────┐
│  main.py    │ ──┐
└─────────────┘   │
                  │ starts
┌─────────────┐   │
│ voice_agent_│◄──┘
│  runner.py  │
└──────┬──────┘
       │ spawns subprocess
       ▼
┌─────────────────┐
│ onboarding_     │
│  agent.py       │
│                 │
│ • LiveKit       │
│ • Deepgram STT  │
│ • OpenAI LLM    │
│ • Inworld TTS   │
└─────────────────┘
       │
       │ collects data
       ▼
┌─────────────────┐
│ Username + Email│
└─────────────────┘
```

### Components

1. **[onboarding_agent.py](src/onboarding_agent.py)**
   - Specialized LiveKit agent for onboarding
   - Uses function calling to extract user data
   - Conversational flow with confirmations

2. **[voice_agent_runner.py](src/voice_agent_runner.py)**
   - Helper to run voice agent as subprocess
   - Monitors output for completion
   - Extracts username/email from agent output

3. **[main.py](src/main.py)** - Updated to use voice onboarding
   - Calls `run_onboarding_with_voice()`
   - Falls back to text-based onboarding on failure/cancellation

## Conversation Flow

The onboarding agent follows this conversational flow:

1. **Welcome**
   - "Hey! Welcome to Nowva, your AI-powered smart squat rack..."
   - Brief explanation of features

2. **Collect Name**
   - "What's your name?"
   - User speaks their name

3. **Collect Email**
   - "And what's your email address?"
   - User speaks email (agent handles "at" and "dot" conversion)

4. **Confirm Information**
   - Agent repeats back: "Just to confirm - your name is [NAME] and email is [EMAIL]?"
   - User confirms with "yes", "correct", etc.

5. **Complete**
   - Agent calls `save_user_info()` function
   - "Awesome! You're all set. Let's get started!"

## Usage

### Running Voice Onboarding

```bash
python src/main.py
```

If no session exists, the app automatically starts voice onboarding:

```
==================================================
VOICE ONBOARDING
==================================================

Starting voice-based onboarding...
The voice agent will:
1. Welcome you to Nowva
2. Explain the product
3. Ask for your name
4. Ask for your email
5. Confirm your information

You can also use text onboarding by pressing Ctrl+C

Voice agent process started...
Waiting for agent to initialize...
```

### Browser Opens

The LiveKit agent opens in your browser. You'll need to:

1. **Allow microphone access** when prompted
2. **Speak with the agent** - have a conversation
3. **Provide your information** when asked
4. **Confirm** when agent asks if information is correct

### Completion

When complete, you'll see:

```
==================================================
ONBOARDING COMPLETE
Name: John Doe
Email: john@example.com
==================================================

✓ Onboarding data collected successfully!
Created new user: John Doe (ID: 1)
Session saved for user: John Doe

✓ Onboarding complete! Welcome, John Doe!
```

### Fallback to Text

If voice onboarding fails or you press Ctrl+C, you can use text-based onboarding:

```
Voice onboarding cancelled.
Would you like to use text-based onboarding instead? (y/n)
y

==================================================
TEXT ONBOARDING
==================================================

Enter your name: John Doe
Enter your email: john@example.com

✓ Onboarding complete! Welcome, John Doe!
```

## Function Calling

The onboarding agent uses OpenAI's function calling feature to extract structured data from the conversation.

### save_user_info Function

```python
{
    "name": "save_user_info",
    "description": "Save the user's name and email to complete onboarding",
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "The user's name"
            },
            "email": {
                "type": "string",
                "description": "The user's email address"
            }
        },
        "required": ["name", "email"]
    }
}
```

The LLM automatically calls this function when:
- User has provided both name and email
- User has confirmed the information is correct

## Configuration

### Environment Variables

Required in `.env`:

```bash
# LiveKit
LIVEKIT_URL=wss://your-livekit-server.livekit.cloud
LIVEKIT_API_KEY=your_api_key
LIVEKIT_API_SECRET=your_api_secret

# OpenAI (for LLM)
OPENAI_API_KEY=your_openai_key
LLM_CHOICE=gpt-4o-mini

# Deepgram (for STT)
DEEPGRAM_API_KEY=your_deepgram_key

# Inworld (for TTS)
INWORLD_API_KEY=your_inworld_key

# Database
DATABASE_URL=your_database_url
```

## Testing

### Test Voice Agent Standalone

```bash
cd src
python onboarding_agent.py dev
```

This starts the onboarding agent in development mode. Open the browser link and test the conversation.

### Test Voice Agent Runner

```bash
cd src
python voice_agent_runner.py
```

This tests the runner that spawns and monitors the agent process.

## Troubleshooting

### Agent doesn't start

**Check:**
- LiveKit credentials in `.env`
- Internet connection
- Port 443 not blocked

**Solution:**
```bash
# Test LiveKit connection
curl -I https://your-livekit-server.livekit.cloud
```

### No audio/microphone not working

**Check:**
- Browser microphone permissions
- System audio settings
- Correct input device selected

**Solution:**
- Refresh browser page
- Check browser console for errors
- Try different browser (Chrome recommended)

### Agent doesn't extract data

**Check:**
- OpenAI API key valid
- Function calling enabled (GPT-4 or GPT-3.5-turbo)
- User confirmed information with "yes" or similar

**Solution:**
- Check agent logs for function calls
- Try saying "yes" or "correct" more clearly
- Fall back to text onboarding

### Timeout waiting for completion

**Default timeout:** 300 seconds (5 minutes)

**Solution:**
- Complete onboarding faster
- Increase timeout in `voice_agent_runner.py`:
  ```python
  result = runner.wait_for_completion(timeout=600)  # 10 minutes
  ```

## Advanced Usage

### Custom Onboarding Questions

Edit `onboarding_agent.py` instructions to add more questions:

```python
instructions="""
...
After collecting name and email, also ask:
- What are your fitness goals?
- Do you have any injuries?
...
"""
```

Then update the `save_user_info` function to accept additional parameters.

### Different Voice

Change TTS voice in `onboarding_agent.py`:

```python
tts=inworld.TTS(
    voice="YourChosenVoice",  # Choose from Inworld voice catalog
    model="inworld-tts-1-max",
)
```

### Multiple Languages

Update STT language in `onboarding_agent.py`:

```python
stt=deepgram.STT(
    model="nova-3",
    language="es",  # Spanish, or other supported language
)
```

## Future Enhancements

- [ ] Add profile picture capture during onboarding
- [ ] Ask for fitness goals and injuries
- [ ] Personalized welcome message based on user info
- [ ] Store conversation transcript for review
- [ ] Multi-language support
- [ ] Voice activity animations in browser
- [ ] Real-time transcription display

## Related Files

- [src/onboarding_agent.py](src/onboarding_agent.py) - Onboarding agent implementation
- [src/voice_agent_runner.py](src/voice_agent_runner.py) - Agent runner/monitor
- [src/main.py](src/main.py) - Main app with onboarding integration
- [src/Agent.py](src/Agent.py) - Main voice agent (for workouts)
- [src/session_manager.py](src/session_manager.py) - Session storage
