import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
BIN_DIR = os.path.join(ROOT, "bin")


def _ok(msg):
    print(f"  [ok]   {msg}")

def _skip(msg):
    print(f"  [skip] {msg}")

def _warn(msg):
    print(f"  [warn] {msg}")

def _err(msg):
    print(f"  [error] {msg}")

def _step(msg):
    print(f"\n>> {msg}")


# ── Step 1: Python version ────────────────────────────────────────────────────

def check_python_version():
    _step("Checking Python version")
    major, minor = sys.version_info[:2]
    if (major, minor) < (3, 8):
        _err(f"Python 3.8+ required. You have {major}.{minor}.")
        sys.exit(1)
    _ok(f"Python {major}.{minor}")


# ── Step 2: tkinter ───────────────────────────────────────────────────────────

def ensure_tkinter():
    _step("Checking tkinter")
    try:
        import tkinter  # noqa: F401
        _ok("tkinter available")
        return
    except ModuleNotFoundError:
        pass

    if sys.platform == "win32":
        _warn("tkinter not found. Reinstall Python and check 'tcl/tk and IDLE' during setup.")
        return

    # Linux — try to install via system package manager
    if shutil.which("apt-get"):
        _step("Installing python3-tk via apt-get")
        result = subprocess.run(["sudo", "apt-get", "install", "-y", "python3-tk"])
        if result.returncode == 0:
            _ok("python3-tk installed")
        else:
            _warn("apt-get failed. Install manually: sudo apt-get install python3-tk")
    elif shutil.which("dnf"):
        _step("Installing python3-tkinter via dnf")
        result = subprocess.run(["sudo", "dnf", "install", "-y", "python3-tkinter"])
        if result.returncode == 0:
            _ok("python3-tkinter installed")
        else:
            _warn("dnf failed. Install manually: sudo dnf install python3-tkinter")
    elif shutil.which("pacman"):
        _step("Installing tk via pacman")
        result = subprocess.run(["sudo", "pacman", "-S", "--noconfirm", "tk"])
        if result.returncode == 0:
            _ok("tk installed")
        else:
            _warn("pacman failed. Install manually: sudo pacman -S tk")
    else:
        _warn("Could not detect package manager. Install tkinter manually for your distro.")


# ── Step 3: settings.json ─────────────────────────────────────────────────────

def create_settings_if_missing():
    _step("Checking config/settings.json")
    config_dir = os.path.join(ROOT, "config")
    settings_path = os.path.join(config_dir, "settings.json")
    example_path = os.path.join(ROOT, "settings.json.example")

    if os.path.exists(settings_path):
        _skip("config/settings.json already exists")
        return

    os.makedirs(config_dir, exist_ok=True)
    if not os.path.exists(example_path):
        _warn("settings.json.example not found — skipping")
        return

    shutil.copy(example_path, settings_path)
    _ok("Created config/settings.json from settings.json.example")


# ── Step 4: pip dependencies ──────────────────────────────────────────────────

def install_pip_deps():
    _step("Installing pip dependencies")
    reqs = ["requirements.txt", "requirements-gui.txt"]
    for req in reqs:
        path = os.path.join(ROOT, req)
        if not os.path.exists(path):
            _skip(f"{req} not found")
            continue
        result = subprocess.run([sys.executable, "-m", "pip", "install", "-r", path])
        if result.returncode == 0:
            _ok(f"Installed {req}")
        else:
            _err(f"Failed to install {req}")
            sys.exit(1)


# ── Step 5: git submodules ────────────────────────────────────────────────────

def init_submodules():
    _step("Initializing git submodules")
    if not os.path.exists(os.path.join(ROOT, ".git")):
        _warn("Not a git repository — skipping submodule init")
        return
    if not os.path.exists(os.path.join(ROOT, ".gitmodules")):
        _skip("No .gitmodules found")
        return
    result = subprocess.run(
        ["git", "submodule", "update", "--init", "--recursive"],
        cwd=ROOT,
    )
    if result.returncode == 0:
        _ok("Submodules initialized")
    else:
        _err("git submodule update failed")


# ── Step 6: FFmpeg ────────────────────────────────────────────────────────────

def _download_with_progress(url, dest_path):
    print(f"     Downloading {os.path.basename(dest_path)}…", end="", flush=True)

    def reporthook(count, block_size, total_size):
        if total_size > 0:
            pct = min(100, int(count * block_size * 100 / total_size))
            print(f"\r     Downloading {os.path.basename(dest_path)}… {pct}%", end="", flush=True)

    urllib.request.urlretrieve(url, dest_path, reporthook)
    print()  # newline after progress


def download_ffmpeg():
    _step("Checking FFmpeg")

    if shutil.which("ffmpeg"):
        _skip("ffmpeg already on PATH")
        return

    ffmpeg_bin = os.path.join(BIN_DIR, "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    ffprobe_bin = os.path.join(BIN_DIR, "ffprobe.exe" if sys.platform == "win32" else "ffprobe")

    if os.path.exists(ffmpeg_bin):
        _skip(f"bin/ffmpeg already exists")
        return

    os.makedirs(BIN_DIR, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        if sys.platform == "win32":
            _download_ffmpeg_windows(tmp, ffmpeg_bin, ffprobe_bin)
        elif sys.platform == "linux":
            _download_ffmpeg_linux(tmp, ffmpeg_bin, ffprobe_bin)
        else:
            _warn(f"Unsupported platform '{sys.platform}'. Install FFmpeg manually.")
            return

    _ok(f"FFmpeg saved to bin/")
    _warn("Add the bin/ directory to your PATH to use FFmpeg system-wide.")


def _download_ffmpeg_windows(tmp, ffmpeg_dest, ffprobe_dest):
    url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
    zip_path = os.path.join(tmp, "ffmpeg.zip")
    try:
        _download_with_progress(url, zip_path)
    except Exception as e:
        _err(f"Download failed: {e}")
        _warn("Download FFmpeg manually from https://ffmpeg.org/download.html")
        return

    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            basename = os.path.basename(member)
            if basename in ("ffmpeg.exe", "ffprobe.exe"):
                dest = ffmpeg_dest if basename == "ffmpeg.exe" else ffprobe_dest
                with zf.open(member) as src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst)


def _download_ffmpeg_linux(tmp, ffmpeg_dest, ffprobe_dest):
    arch = platform.machine()
    if arch not in ("x86_64", "aarch64"):
        _warn(f"Architecture {arch} not directly supported. Install FFmpeg via your package manager.")
        return

    arch_slug = "amd64" if arch == "x86_64" else "arm64"
    url = f"https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-{arch_slug}-static.tar.xz"
    tar_path = os.path.join(tmp, "ffmpeg.tar.xz")
    try:
        _download_with_progress(url, tar_path)
    except Exception as e:
        _err(f"Download failed: {e}")
        _warn("Install FFmpeg via your package manager: sudo apt-get install ffmpeg")
        return

    with tarfile.open(tar_path, "r:xz") as tf:
        for member in tf.getmembers():
            basename = os.path.basename(member.name)
            if basename in ("ffmpeg", "ffprobe") and not member.isdir():
                dest = ffmpeg_dest if basename == "ffmpeg" else ffprobe_dest
                src = tf.extractfile(member)
                if src:
                    with open(dest, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    os.chmod(dest, 0o755)


# ── Summary ───────────────────────────────────────────────────────────────────

def print_summary():
    _step("Setup complete")
    print()
    print("  Run the GUI with:")
    print(f"    python gui.py")
    print()
    bin_dir_rel = os.path.relpath(BIN_DIR, ROOT)
    if os.path.isdir(BIN_DIR) and any(
        f.startswith("ffmpeg") for f in os.listdir(BIN_DIR)
    ):
        if sys.platform == "win32":
            print(f"  To use FFmpeg system-wide, add to PATH:")
            print(f"    {BIN_DIR}")
        else:
            print(f"  To use FFmpeg system-wide, add to your shell profile:")
            print(f"    export PATH=\"{BIN_DIR}:$PATH\"")
        print()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    print("OrpheusDL Installer")
    print("===================")
    check_python_version()
    ensure_tkinter()
    create_settings_if_missing()
    install_pip_deps()
    init_submodules()
    download_ffmpeg()
    print_summary()


if __name__ == "__main__":
    main()
