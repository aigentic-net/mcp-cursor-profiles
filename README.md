# MCP Cursor Profiles Server

An MCP (Model Context Protocol) server for managing multiple Cursor IDE profiles across different platforms.

## Features

- Switch between Cursor profiles seamlessly
- Create new profiles from current configuration
- Rename existing profiles
- List all available profiles with active profile indication
- Git authentication management across multiple GitHub accounts
- Cross-platform support (macOS, Windows, Linux)
- Safety checks to prevent data corruption while Cursor is running

## Installation

### Prerequisites

- Python 3.10 or higher
- Cursor IDE installed
- An MCP-compatible client (Claude Desktop, Cursor, etc.)
- [uv](https://github.com/astral-sh/uv) package manager (recommended)
- [gh](https://cli.github.com/) CLI (required for git auth tools)

### Using uv (Recommended)

```bash
cd mcp-cursor-profiles
uv sync
```

### Using pip

```bash
cd mcp-cursor-profiles
pip install -r requirements.txt
```

## Configuration

### Option 1: Local Virtual Environment (Recommended for Development)

After running `uv sync`, use the Python path from your virtual environment:

```json
{
  "mcpServers": {
    "cursor-profiles": {
      "command": "/full/path/to/mcp-cursor-profiles/.venv/bin/python",
      "args": ["-m", "cursor_profiles_mcp"]
    }
  }
}
```

### Option 2: Install with uvx (Recommended for Distribution)

```bash
uv tool install -e .
```

Then configure:

```json
{
  "mcpServers": {
    "cursor-profiles": {
      "command": "uvx",
      "args": ["cursor-profiles-mcp"]
    }
  }
}
```

### Option 3: Direct uv Run

```json
{
  "mcpServers": {
    "cursor-profiles": {
      "command": "uv",
      "args": ["run", "--directory", "/full/path/to/mcp-cursor-profiles", "cursor_profiles_mcp.py"]
    }
  }
}
```

### Option 4: Entry Point Directly

After `uv sync`, use the installed console script:

```json
{
  "mcpServers": {
    "cursor-profiles": {
      "command": "/full/path/to/mcp-cursor-profiles/.venv/bin/cursor-profiles-mcp"
    }
  }
}
```

## Finding the Correct Paths

```bash
# Get your project path
pwd

# Get Python path in your virtual environment
source .venv/bin/activate
which python
```

## Available Tools

### `list_profiles`

List all available Cursor profiles. The active profile is marked with an asterisk (`*`).

### `switch_profile`

Switch to a specific profile and open Cursor.

| Parameter      | Type   | Description                       |
| -------------- | ------ | --------------------------------- |
| `profile_name` | string | Name of the profile to switch to  |

### `init_profile`

Create a new profile from your current Cursor configuration.

| Parameter      | Type   | Description              |
| -------------- | ------ | ------------------------ |
| `profile_name` | string | Name for the new profile |

### `rename_profile`

Rename an existing profile.

| Parameter  | Type   | Description          |
| ---------- | ------ | -------------------- |
| `old_name` | string | Current profile name |
| `new_name` | string | New profile name     |

### `open_cursor`

Open the Cursor application with the current profile.

### `list_git_accounts`

List all GitHub accounts authenticated via the `gh` CLI. Shows which account is currently active.

### `check_git_auth`

Check whether the active `gh` account matches a repository's GitHub remote owner. Reports mismatches and suggests fixes.

| Parameter   | Type   | Description                              |
| ----------- | ------ | ---------------------------------------- |
| `repo_path` | string | Absolute path to the git repository      |

### `fix_git_remote`

Embed the GitHub username in a repo's `origin` URL so the `gh` credential helper automatically resolves the correct account — no manual `gh auth switch` needed.

| Parameter   | Type   | Description                                           |
| ----------- | ------ | ----------------------------------------------------- |
| `repo_path` | string | Absolute path to the git repository                   |
| `username`  | string | GitHub username to embed (defaults to the repo owner) |

### `switch_git_account`

Switch the active GitHub account in the `gh` CLI.

| Parameter | Type   | Description                     |
| --------- | ------ | ------------------------------- |
| `account` | string | GitHub username to switch to    |

## Platform Support

| Platform  | Cursor Config Path                     |
| --------- | -------------------------------------- |
| macOS     | `~/Library/Application Support/Cursor` |
| Windows   | `%APPDATA%/Cursor`                     |
| Linux     | `~/.config/Cursor`                     |

## How It Works

1. Creates symlinks from the main Cursor directories to profile-specific directories
2. Maintains two sets of profiles (Application Support and dotfile versions)
3. Ensures Cursor is closed before profile operations to prevent data corruption
4. Automatically detects the correct paths for your operating system

## Safety Features

- Checks if Cursor is running before profile operations
- Validates profile names (alphanumeric, hyphens, underscores, dots)
- Validates profile existence before switching
- Prevents overwriting existing profiles
- Maintains symlink integrity

## Troubleshooting

### "Cursor is currently running" error

Quit Cursor completely before using profile management tools.

### "Profile not found" error

Ensure the profile exists using `list_profiles`.

### Permission errors

Make sure the script has read/write access to Cursor directories.

### MCP connection issues

- Verify the full path to the Python script in your configuration
- Ensure Python is in your system PATH
- Check that all dependencies are installed
- For uvx issues, ensure the package is properly installed with `uv tool install -e .`

### Python version issues

This package requires Python 3.10+. Check your version:

```bash
python --version
```

## Development

```bash
# Run directly
python cursor_profiles_mcp.py

# Debug mode
MCP_DEBUG=1 python cursor_profiles_mcp.py
```

## License

MIT
