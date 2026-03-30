# Project Constitution - Onjaro Web Application

## Product Goal
Magyar nyelvű kerékpársport-portál 45-60 éves férfiak számára, akik az országúti kerékpározás, mountain bike (MTB) és ciklokrossz iránt érdeklődnek. A weboldal célja: hasznos tartalmak, tippek, edzéstervek, felszerelés-tanácsok és közösségi élmény nyújtása ennek a korosztálynak. A portál figyelembe veszi a 45-60 éves korosztály fizikai sajátosságait (regeneráció, ízületek védelme, teljesítményoptimalizálás életkor felett), életstílusát (munkával, családdal egyensúlyozás) és vásárlóerejét (prémium felszerelések iránti nyitottság).

## Target Audience
**Elsődleges célcsoport:** 45-60 éves magyar férfiak, akik aktívan kerékpároznak vagy érdeklődnek a sport iránt.

**Jellemzők:**
- Tapasztalt vagy újrakezdő kerékpárosok
- Érdeklődési körük: országúti (road bike), mountain bike (MTB), ciklokrossz
- Rendszeres mozgást keresnek, egészségtudatosak
- Prémium felszerelések iránt nyitottak, de tudatos vásárlók
- Magyar anyanyelvűek, magyar tartalmakat preferálnak
- Asztali és mobil böngészőt egyaránt használnak

## UX Principles
- Simple, clean, intuitive interface
- Mobile-first responsive design
- Fast loading times
- Accessible (WCAG 2.1 AA)
- Hungarian language primary, English secondary
- Consistent visual language

## Tech Stack
- Framework: (to be determined based on initial setup)
- Language: TypeScript / JavaScript
- Styling: CSS / Tailwind CSS
- Build: npm

## Visual & Content Guidelines
- Modern, minimal design
- Clear typography hierarchy
- Consistent color palette
- Meaningful icons and visual feedback
- Concise, user-friendly copy

## Blocklist - NEVER Touch These
- Authentication / authorization / login
- Payment / billing / subscription
- Database migrations (destructive)
- Global refactoring
- Dependency upgrades
- Secrets / keys / env structure
- Destructive file deletion
- Multi-area refactors
- Anything requiring human login or CAPTCHA

## Critical System Files - NEVER Modify
- `orchestrator/` - Evolution system orchestrator
- `db/` - Database layer
- `agents/` - AI agent system
- `hooks/` - Hook system
- `dashboard/` - Activity dashboard
- `data/` - Runtime data
- `artifacts/` - Stored artifacts
- `CLAUDE.md` - This file
- `requirements.txt` - Python dependencies
- `.claude/` - Claude configuration

## Build & Test Commands
```bash
npm run build    # Build the application
npm run lint     # Run linter
npx tsc --noEmit # Type checking
npm test         # Run test suite
```

## What Makes a Good Evolutionary Step
- Focused, single-purpose change
- Adds value aligned with the product goal
- Can be tested automatically
- Doesn't break existing functionality
- Touches one screen/component area
- Is additive rather than destructive
- Has low regression risk

## What to Avoid in Evolutionary Steps
- Large refactors spanning multiple files
- Changes to core architecture
- Features that depend on unbuilt features
- Removal of existing functionality
- Performance optimizations without measurements
- Style-only changes with no user value

## Commit Message Format
```
[auto/{run_id}] Feature Title

Summary: Brief description of what was built
Screen: Affected screen/route
Tests: pass/fail status
Run: run_id
```

## Logging Expectations
- Every run must be fully traceable
- Decisions must include rationale
- Failures must include full context
- All artifacts must be preserved
