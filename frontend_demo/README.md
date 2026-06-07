# frontend_demo/

React 19 + TypeScript SPA for the Nowva website. Built with Vite, styled with Tailwind CSS.

## Quick Start

```bash
cd frontend_demo
npm install
npm run dev
```

## What It Does

Public-facing landing page where visitors can generate personalized workout programs via:
1. **Voice conversation** — connects to the LiveKit voice agent for a guided intake flow
2. **Structured form** — multi-step onboarding form as an alternative to voice

## Tech Stack

- React 19 + TypeScript 5.6
- Vite 7.2 (build tool)
- Tailwind CSS 3.4
- Framer Motion (animations)
- LiveKit Client SDK (WebRTC voice connection)

## Structure

- `src/components/sections/` — landing page sections (Hero, Features, ProgramGenerator, etc.)
- `src/components/generator/` — program generator funnel (email gate, mode selector, voice/form)
- `src/components/ui/` — reusable UI components
- `src/api/` — API client for backend communication
- `src/hooks/` — React hooks
- `src/types/` — TypeScript type definitions
