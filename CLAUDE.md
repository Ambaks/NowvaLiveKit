## Product Vision & Guardrails

Nowva is an AI personal trainer that runs on edge hardware. Every technical decision should serve this end state.

### What we're building
- A **biomechanics diagnosis engine** that analyzes a user's squat form in real-time, adapts to their anatomy and range of motion, and gives specific actionable cues ("widen your stance 10 degrees")
- A **conversational voice agent** running on a small local model (Gemma 2B-4B class) on edge hardware (Jetson Nano / Orin Nano Super) — it relays diagnosis cues naturally, no cloud API calls needed
- A **multi-camera triangulation pipeline** for accurate pose estimation
- The diagnosis engine is the core IP. The conversational layer just needs to sound human and deliver the cues.

### Business model
- Hardware + subscription. Ship a ~$200 edge device, charge ~$200/month. User's hardware runs inference — near-zero marginal cost after delivery, ~95% margins.
- We are 10x cheaper than a human personal trainer ($1,500-2,500/month in major US cities).
- Competitive moat: full-stack (biomechanics engine + hardware + edge deployment). We are NOT an API wrapper or a fitness app.

### Guardrails — push back if any change would:
1. **Add cloud/API dependency for the conversational layer.** The voice agent must run locally on edge hardware. Any change that makes it depend on cloud inference for conversation goes against the core business model. Flag it immediately.
2. **Overcomplicate the diagnosis engine outputs.** The engine should produce simple, structured outputs that a small local model can relay. If outputs are getting complex enough to need a large model to interpret, simplify.
3. **Break edge compatibility.** Any model, dependency, or computation that can't eventually run on a Jetson-class device (~40 TOPS) needs to be flagged. Ask: "Can this run on the edge device?"
4. **Sacrifice diagnosis accuracy for speed prematurely.** The diagnosis engine is the core IP. Don't cut corners on accuracy to optimize for latency until the accuracy is proven correct first. Get it right, then make it fast.
5. **Add scope beyond squats right now.** We are building one exercise done perfectly before expanding. If a change adds complexity for future exercises at the cost of squat pipeline quality, push back.
6. **Hurt the demo/YC pitch.** We are preparing for a YC application. Every feature should contribute to a working demo: real user squats with AI, system diagnoses form, gives a cue, user improves. If a change doesn't serve that loop, question whether it's needed right now.

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)

