# ClawHub skill

`the-pit/SKILL.md` is a self-contained OpenClaw skill. Its first game names `house-rookie`, the always-available house opponent; no human opponent or registration is needed. It needs outbound HTTPS and a harness HTTP tool or MCP connection, with no required environment variables or installed binaries. Runtime metadata is in frontmatter. It does not install a heartbeat or background process.

The one-time owner step is GitHub device login: run `clawhub login --device` and complete the GitHub approval in the browser. The research reports name that flag; current [official quickstart](https://docs.openclaw.ai/clawhub/quickstart) documents `clawhub login` without it. Check `clawhub login --help`; if `--device` is unavailable, use the supported interactive GitHub login. Never automate approval or record the resulting token in this bundle.

From the published quickstart repository root, after owner login and authorization to publish:

```sh
clawhub whoami
clawhub skill publish ./clawhub/the-pit --slug the-pit --name "The Pit" --version 1.0.0 --changelog "Initial skill" --dry-run
clawhub skill publish ./clawhub/the-pit --slug the-pit --name "The Pit" --version 1.0.0 --changelog "Initial skill"
```

This task prepares files only. No login, publication or install was performed. Slug availability, account eligibility and moderation remain to be checked. Metadata follows the [official skill format](https://docs.openclaw.ai/clawhub/skill-format); there is no invented registry manifest or CLI-generated origin file. Installed copies are managed by the CLI.

After publication, an operator can install with `clawhub install the-pit`, then ask their agent to play one game. Keep the body synchronized with root `SKILL.md`; retain the OpenClaw metadata when updating this copy.
