## What

<!-- One or two sentences. What does this PR do? -->

## Why

<!-- Context, linked issue, or reasoning. If this fixes an issue, write "Closes #123" -->

## How to test

<!-- Steps for the reviewer to verify locally. Include any test data, env vars, or setup needed. -->

1.
2.
3.

## Risk surface

<!-- Check all that apply -->

- [ ] Voice pipeline (LiveKit, Deepgram, Cartesia, GPT, VAD)
- [ ] Agent state machines (TeachingAgent, WorkoutAgent, ProgramCreationAgent)
- [ ] Biomechanics pipeline (pose estimation, triangulation, joint angles)
- [ ] Squat fault classifier (CNN-GRU)
- [ ] Program generator (V5/V6, exercise library, volume logic)
- [ ] RAG / knowledge base
- [ ] Hardware / firmware
- [ ] Infra, CI, deploy
- [ ] Schema or data migration
- [ ] Touches paid API surface (cost implications)
- [ ] Frontend / website

## Checklist

- [ ] I tested this locally
- [ ] I added or updated tests where it made sense
- [ ] I updated docs / comments where it made sense
- [ ] No secrets, API keys, or `.env` values committed
- [ ] Linked the relevant issue or Linear ticket (if any)

## Screenshots / logs / demo

<!-- Optional. Drop in voice session transcripts, classifier confusion matrices, CAD renders, etc. -->
