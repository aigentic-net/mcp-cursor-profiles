# MCP Cursor Profiles

An MCP server that integrates with Cursor IDE's native profile system and adds automatic GitHub identity switching.

## The Problem

Cursor stores all configuration in a single set of directories. If you juggle multiple projects, clients, or GitHub identities, there's no built-in way to tie a Cursor profile to a specific GitHub account. You end up manually running `gh auth switch` every time you change context, or worse — pushing to the wrong repo with the wrong account.

![Gap Analysis](docs/gap-analysis.svg)

## How It Works

This MCP server builds **on top of** Cursor's real profile system — not around it:

- **Cursor profiles** handle settings, extensions, keybindings, snippets, and tasks (managed natively by Cursor)
- **Identity bindings** link each profile to a GitHub account, so switching profiles automatically switches `gh` credentials
- **No symlinks, no hacks** — uses `cursor --profile <name>` and Cursor's `storage.json` directly

![Architecture Overview](docs/architecture-overview.svg)

## Features

- List Cursor's native profiles with linked GitHub identities
- Switch profiles and auto-switch GitHub accounts in one step
- Create new profiles with optional GitHub identity binding
- Link / unlink GitHub identities to existing profiles
- Check and fix git remote authentication per-repo
- Cross-platform support (macOS, Windows, Linux)

## Prerequisites

- Python 3.10 or higher
- [uv](https://github.com/astral-sh/uv) package manager
- Cursor IDE installed
- [gh](https://cli.github.com/) CLI (required for git identity features)

## Installation & Configuration

Clone the repository and install as a tool:

```bash
git clone https://github.com/aigentic-net/mcp-cursor-profiles.git
cd mcp-cursor-profiles
uv tool install -e .
```

Then add to your MCP client configuration (Cursor, Claude Desktop, etc.):

```json
{
  "mcpServers": {
    "cursor-profiles": {
      "command": "cursor-profiles-mcp"
    }
  }
}
```

`uv tool install` places the `cursor-profiles-mcp` binary on your PATH (at `~/.local/bin/` by default).

> **Note:** If `~/.local/bin` is not on your PATH, use the full path instead:
>
> ```json
> { "command": "/Users/you/.local/bin/cursor-profiles-mcp" }
> ```
>
> You can find the exact path with `uv tool dir --bin`.

> **Updating:** After pulling new changes, re-run `uv tool install -e .` to pick them up.

## Available Tools

### Profile Management

#### `show_profiles`

List all Cursor profiles with their linked GitHub identities. The active profile is marked with an asterisk (`*`).

#### `switch_profile`

Switch to a Cursor profile and open Cursor. If the profile has a linked GitHub identity, the `gh` account is switched automatically.

![Profile Switch Workflow](docs/profile-switch-workflow.svg)

| Parameter      | Type   | Description                       |
| -------------- | ------ | --------------------------------- |
| `profile_name` | string | Name of the profile to switch to  |

#### `init_profile`

Create a new Cursor profile using Cursor's native profile system. Optionally link a GitHub identity at creation time.

![Profile Init Workflow](docs/profile-init-workflow.svg)

| Parameter         | Type   | Description                                  |
| ----------------- | ------ | -------------------------------------------- |
| `profile_name`    | string | Name for the new profile                     |
| `github_username` | string | GitHub username to link (optional)           |

#### `open_cursor`

Open the Cursor application with the current profile.

### Identity Management

#### `link_identity`

Link a GitHub account to an existing Cursor profile. When you switch to this profile, your `gh` account switches automatically.

| Parameter         | Type   | Description                          |
| ----------------- | ------ | ------------------------------------ |
| `profile_name`    | string | Name of the Cursor profile           |
| `github_username` | string | GitHub username to link              |

#### `unlink_identity`

Remove the GitHub identity link from a Cursor profile.

| Parameter      | Type   | Description                              |
| -------------- | ------ | ---------------------------------------- |
| `profile_name` | string | Name of the Cursor profile to unlink     |

### Git Authentication

These tools manage GitHub authentication across multiple accounts via the `gh` CLI.

![Git Auth Workflow](docs/git-auth-workflow.svg)

#### `list_git_accounts`

List all GitHub accounts authenticated via the `gh` CLI. Shows which account is currently active.

#### `check_git_auth`

Check whether the active `gh` account matches a repository's GitHub remote owner. Reports mismatches and suggests fixes.

| Parameter   | Type   | Description                              |
| ----------- | ------ | ---------------------------------------- |
| `repo_path` | string | Absolute path to the git repository      |

#### `fix_git_remote`

Embed the GitHub username in a repo's `origin` URL so the `gh` credential helper automatically resolves the correct account — no manual `gh auth switch` needed.

| Parameter   | Type   | Description                                           |
| ----------- | ------ | ----------------------------------------------------- |
| `repo_path` | string | Absolute path to the git repository                   |
| `username`  | string | GitHub username to embed (defaults to the repo owner) |

#### `switch_git_account`

Switch the active GitHub account in the `gh` CLI.

| Parameter | Type   | Description                     |
| --------- | ------ | ------------------------------- |
| `account` | string | GitHub username to switch to    |

## Cursor Profiles vs Identity Bindings

| Feature | Cursor Profiles (native) | Identity Bindings (this tool) |
| ------- | ------------------------ | ----------------------------- |
| Settings isolation | Yes | — |
| Extension isolation | Yes | — |
| Keybindings per profile | Yes | — |
| Snippets per profile | Yes | — |
| Git credential switching | No | Yes |
| Auto `gh auth switch` | No | Yes |
| Per-repo auth verification | No | Yes |
| Visible in Cursor Settings UI | Yes | — |

Identity bindings are stored in `~/.cursor/identities.json` — a simple JSON file mapping profile names to GitHub usernames.

## Platform Support

| Platform  | Cursor Config Path                     |
| --------- | -------------------------------------- |
| macOS     | `~/Library/Application Support/Cursor` |
| Windows   | `%APPDATA%/Cursor`                     |
| Linux     | `~/.config/Cursor`                     |

## Troubleshooting

### "Profile not found" error

Ensure the profile exists using `show_profiles`. Profile names are case-sensitive.

### Git push fails with "permission denied"

Run `check_git_auth` with the repo path. It will tell you if there's a mismatch between your active `gh` account and the repo owner, and suggest the fix.

### MCP connection issues

- Ensure `uv` is installed and on your PATH
- Re-run `uv tool install -e .` from the project directory
- Verify the binary runs: `cursor-profiles-mcp` (it should block waiting for input — that's normal, Ctrl+C to exit)
- If the command is not found, check that `~/.local/bin` is on your PATH or use the full path from `uv tool dir --bin`

### Python version issues

This package requires Python 3.10+. Check your version:

```bash
python --version
```

## Development

For working on the server itself:

```bash
cd mcp-cursor-profiles
uv sync

# Run directly
uv run cursor-profiles-mcp

# Debug mode
MCP_DEBUG=1 uv run cursor-profiles-mcp
```

For development, you can point the MCP config at the venv instead:

```json
{
  "mcpServers": {
    "cursor-profiles": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/mcp-cursor-profiles", "cursor-profiles-mcp"]
    }
  }
}
```

## License

MIT
