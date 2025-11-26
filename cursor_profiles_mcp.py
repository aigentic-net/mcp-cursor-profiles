#!/usr/bin/env python3
"""
MCP Server for managing Cursor profiles across platforms
"""

import asyncio
import json
import os
import platform
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional
import subprocess

from mcp.server import Server
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types

# Platform-specific paths
def get_platform_paths():
    system = platform.system().lower()
    home = Path.home()
    
    if system == "darwin":  # macOS
        return {
            "cursor_dir": home / "Library" / "Application Support" / "Cursor",
            "cursor_profiles_dir": home / "Library" / "Application Support" / "CursorProfiles",
            "dot_cursor": home / ".cursor",
            "dot_cursor_profiles": home / ".cursor-profiles"
        }
    elif system == "windows":
        return {
            "cursor_dir": home / "AppData" / "Roaming" / "Cursor",
            "cursor_profiles_dir": home / "AppData" / "Roaming" / "CursorProfiles",
            "dot_cursor": home / ".cursor",
            "dot_cursor_profiles": home / ".cursor-profiles"
        }
    else:  # Linux and other Unix-like systems
        return {
            "cursor_dir": home / ".config" / "Cursor",
            "cursor_profiles_dir": home / ".config" / "CursorProfiles",
            "dot_cursor": home / ".cursor",
            "dot_cursor_profiles": home / ".cursor-profiles"
        }

PATHS = get_platform_paths()

class CursorProfileManager:
    def __init__(self):
        self.paths = PATHS
        
    def ensure_profile_roots(self):
        """Create profile directories if they don't exist"""
        self.paths["cursor_profiles_dir"].mkdir(parents=True, exist_ok=True)
        self.paths["dot_cursor_profiles"].mkdir(parents=True, exist_ok=True)
        
    def is_cursor_running(self) -> bool:
        """Check if Cursor is currently running"""
        system = platform.system().lower()
        try:
            if system == "darwin":
                result = subprocess.run(["pgrep", "-x", "Cursor"], capture_output=True, text=True)
                return result.returncode == 0
            elif system == "windows":
                result = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Cursor.exe"], 
                                      capture_output=True, text=True)
                return "Cursor.exe" in result.stdout
            else:  # Linux
                result = subprocess.run(["pgrep", "-x", "cursor"], capture_output=True, text=True)
                return result.returncode == 0
        except Exception:
            return False
    
    def abort_if_running(self):
        """Raise an exception if Cursor is running"""
        if self.is_cursor_running():
            raise RuntimeError("Cursor is currently running. Quit it before switching or modifying profiles.")
    
    def open_cursor(self):
        """Open Cursor application"""
        system = platform.system().lower()
        try:
            if system == "darwin":
                subprocess.run(["open", "-a", "Cursor"])
            elif system == "windows":
                subprocess.run(["start", "cursor"], shell=True)
            else:  # Linux
                subprocess.run(["cursor"])
        except Exception as e:
            raise RuntimeError(f"Failed to open Cursor: {e}")
    
    def list_profiles(self) -> List[str]:
        """List all available profiles"""
        self.ensure_profile_roots()
        
        profiles = set()
        
        # Get profiles from cursor profiles directory
        if self.paths["cursor_profiles_dir"].exists():
            for item in self.paths["cursor_profiles_dir"].iterdir():
                if item.is_dir():
                    profiles.add(item.name)
        
        # Get profiles from dot cursor profiles directory
        if self.paths["dot_cursor_profiles"].exists():
            for item in self.paths["dot_cursor_profiles"].iterdir():
                if item.is_dir():
                    profiles.add(item.name)
        
        # Get active profile
        active_profile = None
        if self.paths["cursor_dir"].is_symlink():
            try:
                target = self.paths["cursor_dir"].resolve()
                active_profile = target.name
            except Exception:
                pass
        
        # Return sorted list with active profile marked
        sorted_profiles = sorted(profiles)
        if active_profile and active_profile in sorted_profiles:
            sorted_profiles[sorted_profiles.index(active_profile)] = f"* {active_profile}"
        
        return sorted_profiles
    
    def switch_profile(self, profile_name: str):
        """Switch to a specific profile"""
        self.abort_if_running()
        self.ensure_profile_roots()
        
        # Validate profile exists in both directories
        cursor_profile_path = self.paths["cursor_profiles_dir"] / profile_name
        dot_profile_path = self.paths["dot_cursor_profiles"] / profile_name
        
        if not cursor_profile_path.exists() or not dot_profile_path.exists():
            raise ValueError(f"Profile '{profile_name}' not found in both profile directories")
        
        # Switch cursor directory
        if self.paths["cursor_dir"].exists() and not self.paths["cursor_dir"].is_symlink():
            raise RuntimeError(f"{self.paths['cursor_dir']} exists and is not a symlink")
        
        if self.paths["cursor_dir"].exists():
            self.paths["cursor_dir"].unlink()
        self.paths["cursor_dir"].symlink_to(cursor_profile_path)
        
        # Switch dot cursor directory
        if self.paths["dot_cursor"].exists() and not self.paths["dot_cursor"].is_symlink():
            raise RuntimeError(f"{self.paths['dot_cursor']} exists and is not a symlink")
        
        if self.paths["dot_cursor"].exists():
            self.paths["dot_cursor"].unlink()
        self.paths["dot_cursor"].symlink_to(dot_profile_path)
    
    def init_profile(self, profile_name: str):
        """Initialize a new profile from current config"""
        self.abort_if_running()
        self.ensure_profile_roots()
        
        cursor_profile_path = self.paths["cursor_profiles_dir"] / profile_name
        dot_profile_path = self.paths["dot_cursor_profiles"] / profile_name
        
        if cursor_profile_path.exists() or dot_profile_path.exists():
            raise ValueError(f"Profile '{profile_name}' already exists")
        
        # Handle cursor directory
        if self.paths["cursor_dir"].is_symlink():
            current_target = self.paths["cursor_dir"].resolve()
            shutil.copytree(current_target, cursor_profile_path)
            self.paths["cursor_dir"].unlink()
            self.paths["cursor_dir"].symlink_to(cursor_profile_path)
        elif self.paths["cursor_dir"].exists():
            shutil.move(str(self.paths["cursor_dir"]), str(cursor_profile_path))
            self.paths["cursor_dir"].symlink_to(cursor_profile_path)
        else:
            cursor_profile_path.mkdir(parents=True)
            self.paths["cursor_dir"].symlink_to(cursor_profile_path)
        
        # Handle dot cursor directory
        if self.paths["dot_cursor"].is_symlink():
            current_target = self.paths["dot_cursor"].resolve()
            shutil.copytree(current_target, dot_profile_path)
            self.paths["dot_cursor"].unlink()
            self.paths["dot_cursor"].symlink_to(dot_profile_path)
        elif self.paths["dot_cursor"].exists():
            shutil.move(str(self.paths["dot_cursor"]), str(dot_profile_path))
            self.paths["dot_cursor"].symlink_to(dot_profile_path)
        else:
            dot_profile_path.mkdir(parents=True)
            self.paths["dot_cursor"].symlink_to(dot_profile_path)
    
    def rename_profile(self, old_name: str, new_name: str):
        """Rename a profile"""
        self.abort_if_running()
        
        old_cursor_path = self.paths["cursor_profiles_dir"] / old_name
        old_dot_path = self.paths["dot_cursor_profiles"] / old_name
        new_cursor_path = self.paths["cursor_profiles_dir"] / new_name
        new_dot_path = self.paths["dot_cursor_profiles"] / new_name
        
        if not old_cursor_path.exists() or not old_dot_path.exists():
            raise ValueError(f"Profile '{old_name}' does not exist in both profile directories")
        
        if new_cursor_path.exists() or new_dot_path.exists():
            raise ValueError(f"Profile '{new_name}' already exists")
        
        # Rename the directories
        shutil.move(str(old_cursor_path), str(new_cursor_path))
        shutil.move(str(old_dot_path), str(new_dot_path))
        
        # Update symlinks if they point to the old profile
        if self.paths["cursor_dir"].is_symlink():
            try:
                current_target = self.paths["cursor_dir"].resolve()
                if current_target.name == old_name:
                    self.paths["cursor_dir"].unlink()
                    self.paths["cursor_dir"].symlink_to(new_cursor_path)
            except Exception:
                pass
        
        if self.paths["dot_cursor"].is_symlink():
            try:
                current_target = self.paths["dot_cursor"].resolve()
                if current_target.name == old_name:
                    self.paths["dot_cursor"].unlink()
                    self.paths["dot_cursor"].symlink_to(new_dot_path)
            except Exception:
                pass

# Create MCP server
server = Server("cursor-profiles")

profile_manager = CursorProfileManager()

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="list_profiles",
            description="List all available Cursor profiles",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        types.Tool(
            name="switch_profile",
            description="Switch to a specific Cursor profile",
            inputSchema={
                "type": "object",
                "properties": {
                    "profile_name": {
                        "type": "string",
                        "description": "Name of the profile to switch to"
                    }
                },
                "required": ["profile_name"]
            }
        ),
        types.Tool(
            name="init_profile",
            description="Initialize a new profile from current Cursor configuration",
            inputSchema={
                "type": "object",
                "properties": {
                    "profile_name": {
                        "type": "string",
                        "description": "Name for the new profile"
                    }
                },
                "required": ["profile_name"]
            }
        ),
        types.Tool(
            name="rename_profile",
            description="Rename an existing Cursor profile",
            inputSchema={
                "type": "object",
                "properties": {
                    "old_name": {
                        "type": "string",
                        "description": "Current name of the profile"
                    },
                    "new_name": {
                        "type": "string",
                        "description": "New name for the profile"
                    }
                },
                "required": ["old_name", "new_name"]
            }
        ),
        types.Tool(
            name="open_cursor",
            description="Open Cursor application with current profile",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        if name == "list_profiles":
            profiles = profile_manager.list_profiles()
            if not profiles:
                return [types.TextContent(type="text", text="No profiles found")]
            
            profile_list = "\n".join(profiles)
            return [types.TextContent(type="text", text=f"Available profiles:\n{profile_list}")]
        
        elif name == "switch_profile":
            profile_name = arguments["profile_name"]
            profile_manager.switch_profile(profile_name)
            profile_manager.open_cursor()
            return [types.TextContent(type="text", text=f"Switched to profile '{profile_name}' and opened Cursor")]
        
        elif name == "init_profile":
            profile_name = arguments["profile_name"]
            profile_manager.init_profile(profile_name)
            profile_manager.open_cursor()
            return [types.TextContent(type="text", text=f"Initialized new profile '{profile_name}' and opened Cursor")]
        
        elif name == "rename_profile":
            old_name = arguments["old_name"]
            new_name = arguments["new_name"]
            profile_manager.rename_profile(old_name, new_name)
            return [types.TextContent(type="text", text=f"Renamed profile '{old_name}' to '{new_name}'")]
        
        elif name == "open_cursor":
            profile_manager.open_cursor()
            return [types.TextContent(type="text", text="Opened Cursor application")]
        
        else:
            raise ValueError(f"Unknown tool: {name}")
            
    except Exception as e:
        return [types.TextContent(type="text", text=f"Error: {str(e)}")]

@server.list_resources()
async def handle_list_resources() -> list[types.Resource]:
    return [
        types.Resource(
            uri="cursor://profiles",
            mimeType="application/json",
            name="Cursor Profiles Overview"
        )
    ]

@server.read_resource()
async def handle_read_resource(uri: str) -> types.ReadResourceResult:
    if uri == "cursor://profiles":
        profiles = profile_manager.list_profiles()
        platform_info = {
            "platform": platform.system(),
            "paths": {k: str(v) for k, v in PATHS.items()},
            "profiles": profiles,
            "cursor_running": profile_manager.is_cursor_running()
        }
        return types.ReadResourceResult(
            contents=[types.TextContent(type="text", text=json.dumps(platform_info, indent=2))]
        )
    
    raise ValueError(f"Unknown resource: {uri}")

async def main():
    # Run the server using stdin/stdout streams
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="cursor-profiles",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=None,
                    experimental_capabilities=None
                )
            )
        )

if __name__ == "__main__":
    asyncio.run(main())
