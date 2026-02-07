#!/usr/bin/env python3
"""MCP Server for managing Cursor IDE profiles and git identities.

Leverages Cursor's native profile system for settings/extensions isolation
and adds a git identity layer so switching profiles also switches GitHub
credentials.
"""

import asyncio
import json
import platform
import re
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
            "cursor_data": home / "Library" / "Application Support" / "Cursor",
            "dot_cursor": home / ".cursor",
        }
    elif system == "windows":
        return {
            "cursor_data": home / "AppData" / "Roaming" / "Cursor",
            "dot_cursor": home / ".cursor",
        }
    else:  # Linux
        return {
            "cursor_data": home / ".config" / "Cursor",
            "dot_cursor": home / ".cursor",
        }


PATHS = _get_platform_paths()


# ---------------------------------------------------------------------------
# Identities config file  (~/.cursor/identities.json)
#
# Maps Cursor profile names to GitHub usernames:
#   {
#     "identities": {
#       "work": {"github_username": "my-work-account"},
#       "personal": {"github_username": "my-personal-account"},
#       "client-acme": {"github_username": "acme-contractor"}
#     }
#   }
# ---------------------------------------------------------------------------

def _identities_path() -> Path:
    """Path to the identities config file."""
    return PATHS["dot_cursor"] / "identities.json"


def _load_identities() -> dict[str, dict]:
    """Load the identities mapping from disk."""
    path = _identities_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("identities", {})
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_identities(identities: dict[str, dict]) -> None:
    """Persist the identities mapping to disk."""
    path = _identities_path()
    path.write_text(
        json.dumps({"identities": identities}, indent=2) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Cursor profile helpers (native profile system)
# ---------------------------------------------------------------------------

def _storage_json_path() -> Path:
    """Path to Cursor's global storage.json."""
    return PATHS["cursor_data"] / "User" / "globalStorage" / "storage.json"


def _read_storage() -> dict:
    """Read Cursor's storage.json."""
    path = _storage_json_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _get_native_profiles() -> list[dict[str, str]]:
    """Return Cursor's native profiles from storage.json.

    Each entry has ``name`` and ``location`` (the hash-based directory name).
    The Default profile is always included even if not in the list.
    """
    storage = _read_storage()
    profiles = storage.get("userDataProfiles", [])
    return profiles


def _get_active_profile_from_associations() -> str | None:
    """Try to determine which profile is currently active.

    Checks the last-opened empty window association as a heuristic.
    Returns the profile name or None.
    """
    storage = _read_storage()
    profiles = storage.get("userDataProfiles", [])
    assoc = storage.get("profileAssociations", {})

    # Map location hashes back to profile names
    loc_to_name: dict[str, str] = {}
    for p in profiles:
        loc_to_name[p["location"]] = p["name"]

    # Check emptyWindows associations (most recently opened)
    empty_windows = assoc.get("emptyWindows", {})
    if empty_windows:
        # Get the most recent empty window association
        for _ts, loc in sorted(empty_windows.items(), reverse=True):
            if loc == "__default__profile__":
                return "Default"
            if loc in loc_to_name:
                return loc_to_name[loc]

    return None


# ---------------------------------------------------------------------------
# Subprocess helpers
# ---------------------------------------------------------------------------

async def _run_cmd(*args: str) -> tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode or 0, stdout.decode().strip(), stderr.decode().strip()


async def _open_cursor_with_profile(profile_name: str | None = None) -> None:
    """Launch Cursor, optionally with a specific profile."""
    system = platform.system().lower()

    if system == "darwin":
        cmd = ["/Applications/Cursor.app/Contents/Resources/app/bin/cursor"]
    elif system == "windows":
        cmd = ["cursor"]
    else:
        cmd = ["cursor"]

    if profile_name and profile_name != "Default":
        cmd.extend(["--profile", profile_name])

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    # Don't wait — let Cursor run in the background
    # Give it a moment to start
    await asyncio.sleep(1)


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


def _parse_github_remote(url: str) -> dict[str, str | None] | None:
    """Extract owner, repo, and embedded username from a GitHub remote URL."""
    m = _GITHUB_HTTPS_RE.match(url) or _GITHUB_SSH_RE.match(url)
    if not m:
        return None
    groups = m.groupdict()
    return {
        "owner": groups["owner"],
        "repo": groups["repo"],
        "embedded_user": groups.get("user"),
    }


async def _get_gh_accounts() -> list[dict[str, str | bool]]:
    """Return a list of ``{username, active}`` dicts from ``gh auth status``."""
    rc, stdout, stderr = await _run_cmd("gh", "auth", "status")
    combined = f"{stdout}\n{stderr}"

    accounts: list[dict[str, str | bool]] = []
    current_user: str | None = None

    for line in combined.splitlines():
        logged_in = re.search(r"Logged in to github\.com account (\S+)", line)
        if logged_in:
            current_user = logged_in.group(1)
            continue
        active_match = re.search(r"Active account:\s*(true|false)", line)
        if active_match and current_user:
            accounts.append({
                "username": current_user,
                "active": active_match.group(1) == "true",
            })
            current_user = None

    return accounts


async def _switch_gh_account(username: str) -> tuple[bool, str]:
    """Switch the active gh account. Returns (success, message)."""
    rc, stdout, stderr = await _run_cmd(
        "gh", "auth", "switch", "-h", "github.com", "-u", username,
    )
    if rc != 0:
        return False, f"Failed to switch to '{username}': {stderr or stdout}"
    return True, f"Switched active gh account to '{username}'."


# ---------------------------------------------------------------------------
# MCP Tools — Profile management (leveraging Cursor's native profiles)
# ---------------------------------------------------------------------------

@mcp.tool(name="show_profiles")
async def show_profiles() -> str:
    """List all available Cursor profiles.

    The active profile is marked with an asterisk (*).
    """
    native = _get_native_profiles()
    identities = _load_identities()
    active = _get_active_profile_from_associations()

    lines = []

    # Default profile is always present
    prefix = "* " if active == "Default" or active is None else "  "
    gh_info = ""
    if "Default" in identities:
        gh_info = f"  (github: {identities['Default']['github_username']})"
    lines.append(f"{prefix}Default{gh_info}")

    for prof in sorted(native, key=lambda p: p["name"]):
        name = prof["name"]
        prefix = "* " if name == active else "  "
        gh_info = ""
        if name in identities:
            gh_info = f"  (github: {identities[name]['github_username']})"
        lines.append(f"{prefix}{name}{gh_info}")

    return "Cursor profiles:\n" + "\n".join(lines)


@mcp.tool()
async def switch_profile(profile_name: str) -> str:
    """Switch to a specific Cursor profile and open Cursor.

    If the profile has a linked git identity, the active GitHub account
    is switched automatically.

    Args:
        profile_name: Name of the profile to switch to.
    """
    # Verify the profile exists (unless it's Default)
    if profile_name != "Default":
        native = _get_native_profiles()
        names = {p["name"] for p in native}
        if profile_name not in names:
            available = ", ".join(sorted(names)) or "(none)"
            raise ValueError(
                f"Profile '{profile_name}' not found. "
                f"Available: Default, {available}"
            )

    # Switch git identity if one is linked
    identities = _load_identities()
    git_msg = ""
    if profile_name in identities:
        gh_user = identities[profile_name]["github_username"]
        ok, msg = await _switch_gh_account(gh_user)
        git_msg = f"\nGit identity: {msg}"

    # Open Cursor with the target profile
    await _open_cursor_with_profile(profile_name)

    return f"Switched to profile '{profile_name}' and opened Cursor.{git_msg}"


@mcp.tool()
async def init_profile(profile_name: str, github_username: str = "") -> str:
    """Create a new Cursor profile, optionally linked to a GitHub identity.

    Uses Cursor's native profile system. The profile is created and Cursor
    opens with it.

    Args:
        profile_name: Name for the new profile.
        github_username: GitHub username to link (optional). If provided,
                        switching to this profile will auto-switch gh accounts.
    """
    if not profile_name or not re.match(r"^[A-Za-z0-9][A-Za-z0-9 ._-]*$", profile_name):
        raise ValueError(
            f"Invalid profile name '{profile_name}'. "
            "Use letters, digits, spaces, hyphens, underscores, and dots. "
            "Must start with a letter or digit."
        )

    # Check if it already exists
    native = _get_native_profiles()
    names = {p["name"] for p in native}
    if profile_name in names:
        raise ValueError(f"Profile '{profile_name}' already exists.")

    # Link git identity if provided
    if github_username.strip():
        identities = _load_identities()
        identities[profile_name] = {"github_username": github_username.strip()}
        _save_identities(identities)

    # Create the profile by opening Cursor with --profile (auto-creates if new)
    await _open_cursor_with_profile(profile_name)

    result = f"Created profile '{profile_name}' and opened Cursor."
    if github_username.strip():
        result += f"\nLinked to GitHub account: {github_username.strip()}"

    return result


@mcp.tool()
async def link_identity(profile_name: str, github_username: str) -> str:
    """Link a GitHub identity to an existing Cursor profile.

    When you switch to this profile, the gh CLI account will be
    switched automatically.

    Args:
        profile_name: Name of the Cursor profile.
        github_username: GitHub username to link.
    """
    # Verify the profile exists
    if profile_name != "Default":
        native = _get_native_profiles()
        names = {p["name"] for p in native}
        if profile_name not in names:
            raise ValueError(f"Profile '{profile_name}' not found.")

    if not github_username.strip():
        raise ValueError("GitHub username cannot be empty.")

    identities = _load_identities()
    identities[profile_name] = {"github_username": github_username.strip()}
    _save_identities(identities)

    return (
        f"Linked profile '{profile_name}' to GitHub account '{github_username.strip()}'.\n"
        f"Switching to this profile will now auto-switch your gh account."
    )


@mcp.tool()
async def unlink_identity(profile_name: str) -> str:
    """Remove the GitHub identity link from a Cursor profile.

    Args:
        profile_name: Name of the Cursor profile to unlink.
    """
    identities = _load_identities()
    if profile_name not in identities:
        return f"Profile '{profile_name}' has no linked identity."

    del identities[profile_name]
    _save_identities(identities)
    return f"Removed identity link from profile '{profile_name}'."


@mcp.tool()
async def open_cursor() -> str:
    """Open the Cursor application with the current profile."""
    await _open_cursor_with_profile()
    return "Opened Cursor application."


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

    rc, url, _ = await _run_cmd("git", "-C", str(repo), "remote", "get-url", "origin")
    if rc != 0 or not url:
        raise ValueError("No 'origin' remote found in this repository.")

    parsed = _parse_github_remote(url)
    if parsed is None:
        return f"Remote URL is not a GitHub URL: {url}\nGit auth check only supports GitHub remotes."

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

    rc, _, err = await _run_cmd(
        "git", "-C", str(repo), "remote", "set-url", "origin", new_url,
    )
    if rc != 0:
        raise RuntimeError(f"Failed to update remote URL: {err}")

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
    ok, msg = await _switch_gh_account(account)
    if not ok:
        raise RuntimeError(msg)
    return msg


# ---------------------------------------------------------------------------
# MCP Resources
# ---------------------------------------------------------------------------

@mcp.resource("cursor://profiles")
async def profiles_overview() -> str:
    """Cursor profiles overview including platform info and identity bindings."""
    native = _get_native_profiles()
    identities = _load_identities()
    accounts = await _get_gh_accounts()
    active_gh = next((a["username"] for a in accounts if a["active"]), None)

    info = {
        "platform": platform.system(),
        "cursor_data": str(PATHS["cursor_data"]),
        "profiles": [
            {"name": "Default", "location": "__default__profile__"},
            *[{"name": p["name"], "location": p["location"]} for p in native],
        ],
        "identities": identities,
        "active_gh_account": active_gh,
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
