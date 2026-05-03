#!/usr/bin/env python3
"""
OrpheusDL Installer Builder

Usage:
    python installer/build_installer.py                  # auto-detect platform
    python installer/build_installer.py --platform windows
    python installer/build_installer.py --platform linux --format deb
    python installer/build_installer.py --skip-pyinstaller  # reuse existing dist/
"""

import argparse
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import urllib.request
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
INSTALLER_DIR = Path(__file__).parent
BUILD_DIR = PROJECT_ROOT / "build"
DIST_DIR = PROJECT_ROOT / "dist"
CONFIG_FILE = PROJECT_ROOT / "build.json"


# ── Config ────────────────────────────────────────────────────────────────────

def load_config():
    if not CONFIG_FILE.exists():
        print(f"ERROR: build.json not found at {CONFIG_FILE}")
        sys.exit(1)
    with open(CONFIG_FILE) as f:
        return json.load(f)


def get_version():
    gui_path = PROJECT_ROOT / "gui.py"
    if not gui_path.exists():
        print("ERROR: gui.py not found")
        sys.exit(1)
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', gui_path.read_text(encoding="utf-8"))
    if not match:
        print("ERROR: __version__ not found in gui.py")
        sys.exit(1)
    return match.group(1)


def get_available_modules():
    modules_dir = PROJECT_ROOT / "modules"
    return [
        d.name for d in modules_dir.iterdir()
        if d.is_dir() and (d / "interface.py").exists()
    ] if modules_dir.exists() else []


def run_command(cmd, cwd=None, check=True, env=None):
    print("Running:", " ".join(str(c) for c in cmd))
    full_env = None
    if env:
        full_env = os.environ.copy()
        full_env.update(env)
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=full_env)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, cmd)
    return result


# ── PyInstaller ───────────────────────────────────────────────────────────────

def build_pyinstaller():
    print("\n=== PyInstaller build ===")

    for d in [BUILD_DIR, DIST_DIR]:
        if d.exists():
            shutil.rmtree(d)

    run_command(
        [sys.executable, "-m", "PyInstaller", "--clean", str(PROJECT_ROOT / "gui.spec")],
        cwd=PROJECT_ROOT,
    )

    # Copy config into dist so Inno Setup can pick it up
    dist_app = DIST_DIR / "OrpheusDL"
    dist_config = dist_app / "config"
    src_config = PROJECT_ROOT / "config"
    if src_config.exists() and not dist_config.exists():
        shutil.copytree(src_config, dist_config)
        print(f"Copied config → {dist_config}")

    print("PyInstaller build complete")


# ── Windows ───────────────────────────────────────────────────────────────────

def generate_version_iss(version):
    windows_dir = INSTALLER_DIR / "windows"
    windows_dir.mkdir(parents=True, exist_ok=True)
    (windows_dir / "version.iss").write_text(f'#define MyAppVersion "{version.lstrip("v")}"\n', encoding="ascii")
    print(f"Generated version.iss ({version})")


def create_inno_setup_script(cfg, modules):
    windows_dir = INSTALLER_DIR / "windows"
    windows_dir.mkdir(parents=True, exist_ok=True)

    app_name  = cfg["app_name"]
    publisher = cfg["app_publisher"]
    app_url   = cfg["app_url"]
    app_id    = cfg["app_id"]
    default_dir = cfg["install"]["default_dir_windows"]
    desktop   = str(cfg["install"]["create_desktop_shortcut"]).lower()
    launch    = str(cfg["install"]["launch_after_install"]).lower()
    inc_ffmpeg = cfg["build"]["include_ffmpeg"]

    module_components = ""
    module_files = ""
    for m in modules:
        module_components += f'Name: "modules\\{m}"; Description: "{m.capitalize()} support"; Types: full custom\n'
        module_files += (
            f'Source: "{{#RepoDir}}\\modules\\{m}\\*"; '
            f'DestDir: "{{app}}\\modules\\{m}"; '
            f'Components: modules\\{m}; Flags: recursesubdirs\n'
        )

    ffmpeg_section = ""
    if inc_ffmpeg:
        ffmpeg_section = (
            'Name: "ffmpeg"; Description: "FFmpeg (required for codec conversions)"; Types: full custom; Flags: fixed\n'
        )
        ffmpeg_files = (
            'Source: "{#RepoDir}\\bin\\ffmpeg.exe"; DestDir: "{app}"; Components: ffmpeg; Flags: ignoreversion skipifsourcedoesntexist\n'
            'Source: "{#RepoDir}\\bin\\ffprobe.exe"; DestDir: "{app}"; Components: ffmpeg; Flags: ignoreversion skipifsourcedoesntexist\n'
        )
    else:
        ffmpeg_files = ""

    icon_line = 'SetupIconFile=..\\..\\icon.ico' if (PROJECT_ROOT / "icon.ico").exists() else ""
    wizard_img = 'WizardImageFile=wizard_image.bmp' if (INSTALLER_DIR / "windows" / "wizard_image.bmp").exists() else ""
    wizard_sml = 'WizardSmallImageFile=wizard_small_image.bmp' if (INSTALLER_DIR / "windows" / "wizard_small_image.bmp").exists() else ""

    run_section = ""
    if launch == "true":
        run_section = f"""
[Run]
Filename: "{{app}}\\{app_name}.exe"; Description: "{{cm:LaunchProgram,{app_name}}}"; Flags: nowait postinstall skipifsilent
"""

    iss = f"""#define MyAppName "{app_name}"
#include "version.iss"
#define MyAppPublisher "{publisher}"
#define MyAppURL "{app_url}"
#define MyAppExeName "{app_name}.exe"
#define SourcePath "..\\..\\dist\\{app_name}"
#define RepoDir "..\\.."

[Setup]
AppId={{{{{app_id}}}}}
AppName={{#MyAppName}}
AppVersion={{#MyAppVersion}}
AppPublisher={{#MyAppPublisher}}
AppPublisherURL={{#MyAppURL}}
DefaultDirName={default_dir}
DefaultGroupName={{#MyAppName}}
UninstallDisplayIcon={{app}}\\icon.ico
UninstallDisplayName={{#MyAppName}}
OutputDir=..\\..\\dist
OutputBaseFilename={{#MyAppName}}-Setup-{{#MyAppVersion}}
{icon_line}
{wizard_img}
{wizard_sml}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
AllowNoIcons=yes
DisableProgramGroupPage=yes
CloseApplications=force

[Types]
Name: "full"; Description: "Full installation"
Name: "compact"; Description: "Compact installation"
Name: "custom"; Description: "Custom installation"; Flags: iscustom

[Components]
Name: "main"; Description: "{app_name} Core (required)"; Types: full compact custom; Flags: fixed
{ffmpeg_section}
Name: "modules"; Description: "Music Platform Modules"; Types: full custom
{module_components}

[Tasks]
Name: "desktopicon"; Description: "{{cm:CreateDesktopIcon}}"; GroupDescription: "{{cm:AdditionalIcons}}"

[Files]
Source: "{{#SourcePath}}\\{{#MyAppExeName}}"; DestDir: "{{app}}"; Components: main; Flags: ignoreversion
Source: "{{#SourcePath}}\\*"; Excludes: "{{#MyAppExeName}}"; DestDir: "{{app}}"; Components: main; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist
Source: "{{#SourcePath}}\\config\\settings.json"; DestDir: "{{app}}\\config"; Components: main; Flags: ignoreversion onlyifdoesntexist uninsneveruninstall skipifsourcedoesntexist
{ffmpeg_files}
{module_files}
Source: "{{#RepoDir}}\\modules\\__init__.py"; DestDir: "{{app}}\\modules"; Components: main; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{{group}}\\{{#MyAppName}}"; Filename: "{{app}}\\{{#MyAppExeName}}"; IconFilename: "{{app}}\\icon.ico"
Name: "{{group}}\\{{cm:UninstallProgram,{{#MyAppName}}}}"; Filename: "{{uninstallexe}}"
Name: "{{autodesktop}}\\{{#MyAppName}}"; Filename: "{{app}}\\{{#MyAppExeName}}"; IconFilename: "{{app}}\\icon.ico"; Tasks: desktopicon
{run_section}
"""
    path = windows_dir / "installer.iss"
    path.write_text(iss)
    print("Created installer/windows/installer.iss")


def build_windows_installer(cfg, modules):
    print("\n=== Windows installer ===")
    version = get_version()
    generate_version_iss(version)
    create_inno_setup_script(cfg, modules)

    iss_rel = str((INSTALLER_DIR / "windows" / "installer.iss").relative_to(PROJECT_ROOT))

    # 1. Docker (preferred on Linux/macOS — no Wine needed)
    if shutil.which("docker"):
        print("Using Docker (amake/innosetup) to compile installer…")
        run_command([
            "docker", "run", "--rm", "-i",
            "-v", f"{PROJECT_ROOT}:/work",
            "amake/innosetup",
            iss_rel,
        ])
        print("Windows installer created in dist/")
        return True

    # 2. Native Windows
    for p in [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
    ]:
        if os.path.exists(p):
            run_command([p, str(INSTALLER_DIR / "windows" / "installer.iss")])
            print("Windows installer created in dist/")
            return True

    # 3. Wine fallback
    if shutil.which("wine"):
        wine_prefix = os.path.expanduser("~/.wine")
        for rel in [
            "drive_c/Program Files (x86)/Inno Setup 6/ISCC.exe",
            "drive_c/Program Files/Inno Setup 6/ISCC.exe",
        ]:
            p = os.path.join(wine_prefix, rel)
            if os.path.exists(p):
                run_command(["wine", p, str(INSTALLER_DIR / "windows" / "installer.iss")])
                print("Windows installer created in dist/")
                return True

    print("No Inno Setup compiler found — installer.iss written but not compiled.")
    print()
    print("  Easiest : install Docker, then re-run (uses amake/innosetup image automatically)")
    print("  Windows : install Inno Setup 6 from https://jrsoftware.org/isinfo.php")
    return False


# ── Linux ─────────────────────────────────────────────────────────────────────

def _get_linux_exe():
    exe = DIST_DIR / "OrpheusDL" / "OrpheusDL"
    if not exe.exists():
        print(f"ERROR: Bundled executable not found at {exe}")
        return None
    return exe


def build_linux_appimage(cfg):
    print("\n=== Linux AppImage ===")

    appimagetool = shutil.which("appimagetool")
    if not appimagetool:
        local = INSTALLER_DIR / "linux" / "appimagetool-x86_64.AppImage"
        if local.exists():
            appimagetool = str(local)
        else:
            print("appimagetool not found — downloading…")
            url = "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
            try:
                urllib.request.urlretrieve(url, local)
                local.chmod(local.stat().st_mode | stat.S_IEXEC)
                appimagetool = str(local)
            except Exception as e:
                print(f"ERROR: {e}")
                return False

    exe = _get_linux_exe()
    if not exe:
        return False

    app_name = cfg["app_name"]
    appdir = DIST_DIR / f"{app_name}.AppDir"
    if appdir.exists():
        shutil.rmtree(appdir)

    (appdir / "usr" / "bin").mkdir(parents=True)
    (appdir / "usr" / "share" / "applications").mkdir(parents=True)
    (appdir / "usr" / "share" / "metainfo").mkdir(parents=True)
    (appdir / "usr" / "share" / "icons" / "hicolor" / "scalable" / "apps").mkdir(parents=True)

    dest_exe = appdir / "usr" / "bin" / app_name
    shutil.copy(exe, dest_exe)
    dest_exe.chmod(0o755)

    _copy_icon(cfg, appdir)

    desktop_content = _desktop_content(cfg)
    (appdir / "usr" / "share" / "applications" / "orpheusdl.desktop").write_text(desktop_content)
    (appdir / "orpheusdl.desktop").write_text(desktop_content)

    appdata_src = INSTALLER_DIR / "linux" / "orpheusdl.appdata.xml"
    if appdata_src.exists():
        shutil.copy(appdata_src, appdir / "usr" / "share" / "metainfo" / "orpheusdl.appdata.xml")

    apprun = appdir / "AppRun"
    apprun.write_text(f'#!/bin/bash\nAPPDIR="$(dirname "$(readlink -f "$0")")"\nexec "$APPDIR/usr/bin/{app_name}" "$@"\n')
    apprun.chmod(0o755)

    out = DIST_DIR / f"{app_name}-x86_64.AppImage"
    run_command(
        [appimagetool, "--no-appstream", str(appdir), str(out)],
        env={"APPIMAGE_EXTRACT_AND_RUN": "1"},
    )
    print(f"AppImage: {out}")
    return True


def build_linux_deb(cfg):
    print("\n=== Debian package ===")
    if not shutil.which("dpkg-deb"):
        print("ERROR: dpkg-deb not found")
        return False

    exe = _get_linux_exe()
    if not exe:
        return False

    app_name  = cfg["app_name"]
    publisher = cfg["app_publisher"]
    app_url   = cfg["app_url"]
    version   = get_version().lstrip("v")
    pkg_name  = app_name.lower().replace(" ", "-")

    deb_root = DIST_DIR / "deb_build" / pkg_name
    if deb_root.exists():
        shutil.rmtree(deb_root)

    (deb_root / "DEBIAN").mkdir(parents=True)
    (deb_root / "usr" / "bin").mkdir(parents=True)
    (deb_root / "usr" / "share" / "applications").mkdir(parents=True)
    (deb_root / "usr" / "share" / "metainfo").mkdir(parents=True)
    (deb_root / "usr" / "share" / "icons" / "hicolor" / "scalable" / "apps").mkdir(parents=True)

    (deb_root / "DEBIAN" / "control").write_text(
        f"Package: {pkg_name}\n"
        f"Version: {version}\n"
        "Section: sound\n"
        "Priority: optional\n"
        "Architecture: amd64\n"
        "Depends: ffmpeg\n"
        f"Maintainer: {publisher}\n"
        f"Homepage: {app_url}\n"
        f"Description: {app_name}\n"
        f" Modular music archival tool with GUI.\n"
    )

    dest_exe = deb_root / "usr" / "bin" / app_name
    shutil.copy(exe, dest_exe)
    dest_exe.chmod(0o755)

    _copy_icon(cfg, deb_root)

    (deb_root / "usr" / "share" / "applications" / "orpheusdl.desktop").write_text(_desktop_content(cfg))

    appdata_src = INSTALLER_DIR / "linux" / "orpheusdl.appdata.xml"
    if appdata_src.exists():
        shutil.copy(appdata_src, deb_root / "usr" / "share" / "metainfo" / "orpheusdl.appdata.xml")

    out = DIST_DIR / f"{app_name}-{version}-amd64.deb"
    run_command(["dpkg-deb", "--build", str(deb_root), str(out)])
    print(f"Deb package: {out}")
    return True


# ── Helpers ───────────────────────────────────────────────────────────────────

def _desktop_content(cfg):
    app_name = cfg["app_name"]
    return (
        "[Desktop Entry]\n"
        f"Name={app_name}\n"
        "Comment=Modular music archival tool\n"
        f"Exec={app_name}\n"
        "Icon=orpheusdl\n"
        "Type=Application\n"
        "Categories=AudioVideo;Audio;\n"
        "Terminal=false\n"
    )


_FALLBACK_SVG = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
  <rect width="256" height="256" rx="32" fill="#1a1a2e"/>
  <text x="128" y="172" font-family="sans-serif" font-size="140"
        text-anchor="middle" fill="#7cb4e8">♪</text>
</svg>
"""


def _copy_icon(cfg, dest_root):
    dest_root = Path(dest_root)
    copied = False
    for src, rel in [
        (PROJECT_ROOT / "icon.svg", "usr/share/icons/hicolor/scalable/apps/orpheusdl.svg"),
        (PROJECT_ROOT / "icon.png", "usr/share/icons/hicolor/256x256/apps/orpheusdl.png"),
    ]:
        if src.exists():
            out = dest_root / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, out)
            # Drop a copy in AppDir root for AppImage (must be named orpheusdl.*)
            root_copy = dest_root / ("orpheusdl" + src.suffix)
            if not root_copy.exists():
                shutil.copy(src, root_copy)
            copied = True

    if not copied:
        # No project icon found — write a minimal SVG fallback so appimagetool
        # has something to embed (avoids non-zero exit on missing icon).
        svg_rel = "usr/share/icons/hicolor/scalable/apps/orpheusdl.svg"
        out = dest_root / svg_rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(_FALLBACK_SVG)
        root_copy = dest_root / "orpheusdl.svg"
        root_copy.write_text(_FALLBACK_SVG)
        print("  (no icon.svg/icon.png found — using built-in placeholder)")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="OrpheusDL Installer Builder")
    parser.add_argument("--platform", choices=["windows", "linux", "auto"], default="auto")
    parser.add_argument("--format", choices=["all", "appimage", "deb"], default="all",
                        help="Linux format (default: all)")
    parser.add_argument("--skip-pyinstaller", action="store_true",
                        help="Skip PyInstaller build and reuse existing dist/")
    args = parser.parse_args()

    if args.platform == "auto":
        args.platform = "windows" if sys.platform == "win32" else "linux"

    cfg = load_config()
    version = get_version()
    modules = get_available_modules()

    print("\n=== OrpheusDL Installer Builder ===")
    print(f"Version : {version}")
    print(f"Platform: {args.platform}")
    print(f"Modules : {modules or '(none detected)'}")

    if not args.skip_pyinstaller:
        build_pyinstaller()
    else:
        print("\nSkipping PyInstaller (--skip-pyinstaller)")

    if args.platform == "windows":
        build_windows_installer(cfg, modules)
    elif args.platform == "linux":
        if args.format in ("all", "appimage"):
            build_linux_appimage(cfg)
        if args.format in ("all", "deb"):
            build_linux_deb(cfg)

    print("\nBuild complete. Artifacts in dist/")


if __name__ == "__main__":
    main()
