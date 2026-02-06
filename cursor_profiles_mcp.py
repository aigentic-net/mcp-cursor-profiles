#!/usr/bin/env python3
"""MCP Server for managing Cursor profiles across platforms."""

import asyncio
import json
import platform
import re
import shutil
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("cursor-profiles")


# ---------------------------------------------------------------------------
# Platform paths
# ---------------------------------------------------------------------------

def _get_platform_paths() -> dict[str, Path]:
    """Return platform-specific paths for Cursor directories."""
    system = platform.system().lower()
    home = Path.home()

    if system == "darwin":
        return {
            "cursor_dir": home / "Library" / "Application Support" / "Cursor",
            "cursor_profiles_dir": home / "Library" / "Application Support" / "CursorProfiles",
            "dot_cursor": home / ".cursor",
            "dot_cursor_profiles": home / ".cursor-profiles",
        }
    elif system == "windows":
        return {
            "cursor_dir": home / "AppData" / "Roaming" / "Cursor",
            "cursor_profiles_dir": home / "AppData" / "Roaming" / "CursorProfiles",
            "dot_cursor": home / ".cursor",
            "dot_cursor_profiles": home / ".cursor-profiles",
        }
    else:  # Linux and other Unix-like systems
        return {
            "cursor_dir": home / ".config" / "Cursor",
            "cursor_profiles_dir": home / ".config" / "CursorProfiles",
            "dot_cursor": home / ".cursor",
            "dot_cursor_profiles": home / ".cursor-profiles",
        }


PATHS = _get_platform_paths()

# Valid profile name: alphanumeric, hyphens, underscores, dots (no path separators)
_PROFILE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_profile_name(name: str) -> None:
    """Raise ValueError if *name* is not a safe profile name."""
    if not name or not _PROFILE_NAME_RE.match(name):
        raise ValueError(
            f"Invalid profile name '{name}'. "
            "Use only letters, digits, hyphens, underscores, and dots. "
            "Must start with a letter or digit."
        )


def _ensure_profile_roots() -> None:
    """Create the top-level profile directories if they don't exist."""
    PATHS["cursor_profiles_dir"].mkdir(parents=True, exist_ok=True)
    PATHS["dot_cursor_profiles"].mkdir(parents=True, exist_ok=True)


async def _is_cursor_running() -> bool:
    """Check whether Cursor is currently running (non-blocking)."""
    system = platform.system().lower()
    try:
        if system == "darwin":
            proc = await asyncio.create_subprocess_exec(
                "pgrep", "-x", "Cursor",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            return proc.returncode == 0
        elif system == "windows":
            proc = await asyncio.create_subprocess_exec(
                "tasklist", "/FI", "IMAGENAME eq Cursor.exe",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await proc.communicate()
            return b"Cursor.exe" in stdout
        else:  # Linux
            proc = await asyncio.create_subprocess_exec(
                "pgrep", "-x", "cursor",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            return proc.returncode == 0
    except Exception:
        return False


async def _abort_if_running() -> None:
    """Raise RuntimeError if Cursor is still running."""
    if await _is_cursor_running():
        raise RuntimeError(
            "Cursor is currently running. Quit it before switching or modifying profiles."
        )


async def _open_cursor() -> None:
    """Launch the Cursor application (non-blocking)."""
    system = platform.system().lower()
    try:
        if system == "darwin":
            proc = await asyncio.create_subprocess_exec("open", "-a", "Cursor")
            await proc.wait()
        elif system == "windows":
            proc = await asyncio.create_subprocess_shell("start cursor")
            await proc.wait()
        else:  # Linux
            proc = await asyncio.create_subprocess_exec("cursor")
            await proc.wait()
    except Exception as e:
        raise RuntimeError(f"Failed to open Cursor: {e}") from e


def _get_active_profile() -> str | None:
    """Return the name of the currently active profile, or None."""
    cursor_dir = PATHS["cursor_dir"]
    if cursor_dir.is_symlink():
        try:
            return cursor_dir.resolve().name
        except Exception:
            return None
    return None


def _swap_symlink(link_path: Path, target: Path) -> None:
    """Atomically replace a symlink at *link_path* to point at *target*.

    Raises RuntimeError if *link_path* exists but is **not** a symlink (to
    avoid accidentally destroying real directories).
    """
    if link_path.exists() and not link_path.is_symlink():
        raise RuntimeError(
            f"{link_path} exists and is not a symlink. "
            "Please back it up and remove it manually."
        )
    if link_path.is_symlink():
        link_path.unlink()
    link_path.symlink_to(target)


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_profiles() -> str:
    """List all available Cursor profiles.

    The active profile is marked with an asterisk (*).
    """
    _ensure_profile_roots()

    profiles: set[str] = set()

    for key in ("cursor_profiles_dir", "dot_cursor_profiles"):
        directory = PATHS[key]
        if directory.exists():
            for item in directory.iterdir():
                if item.is_dir():
                    profiles.add(item.name)

    if not profiles:
        return "No profiles found."

    active = _get_active_profile()
    lines = []
    for name in sorted(profiles):
        prefix = "* " if name == active else "  "
        lines.append(f"{prefix}{name}")

    return "Available profiles:\n" + "\n".join(lines)


@mcp.tool()
async def switch_profile(profile_name: str) -> str:
    """Switch to a specific Cursor profile and open Cursor.

    Args:
        profile_name: Name of the profile to switch to.
    """
    _validate_profile_name(profile_name)
    await _abort_if_running()
    _ensure_profile_roots()

    cursor_profile_path = PATHS["cursor_profiles_dir"] / profile_name
    dot_profile_path = PATHS["dot_cursor_profiles"] / profile_name

    if not cursor_profile_path.exists() or not dot_profile_path.exists():
        raise ValueError(
            f"Profile '{profile_name}' not found in both profile directories."
        )

    _swap_symlink(PATHS["cursor_dir"], cursor_profile_path)
    _swap_symlink(PATHS["dot_cursor"], dot_profile_path)

    await _open_cursor()
    return f"Switched to profile '{profile_name}' and opened Cursor."


@mcp.tool()
async def init_profile(profile_name: str) -> str:
    """Create a new profile from the current Cursor configuration.

    Args:
        profile_name: Name for the new profile.
    """
    _validate_profile_name(profile_name)
    await _abort_if_running()
    _ensure_profile_roots()

    cursor_profile_path = PATHS["cursor_profiles_dir"] / profile_name
    dot_profile_path = PATHS["dot_cursor_profiles"] / profile_name

    if cursor_profile_path.exists() or dot_profile_path.exists():
        raise ValueError(f"Profile '{profile_name}' already exists.")

    # --- Application Support / config directory ---
    _init_single_dir(PATHS["cursor_dir"], cursor_profile_path)

    # --- Dotfile directory ---
    _init_single_dir(PATHS["dot_cursor"], dot_profile_path)

    await _open_cursor()
    return f"Initialized new profile '{profile_name}' and opened Cursor."


def _init_single_dir(source: Path, dest: Path) -> None:
    """Copy or move *source* into *dest* and replace *source* with a symlink."""
    if source.is_symlink():
        resolved = source.resolve()
        shutil.copytree(resolved, dest)
        source.unlink()
        source.symlink_to(dest)
    elif source.exists():
        shutil.move(str(source), str(dest))
        source.symlink_to(dest)
    else:
        dest.mkdir(parents=True)
        source.symlink_to(dest)


@mcp.tool()
async def rename_profile(old_name: str, new_name: str) -> str:
    """Rename an existing Cursor profile.

    Args:
        old_name: Current name of the profile.
        new_name: New name for the profile.
    """
    _validate_profile_name(old_name)
    _validate_profile_name(new_name)
    await _abort_if_running()

    old_cursor = PATHS["cursor_profiles_dir"] / old_name
    old_dot = PATHS["dot_cursor_profiles"] / old_name
    new_cursor = PATHS["cursor_profiles_dir"] / new_name
    new_dot = PATHS["dot_cursor_profiles"] / new_name

    if not old_cursor.exists() or not old_dot.exists():
        raise ValueError(
            f"Profile '{old_name}' does not exist in both profile directories."
        )

    if new_cursor.exists() or new_dot.exists():
        raise ValueError(f"Profile '{new_name}' already exists.")

    shutil.move(str(old_cursor), str(new_cursor))
    shutil.move(str(old_dot), str(new_dot))

    # Update symlinks if they currently point to the old profile.
    if PATHS["cursor_dir"].is_symlink():
        target = PATHS["cursor_dir"].resolve()
        if target.name == old_name:
            _swap_symlink(PATHS["cursor_dir"], new_cursor)

    if PATHS["dot_cursor"].is_symlink():
        target = PATHS["dot_cursor"].resolve()
        if target.name == old_name:
            _swap_symlink(PATHS["dot_cursor"], new_dot)

    return f"Renamed profile '{old_name}' to '{new_name}'."


@mcp.tool()
async def open_cursor() -> str:
    """Open the Cursor application with the current profile."""
    await _open_cursor()
    return "Opened Cursor application."


# ---------------------------------------------------------------------------
# Git auth helpers
# ---------------------------------------------------------------------------

# Matches GitHub HTTPS remotes:  https://github.com/OWNER/REPO  or
#                                https://USER@github.com/OWNER/REPO
_GITHUB_HTTPS_RE = re.compile(
    r"https://(?:(?P<user>[^@/]+)@)?github\.com/(?P<owner>[^/]+)/(?P<repo>[^/.]+?)(?:\.git)?$"
)
# Matches GitHub SSH remotes:    git@github.com:OWNER/REPO.git
_GITHUB_SSH_RE = re.compile(
    r"git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/.]+?)(?:\.git)?$"
)


async def _run_cmd(*args: str) -> tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode or 0, stdout.decode().strip(), stderr.decode().strip()


def _parse_github_remote(url: str) -> dict[str, str | None] | None:
    """Extract owner, repo, and embedded username from a GitHub remote URL.

    Returns None if the URL is not a recognised GitHub remote.
    """
    m = _GITHUB_HTTPS_RE.match(url) or _GITHUB_SSH_RE.match(url)
    if not m:
        return None
    groups = m.groupdict()
    return {
        "owner": groups["owner"],
        "repo": groups["repo"],
        "embedded_user": groups.get("user"),  # only present for HTTPS
    }


async def _get_gh_accounts() -> list[dict[str, str | bool]]:
    """Return a list of ``{username, active}`` dicts from ``gh auth status``."""
    rc, stdout, stderr = await _run_cmd("gh", "auth", "status")
    combined = f"{stdout}\n{stderr}"  # gh may write to stderr

    accounts: list[dict[str, str | bool]] = []
    current_user: str | None = None

    for line in combined.splitlines():
        # "✓ Logged in to github.com account USERNAME (keyring)"
        logged_in = re.search(r"Logged in to github\.com account (\S+)", line)
        if logged_in:
            current_user = logged_in.group(1)
            continue
        # "- Active account: true" / "- Active account: false"
        active_match = re.search(r"Active account:\s*(true|false)", line)
        if active_match and current_user:
            accounts.append({
                "username": current_user,
                "active": active_match.group(1) == "true",
            })
            current_user = None

    return accounts


# ---------------------------------------------------------------------------
# MCP Tools — Git authentication
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_git_accounts() -> str:
    """List all GitHub accounts authenticated via the gh CLI.

    Shows which account is currently active.
    """
    accounts = await _get_gh_accounts()
    if not accounts:
        return "No GitHub accounts found. Run `gh auth login` to authenticate."

    lines = []
    for acct in accounts:
        prefix = "* " if acct["active"] else "  "
        lines.append(f"{prefix}{acct['username']}")

    return "GitHub accounts (gh CLI):\n" + "\n".join(lines)


@mcp.tool()
async def check_git_auth(repo_path: str) -> str:
    """Check whether the active gh account matches a repo's GitHub remote.

    Compares the active ``gh`` account to the owner of the ``origin`` remote.
    Reports a mismatch and suggests how to fix it.

    Args:
        repo_path: Absolute path to the git repository to check.
    """
    repo = Path(repo_path).expanduser().resolve()
    if not (repo / ".git").exists():
        raise ValueError(f"'{repo}' is not a git repository (no .git directory).")

    # Get remote URL
    rc, url, _ = await _run_cmd("git", "-C", str(repo), "remote", "get-url", "origin")
    if rc != 0 or not url:
        raise ValueError("No 'origin' remote found in this repository.")

    parsed = _parse_github_remote(url)
    if parsed is None:
        return f"Remote URL is not a GitHub URL: {url}\nGit auth check only supports GitHub remotes."

    # Get active gh account
    accounts = await _get_gh_accounts()
    active = next((a for a in accounts if a["active"]), None)
    active_user = active["username"] if active else None

    owner = parsed["owner"]
    embedded = parsed["embedded_user"]

    lines = [
        f"Repository:      {repo}",
        f"Remote URL:      {url}",
        f"Remote owner:    {owner}",
        f"Embedded user:   {embedded or '(none)'}",
        f"Active gh acct:  {active_user or '(none)'}",
        "",
    ]

    # Check embedded username in URL
    has_issues = False

    if not embedded:
        lines.append(
            "WARNING: Remote URL has no embedded username. "
            "Git will use whichever gh account is active, which may be wrong."
        )
        lines.append(
            f"  Fix: run `fix_git_remote` with repo_path='{repo}' to embed the owner in the URL."
        )
        has_issues = True

    # Check active account vs owner
    if active_user and active_user != owner:
        lines.append(
            f"MISMATCH: Active gh account '{active_user}' does not match "
            f"remote owner '{owner}'."
        )
        lines.append(
            f"  Fix: run `switch_git_account` with account='{owner}' to switch."
        )
        has_issues = True

    if not active_user:
        lines.append("WARNING: No active gh account found. Run `gh auth login`.")
        has_issues = True

    if not has_issues:
        lines.append("OK: Active gh account matches the remote owner and URL has embedded username.")

    return "\n".join(lines)


@mcp.tool()
async def fix_git_remote(repo_path: str, username: str = "") -> str:
    """Embed the GitHub username in a repo's origin URL for automatic auth.

    When the remote URL includes ``username@github.com``, the ``gh`` credential
    helper resolves the correct account token automatically — no manual
    ``gh auth switch`` needed.

    Also runs ``gh auth setup-git`` to ensure the credential helper is configured.

    Args:
        repo_path: Absolute path to the git repository.
        username:  GitHub username to embed. Defaults to the remote owner.
    """
    repo = Path(repo_path).expanduser().resolve()
    if not (repo / ".git").exists():
        raise ValueError(f"'{repo}' is not a git repository (no .git directory).")

    rc, url, _ = await _run_cmd("git", "-C", str(repo), "remote", "get-url", "origin")
    if rc != 0 or not url:
        raise ValueError("No 'origin' remote found in this repository.")

    parsed = _parse_github_remote(url)
    if parsed is None:
        return f"Remote URL is not a GitHub URL: {url}\nCannot fix non-GitHub remotes."

    target_user = username.strip() or parsed["owner"]
    new_url = f"https://{target_user}@github.com/{parsed['owner']}/{parsed['repo']}"

    # Update remote URL
    rc, _, err = await _run_cmd(
        "git", "-C", str(repo), "remote", "set-url", "origin", new_url,
    )
    if rc != 0:
        raise RuntimeError(f"Failed to update remote URL: {err}")

    # Ensure gh credential helper is configured
    rc2, _, err2 = await _run_cmd("gh", "auth", "setup-git", "-h", "github.com")
    setup_note = ""
    if rc2 != 0:
        setup_note = f"\nNote: `gh auth setup-git` failed: {err2}"

    return (
        f"Updated remote 'origin':\n"
        f"  Old: {url}\n"
        f"  New: {new_url}\n"
        f"\nThe gh credential helper will now auto-resolve the '{target_user}' account "
        f"for this repo.{setup_note}"
    )


@mcp.tool()
async def switch_git_account(account: str) -> str:
    """Switch the active GitHub account in the gh CLI.

    Args:
        account: GitHub username to switch to.
    """
    rc, stdout, stderr = await _run_cmd(
        "gh", "auth", "switch", "-h", "github.com", "-u", account,
    )
    if rc != 0:
        raise RuntimeError(
            f"Failed to switch to account '{account}': {stderr or stdout}"
        )

    return f"Switched active gh account to '{account}'."


# ---------------------------------------------------------------------------
# MCP Resources
# ---------------------------------------------------------------------------

@mcp.resource("cursor://profiles")
async def profiles_overview() -> str:
    """Cursor profiles overview including platform info and active state."""
    _ensure_profile_roots()

    profiles: set[str] = set()
    for key in ("cursor_profiles_dir", "dot_cursor_profiles"):
        directory = PATHS[key]
        if directory.exists():
            for item in directory.iterdir():
                if item.is_dir():
                    profiles.add(item.name)

    info = {
        "platform": platform.system(),
        "paths": {k: str(v) for k, v in PATHS.items()},
        "profiles": sorted(profiles),
        "active_profile": _get_active_profile(),
        "cursor_running": await _is_cursor_running(),
    }
    return json.dumps(info, indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Synchronous entry point for the console script."""
    mcp.run()


if __name__ == "__main__":
    main()
