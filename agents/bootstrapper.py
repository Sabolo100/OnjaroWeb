"""Bootstrapper agent - creates the initial webapp in webapp/ from CLAUDE.md."""

from agents.base import BaseAgent
from orchestrator.config import WEBAPP_DIR


class Bootstrapper(BaseAgent):
    name = "bootstrapper"
    timeout = 900
    max_budget_usd = 3.00
    allowed_tools = ["Bash", "Read", "Write", "Edit", "Glob", "Grep"]
    json_schema = None

    system_prompt = f"""You are the Bootstrapper agent in an autonomous web app evolution system.
Your job is to create the INITIAL version of a web application from scratch.

The webapp lives in its OWN subdirectory: {WEBAPP_DIR}
ALL files must be created inside this directory. Do NOT touch anything outside it.

CRITICAL RULES:
- Work ONLY inside: {WEBAPP_DIR}
- Create a minimal but complete working webapp
- Use the tech stack from CLAUDE.md, or default to Next.js + TypeScript + Tailwind CSS
- The app must build successfully with: npm run build
- The app must pass lint: npm run lint
- Include package.json with scripts: build, lint, dev, test
- Keep it simple: homepage + max one extra screen
- Do NOT add authentication, payments, or anything on the blocklist
- ALWAYS create a .gitignore file with: node_modules/, .next/, out/, .env*, *.tsbuildinfo
- Use next.config.mjs (NOT next.config.ts) - Vercel does not support .ts config files
- After creating files, run: cd {WEBAPP_DIR} && npm install && npm run build to verify"""

    prompt_template = """Create the initial version of the web application in the webapp/ directory.

## Target directory: {webapp_dir}

## CLAUDE.md (Project Constitution):
{claude_md}

## Your task:
1. cd into {webapp_dir} (create it first if needed with mkdir -p)
2. Choose the tech stack (use what CLAUDE.md specifies, or default to Next.js + TypeScript + Tailwind CSS)
3. Create the complete initial project structure inside {webapp_dir}
4. Implement a minimal but working homepage that reflects the product goal
5. Add basic navigation if there are multiple sections
6. Run: cd {webapp_dir} && npm install && npm run build to verify it works

## Important:
- ALL files go inside {webapp_dir}/
- Keep the initial version MINIMAL - just the homepage/main screen
- Hungarian language content to match the target audience
- Style it according to the UX principles in CLAUDE.md
- Make sure package.json has: build, lint, dev, test scripts"""

    def _build_prompt(self, context: dict) -> str:
        context.setdefault("webapp_dir", WEBAPP_DIR)
        return super()._build_prompt(context)
