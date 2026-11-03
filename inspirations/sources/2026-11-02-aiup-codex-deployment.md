# Source #12 — AI Unified Process setup guidance for Codex

Status: immutable transcription of the user-provided screenshot, received 2026-11-02.
The exact screenshot is preserved beside this transcription as
[`2026-11-02-aiup-codex-guidance.png`](2026-11-02-aiup-codex-guidance.png).

## Screenshot text

> Codex works too, but the setup is different. Claude Code uses `/plugin` commands.
> Codex has no equivalent, so you install the skill files another way.
>
> 1. Install the Codex CLI from OpenAI's instructions. This is a terminal program,
>    so you'd run it from your project folder.
> 2. Get the AIUP skill files in one of two ways:
>    - Tessl (easier): install the Tessl CLI, then run `tessl init --agent codex`
>      followed by `tessl install ai-unified-process/aiup-core`.
>    - Manual: clone `github.com/AI-Unified-Process/marketplace` and copy the
>      skill folders into Codex's skills directory, which the docs list as
>      `~/.codex/skills/` or `.agents/skills/`.
> 3. Start Codex in your project folder. Codex may not have slash commands for
>    these skills, so ask by intent, for example: "Create the requirements
>    catalog from docs/vision.md."
>
> I haven't verified the Codex skill paths or the Tessl package name against the
> repo's install docs. The subagent that made the screenshot did not open the
> `docs/installation/` pages, so check `docs/installation/other-agents.md` in
> the marketplace repo before relying on those paths.

The screenshot was introduced by the user as the intended Codex guidance
("That was the codex guidance in a nutshell"). The quoted uncertainty is part
of the source and must remain visible in derived guidance until checked against
current primary documentation.

## Source identity and limits

- Artifact: user-provided screenshot, preserved byte-for-byte in this directory.
- The text above is a transcription, not an upstream AIUP specification.
- Screenshot paths and package names are claims made by the screenshot; they
  were explicitly unverified there.
- OpenAI's current Codex skill guide documents user skills in `$HOME/.agents/skills`,
  repository skills in `.agents/skills`, and Codex invocation through `/skills`
  or `$skill`: <https://developers.openai.com/codex/skills>.
- The AIUP marketplace currently documents installation through Tessl and
  identifies `codex` as a supported agent: <https://github.com/AI-Unified-Process/marketplace/blob/main/docs/installation/tessl.md>.
- The AIUP manual guide confirms that host-specific skill directories receive
  whole skill folders and that plugin MCP definitions need host-specific
  translation: <https://github.com/AI-Unified-Process/marketplace/blob/main/docs/installation/other-agents.md>.
