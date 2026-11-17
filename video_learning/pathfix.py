"""
Make sure the folder pip puts command .exe files in is on your Windows PATH,
so `video-transcript`, `video-study` and `video-quiz` work in every terminal
(CMD, PowerShell, Windows Terminal, VS Code).

Run automatically by install.bat, or manually:  python -m video_learning.pathfix
Only touches your *user* PATH (HKEY_CURRENT_USER\\Environment), never the system one.
"""
from __future__ import annotations

import os
import sys
import sysconfig
from pathlib import Path

COMMAND = "video-study"


def candidate_dirs() -> list[Path]:
    dirs = [sysconfig.get_path("scripts")]
    try:
        dirs.append(sysconfig.get_path("scripts", f"{os.name}_user"))
    except KeyError:
        pass
    return [Path(d) for d in dirs if d]


def find_scripts_dir() -> Path | None:
    for d in candidate_dirs():
        if (d / f"{COMMAND}.exe").exists() or (d / COMMAND).exists():
            return d
    return None


def norm(p: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.expandvars(p.strip().strip('"'))))


def main() -> None:
    scripts = find_scripts_dir()
    if scripts is None:
        sys.exit(f"Couldn't find {COMMAND}.exe - did `pip install` succeed? Looked in: "
                 + ", ".join(map(str, candidate_dirs())))

    if os.name != "nt":
        print(f"Commands installed in {scripts}. Add it to PATH in your shell profile if needed.")
        return

    import ctypes
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
        try:
            user_path, kind = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            user_path, kind = "", winreg.REG_EXPAND_SZ

        system_path = os.environ.get("PATH", "")
        known = {norm(p) for p in (user_path + ";" + system_path).split(";") if p.strip()}
        if norm(str(scripts)) in known:
            print(f"OK: {scripts} is already on your PATH.")
            return

        new_path = f"{user_path.rstrip(';')};{scripts}" if user_path else str(scripts)
        winreg.SetValueEx(key, "Path", 0, kind if kind in (winreg.REG_SZ, winreg.REG_EXPAND_SZ) else winreg.REG_EXPAND_SZ, new_path)

    # Tell Explorer/new terminals that the environment changed (no reboot or log-off needed).
    HWND_BROADCAST, WM_SETTINGCHANGE, SMTO_ABORTIFHUNG = 0xFFFF, 0x001A, 0x0002
    ctypes.windll.user32.SendMessageTimeoutW(
        HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment", SMTO_ABORTIFHUNG, 5000, ctypes.byref(ctypes.c_ulong())
    )
    print(f"Added {scripts} to your user PATH.")
    print("Open a NEW terminal window (already-open ones keep the old PATH).")


if __name__ == "__main__":
    main()
