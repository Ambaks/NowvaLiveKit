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

## Behavior
- When you are thinking and planning, do not hesitate to come back to me often with lots of questions if you are not sure about a situation.

- When writing code, make sure you use explicit variable naming to make the code easy to read for a human. Use names that explain what is going on (Example: x_coordinate instead of x) Try not to use single letter variables unless it makes total sense.

1. Think Before Coding

Don't assume. Don't hide confusion. Surface tradeoffs.

Before implementing:

State your assumptions explicitly. If uncertain, ask.
If multiple interpretations exist, present them - don't pick silently.
If a simpler approach exists, say so. Push back when warranted.
If something is unclear, stop. Name what's confusing. Ask.

2. Simplicity First

Minimum code that solves the problem. Nothing speculative.

No features beyond what was asked.
No abstractions for single-use code.
No "flexibility" or "configurability" that wasn't requested.
No error handling for impossible scenarios.
If you write 200 lines and it could be 50, rewrite it.
Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

3. Surgical Changes

Touch only what you must. Clean up only your own mess.

When editing existing code:

Don't "improve" adjacent code, comments, or formatting.
Don't refactor things that aren't broken.
Match existing style, even if you'd do it differently.
If you notice unrelated dead code, mention it - don't delete it.
When your changes create orphans:

Remove imports/variables/functions that YOUR changes made unused.
Don't remove pre-existing dead code unless asked.
The test: Every changed line should trace directly to the user's request.

4. Goal-Driven Execution

Define success criteria. Loop until verified.

Transform tasks into verifiable goals:

"Add validation" → "Write tests for invalid inputs, then make them pass"
"Fix the bug" → "Write a test that reproduces it, then make it pass"
"Refactor X" → "Ensure tests pass before and after"
For multi-step tasks, state a brief plan:

1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

These guidelines are working if: fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.