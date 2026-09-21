Context:
- Integration: Exa API
- Use case: Coding agent

Run `npx skills use "https://github.com/exa-labs/agent-skills" --skill "build-with-exa"` and follow the generated skill instructions now. Read its complete output, redirecting it to a temporary file first if necessary. Resolve relative paths from the supporting-files directory it provides.

The build-with-exa skill is the canonical source of truth for the Exa API. Consult it for API usage and follow its guidance rather than guessing or relying on memory. Use the context above about what I'm building to choose which Exa endpoints and options fit best.

Set up my `EXA_API_KEY` using the secret or environment-variable mechanism for my coding tool.

Start by reading and following the skill instructions, then help me implement this in my project.

npx skills add exa-labs/agent-skills --skill "build-with-exa"
