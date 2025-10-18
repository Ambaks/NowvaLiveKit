# Console Voice Onboarding Setup

The Nowva application now supports **console-based voice onboarding** - no browser required! You speak directly in your terminal using your computer's microphone.

## Quick Start

```bash
# 1. Install dependencies
pip install pyaudio deepgram-sdk openai

# 2. Run main app
python src/main.py
```

The voice onboarding will start automatically if no session exists.

## How It Works

### Console Voice Flow

```
┌──────────────────┐
│  User speaks     │
│  into mic        │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Deepgram STT    │
│  (transcribe)    │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  OpenAI LLM      │
│  (process)       │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Text response   │
│  in terminal     │
└──────────────────┘
```

**No browser needed!** Everything happens in your terminal.

## Example Conversation

```
==================================================
SIMPLE VOICE ONBOARDING
==================================================

You'll speak with Nova using your microphone.
After Nova speaks, you'll have 5 seconds to respond.
Press Ctrl+C anytime to cancel.

🤖 Nova: Welcome to Nowva! We track your form and provide coaching. What's your name?

🎤 Listening... (speak now)
   Done recording.
💬 You said: John Doe

🤖 Nova: Great! And what's your email address, John?

🎤 Listening... (speak now)
   Done recording.
💬 You said: john at example dot com

🤖 Nova: Just to confirm - your name is John Doe and email is john@example.com, correct?

🎤 Listening... (speak now)
   Done recording.
💬 You said: yes

🤖 Nova: Awesome! You're all set, John!

==================================================
✓ Information collected:
  Name: John Doe
  Email: john@example.com
==================================================

✓ Onboarding complete! Welcome, John Doe!
```

## Installation

### 1. Install PyAudio

**macOS:**
```bash
brew install portaudio
pip install pyaudio
```

**Linux:**
```bash
sudo apt-get install portaudio19-dev
pip install pyaudio
```

**Windows:**
```bash
pip install pyaudio
```

### 2. Install Speech SDKs

```bash
pip install deepgram-sdk openai
```

### 3. Verify Microphone

Test your microphone works:

```bash
python -c "import pyaudio; p = pyaudio.PyAudio(); print(f'Devices: {p.get_device_count()}'); p.terminate()"
```

Should show available audio devices.

## Configuration

Make sure these are in your `.env` file:

```bash
# Deepgram for speech-to-text
DEEPGRAM_API_KEY=your_deepgram_key

# OpenAI for conversation
OPENAI_API_KEY=your_openai_key
LLM_CHOICE=gpt-4o-mini
```

## Usage Tips

### Speaking Email Addresses

Say emails naturally:
- **Say:** "john at example dot com"
- **Gets:** john@example.com

- **Say:** "jane underscore smith at gmail dot com"
- **Gets:** jane_smith@gmail.com

### If It Doesn't Understand

- Speak clearly and at normal volume
- Avoid background noise
- If it fails, you can fall back to text input

### Recording Duration

- You have **5 seconds** to speak after seeing "🎤 Listening..."
- Speak your full response within that time
- The system automatically processes after 5 seconds

## Troubleshooting

### "No module named 'pyaudio'"

**Solution:**
```bash
# macOS
brew install portaudio
pip install pyaudio

# If still fails, try:
pip install --global-option='build_ext' --global-option='-I/opt/homebrew/include' --global-option='-L/opt/homebrew/lib' pyaudio
```

### "Input overflowed"

This happens if your system can't keep up with audio recording.

**Solution:**
Edit `simple_voice_onboarding.py` and reduce `RECORD_SECONDS`:
```python
self.RECORD_SECONDS = 3  # Reduce from 5 to 3
```

### Microphone Not Working

**Check:**
1. System microphone permissions
2. Correct input device selected
3. Microphone not muted

**Test:**
```bash
python -c "import pyaudio; p = pyaudio.PyAudio(); [print(f'{i}: {p.get_device_info_by_index(i)[\"name\"]}') for i in range(p.get_device_count())]; p.terminate()"
```

### Transcription Errors

If Deepgram isn't understanding you:

1. **Speak louder and clearer**
2. **Reduce background noise**
3. **Check API key is valid:**
   ```bash
   echo $DEEPGRAM_API_KEY
   ```

### Fall Back to Text

At any time, press **Ctrl+C** to cancel voice onboarding and use text-based input instead.

## Comparison: Console vs Browser

| Feature | Console Voice | Browser (LiveKit) |
|---------|---------------|-------------------|
| Setup | Simple (pip install) | Complex (LiveKit account) |
| UI | Terminal only | Visual web interface |
| Dependencies | pyaudio, deepgram, openai | Full LiveKit stack |
| Speed | Fast | Slower (network latency) |
| Reliability | Depends on mic | More robust |

**Recommendation:** Use console voice for simpler setup. Use browser version for production/demo.

## Advanced: Customize Recording Time

Edit `src/simple_voice_onboarding.py`:

```python
class SimpleVoiceOnboarding:
    def __init__(self):
        # ... other settings ...
        self.RECORD_SECONDS = 7  # Change from 5 to 7 seconds
```

## Advanced: Better Email Extraction

The system does basic email extraction. For better accuracy, you can:

1. **Spell out your email:** "j-o-h-n at example dot com"
2. **Say it slowly:** Pause between words
3. **Fall back to text:** Press Ctrl+C and type it

## Testing

Test console voice onboarding standalone:

```bash
cd src
python simple_voice_onboarding.py
```

This runs just the voice onboarding without the full app.

## Files

- [src/simple_voice_onboarding.py](src/simple_voice_onboarding.py) - Console voice implementation
- [src/main.py](src/main.py) - Uses console voice by default
- [src/requirements.txt](src/requirements.txt) - Includes pyaudio, deepgram, openai

## Next Steps

After onboarding completes:
1. User is saved to database
2. Session is stored locally
3. You proceed to main menu
4. Choose "Start workout" to begin!

---

**Questions?** Check [VOICE_ONBOARDING.md](VOICE_ONBOARDING.md) for the browser-based version or [MAIN_APP_README.md](MAIN_APP_README.md) for overall architecture.
