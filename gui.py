import customtkinter as ctk
import json
import os
import queue
import re
import runpy
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter
import tkinter.filedialog
import urllib.request
from packaging.version import parse as parse_version

__version__ = "1.0.0"

# Read from build.json if present, otherwise fall back to defaults
def _load_build_cfg():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build.json")
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return {}

_BUILD_CFG = _load_build_cfg()
_APP_URL = _BUILD_CFG.get("app_url", "https://github.com/xbufu/OrpheusDL")
# Derive owner/repo from URL: "https://github.com/owner/repo"
_GH_OWNER_REPO = "/".join(_APP_URL.rstrip("/").split("/")[-2:])
_GH_API_LATEST = f"https://api.github.com/repos/{_GH_OWNER_REPO}/releases/latest"

# When frozen by PyInstaller (--onedir), sys.executable is the bundled .exe
# and __file__ points into the read-only _internal/ bundle dir.
# User-writable files (settings) must live next to the exe instead.
if getattr(sys, "frozen", False):
    _APP_DIR    = os.path.dirname(sys.executable)       # writable install dir
    _BUNDLE_DIR = getattr(sys, "_MEIPASS", _APP_DIR)    # read-only _internal/
    _ORPHEUS_PY = os.path.join(_BUNDLE_DIR, "orpheus.py")
else:
    _APP_DIR    = os.path.dirname(os.path.abspath(__file__))
    _BUNDLE_DIR = _APP_DIR
    _ORPHEUS_PY = os.path.join(_APP_DIR, "orpheus.py")

SETTINGS_PATH   = os.path.join(_APP_DIR, "config", "settings.json")
_SETTINGS_EXAMPLE = os.path.join(_BUNDLE_DIR, "settings.json.example")

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

QUALITY_OPTIONS = ["hifi", "lossless", "high", "medium", "low"]
COMPRESSION_OPTIONS = ["high", "medium", "low"]
M3U_PATH_OPTIONS = ["absolute", "relative"]
EXTERNAL_FORMAT_OPTIONS = ["png", "jpg", "jpeg"]


def _ensure_settings():
    if os.path.exists(SETTINGS_PATH):
        return
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    if os.path.exists(_SETTINGS_EXAMPLE):
        shutil.copy(_SETTINGS_EXAMPLE, SETTINGS_PATH)
    else:
        # Absolute fallback — write a minimal valid structure
        with open(SETTINGS_PATH, "w") as f:
            json.dump({"global": {
                "general": {"download_path": "./downloads/", "download_quality": "hifi", "search_limit": 10},
                "artist_downloading": {"return_credited_albums": True, "separate_tracks_skip_downloaded": True},
                "formatting": {"album_format": "{name}{explicit}", "playlist_format": "{name}{explicit}",
                               "track_filename_format": "{album_artist} - {name}",
                               "single_full_path_format": "{artist} - {name}",
                               "enable_zfill": True, "force_album_format": False},
                "codecs": {"proprietary_codecs": False, "spatial_codecs": True},
                "module_defaults": {"lyrics": "default", "covers": "default", "credits": "default"},
                "lyrics": {"embed_lyrics": True, "embed_synced_lyrics": False, "save_synced_lyrics": True},
                "covers": {"embed_cover": True, "main_compression": "high", "main_resolution": 1400,
                           "save_external": False, "external_format": "png", "external_compression": "low",
                           "external_resolution": 3000, "save_animated_cover": True},
                "playlist": {"save_m3u": True, "paths_m3u": "absolute", "extended_m3u": True},
                "advanced": {"advanced_login_system": False, "codec_conversions": {},
                             "conversion_flags": {}, "conversion_keep_original": False,
                             "cover_variance_threshold": 8, "debug_mode": False,
                             "disable_subscription_checks": False, "enable_undesirable_conversions": False,
                             "ignore_existing_files": False, "ignore_different_artists": True}
            }, "extensions": {}, "modules": {}}, f, indent=4)


def load_settings():
    _ensure_settings()
    with open(SETTINGS_PATH, "r") as f:
        return json.load(f)


def save_settings(data):
    with open(SETTINGS_PATH, "w") as f:
        json.dump(data, f, indent=4)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("OrpheusDL")
        self.geometry("900x620")
        self.minsize(700, 500)

        self._output_queue = queue.Queue()

        self._tabview = ctk.CTkTabview(self)
        self._tabview.pack(fill="both", expand=True, padx=10, pady=10)

        self._tabview.add("Download")
        self._tabview.add("Settings")
        self._tabview.add("Updates")

        self._build_download_tab(self._tabview.tab("Download"))
        self._build_settings_tab(self._tabview.tab("Settings"))
        self._build_updates_tab(self._tabview.tab("Updates"))

    # ── Download Tab ──────────────────────────────────────────────────────────

    def _build_download_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(4, weight=1)

        # URL row
        url_frame = ctk.CTkFrame(parent, fg_color="transparent")
        url_frame.grid(row=0, column=0, sticky="ew", pady=(6, 4))
        url_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(url_frame, text="URL:", width=50, anchor="w").grid(row=0, column=0, padx=(0, 6))
        self._url_entry = ctk.CTkEntry(url_frame, placeholder_text="Paste download URL here…")
        self._url_entry.grid(row=0, column=1, sticky="ew")
        ctk.CTkButton(url_frame, text="Clear", width=60, command=lambda: self._url_entry.delete(0, "end")).grid(row=0, column=2, padx=(6, 0))

        # Output path row
        out_frame = ctk.CTkFrame(parent, fg_color="transparent")
        out_frame.grid(row=1, column=0, sticky="ew", pady=4)
        out_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(out_frame, text="Output:", width=50, anchor="w").grid(row=0, column=0, padx=(0, 6))
        self._out_entry = ctk.CTkEntry(out_frame, placeholder_text="Override output path (optional)")
        self._out_entry.grid(row=0, column=1, sticky="ew")
        ctk.CTkButton(out_frame, text="Browse", width=60, command=self._browse_output).grid(row=0, column=2, padx=(6, 0))

        # Action buttons + progress bar
        action_frame = ctk.CTkFrame(parent, fg_color="transparent")
        action_frame.grid(row=2, column=0, sticky="ew", pady=4)
        action_frame.grid_columnconfigure(1, weight=1)

        self._download_btn = ctk.CTkButton(action_frame, text="Download", width=110, command=self._start_download)
        self._download_btn.grid(row=0, column=0, padx=(0, 10))

        self._progress = ctk.CTkProgressBar(action_frame, mode="indeterminate")
        self._progress.grid(row=0, column=1, sticky="ew")

        self._stop_btn = ctk.CTkButton(action_frame, text="Stop", width=80, fg_color="#c0392b", hover_color="#a93226", command=self._stop_download, state="disabled")
        self._stop_btn.grid(row=0, column=2, padx=(10, 0))

        # Log output
        self._log = tkinter.Text(
            parent,
            bg="#1a1a2e",
            fg="#c9d1d9",
            insertbackground="#c9d1d9",
            selectbackground="#3a3a5c",
            relief="flat",
            font=("Consolas", 10) if sys.platform == "win32" else ("Courier", 10),
            wrap="word",
            state="disabled",
        )
        self._log.grid(row=4, column=0, sticky="nsew", pady=(6, 0))

        # Colour tags
        self._log.tag_configure("header",  foreground="#58a6ff", font=(
            ("Consolas", 10, "bold") if sys.platform == "win32" else ("Courier", 10, "bold")))
        self._log.tag_configure("success", foreground="#3fb950")
        self._log.tag_configure("error",   foreground="#f85149")
        self._log.tag_configure("warning", foreground="#d29922")
        self._log.tag_configure("gray",    foreground="#8b949e")
        self._log.tag_configure("meta",    foreground="#8b949e")
        self._log.tag_configure("dim",     foreground="#6e7681")

        scrollbar = ctk.CTkScrollbar(parent, command=self._log.yview)
        scrollbar.grid(row=4, column=1, sticky="ns", pady=(6, 0))
        self._log.configure(yscrollcommand=scrollbar.set)

        self._log_last_empty = False

        clear_frame = ctk.CTkFrame(parent, fg_color="transparent")
        clear_frame.grid(row=5, column=0, columnspan=2, sticky="e", pady=(4, 0))
        ctk.CTkButton(clear_frame, text="Clear Output", width=100, command=self._clear_log).pack()

    def _browse_output(self):
        path = tkinter.filedialog.askdirectory()
        if path:
            self._out_entry.delete(0, "end")
            self._out_entry.insert(0, path)

    # ── ANSI / text processing ─────────────────────────────────────────────────

    _ANSI_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    # Track status: "1/10  +  title" → replace + / > / x with symbols
    _STATUS_RE = re.compile(r'^(\s*\d+/\d+\s+)([+>xX✓✗▶])(\s+)')

    def _process_line(self, line):
        """Strip ANSI, replace status markers, return (text, tag)."""
        line = self._ANSI_RE.sub('', line)

        # Replace tqdm-style carriage return lines (progress bars)
        if '\r' in line:
            line = line.rsplit('\r', 1)[-1]

        m = self._STATUS_RE.match(line)
        if m:
            prefix, marker, space = m.group(1), m.group(2), m.group(3)
            rest = line[m.end():]
            if marker in ('+', '✓'):
                return prefix + '✓' + space + rest, 'success'
            elif marker in ('>', '▶'):
                return prefix + '▶' + space + rest, 'dim'
            elif marker in ('x', 'X', '✗'):
                return prefix + '✗' + space + rest, 'error'

        s = line.strip()
        if s.startswith('===') and s.endswith('==='):
            return line, 'header'
        if s.startswith(('[ERROR]', 'Error', 'Traceback', 'FileNotFoundError',
                         'ModuleNotFoundError', '✗', '[error]')):
            return line, 'error'
        if s.startswith(('[WARNING]', 'Warning', '[warn]')):
            return line, 'warning'
        if s.startswith(('[done]', '[ok]', '✓', '[starting]')):
            return line, 'success' if s.startswith(('[done]', '[ok]', '✓')) else 'dim'
        if s.startswith(('[stopped]', '[skip]')):
            return line, 'gray'
        # Metadata lines (key: value indented)
        if re.match(r'^\s+(Artist|Album|Title|Duration|Quality|Year|Track|Playlist|Number|Release|Platform):', s):
            return line, 'meta'
        return line, None

    def _log_write(self, text):
        self._log.configure(state="normal")
        for line in text.splitlines(keepends=True):
            stripped = line.strip()
            if not stripped:
                if self._log_last_empty:
                    continue   # suppress consecutive blank lines
                self._log_last_empty = True
                self._log.insert("end", line)
            else:
                self._log_last_empty = False
                processed, tag = self._process_line(line)
                if tag:
                    self._log.insert("end", processed, tag)
                else:
                    self._log.insert("end", processed)
        self._log.see("end")
        self._log.configure(state="disabled")

    def _clear_log(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")
        self._log_last_empty = False

    def _start_download(self):
        url = self._url_entry.get().strip()
        if not url:
            self._log_write("[error] Please enter a URL.\n")
            return

        self._download_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._progress.start()
        self._stop_event = threading.Event()

        argv = ["orpheus.py", url]
        out_path = self._out_entry.get().strip()
        if out_path:
            argv += ["-o", out_path]

        self._log_write(f"[starting] {' '.join(argv)}\n")

        output_queue = self._output_queue
        stop_event = self._stop_event

        class _Capture:
            def write(self, text):
                if text:
                    output_queue.put(text)
            def flush(self):
                pass

        def run():
            old_argv   = sys.argv[:]
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            sys.argv   = argv
            capture    = _Capture()
            sys.stdout = capture
            sys.stderr = capture
            try:
                if stop_event.is_set():
                    return
                runpy.run_path(_ORPHEUS_PY, run_name="__main__")
                output_queue.put("\n[done] Download finished.\n")
            except SystemExit as e:
                if e.code not in (None, 0):
                    output_queue.put(f"\n[done] Exited with code {e.code}\n")
                else:
                    output_queue.put("\n[done] Download finished.\n")
            except Exception as e:
                output_queue.put(f"\n[error] {e}\n")
            finally:
                sys.argv   = old_argv
                sys.stdout = old_stdout
                sys.stderr = old_stderr
                output_queue.put(None)  # sentinel

        threading.Thread(target=run, daemon=True).start()
        self._poll_output()

    def _poll_output(self):
        try:
            while True:
                line = self._output_queue.get_nowait()
                if line is None:
                    self._on_download_finished()
                    return
                self._log_write(line)
        except queue.Empty:
            pass
        self.after(100, self._poll_output)

    def _on_download_finished(self):
        self._progress.stop()
        self._progress.set(0)
        self._download_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")

    def _stop_download(self):
        if hasattr(self, "_stop_event"):
            self._stop_event.set()
            self._log_write("\n[stopped] Download cancelled — will stop after current operation.\n")

    # ── Settings Tab ──────────────────────────────────────────────────────────

    def _build_settings_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(parent, label_text="")
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(1, weight=1)

        self._settings_data = load_settings()
        self._settings_vars = {}  # key_path -> tkinter variable
        row = [0]  # mutable counter

        def next_row():
            r = row[0]
            row[0] += 1
            return r

        def section_label(text):
            ctk.CTkLabel(scroll, text=text, font=ctk.CTkFont(size=13, weight="bold"),
                         anchor="w", text_color="#7cb4e8").grid(
                row=next_row(), column=0, columnspan=3, sticky="w", pady=(14, 2), padx=4)

        def divider():
            ctk.CTkFrame(scroll, height=1, fg_color="#3a3a3a").grid(
                row=next_row(), column=0, columnspan=3, sticky="ew", pady=2)

        def add_entry(label, key_path, placeholder=""):
            r = next_row()
            ctk.CTkLabel(scroll, text=label, anchor="w").grid(row=r, column=0, sticky="w", padx=(8, 4), pady=2)
            var = tkinter.StringVar(value=str(self._nested_get(key_path)))
            self._settings_vars[key_path] = var
            entry = ctk.CTkEntry(scroll, textvariable=var, placeholder_text=placeholder)
            entry.grid(row=r, column=1, sticky="ew", padx=4, pady=2)
            return var

        def add_path_entry(label, key_path):
            r = next_row()
            ctk.CTkLabel(scroll, text=label, anchor="w").grid(row=r, column=0, sticky="w", padx=(8, 4), pady=2)
            var = tkinter.StringVar(value=str(self._nested_get(key_path)))
            self._settings_vars[key_path] = var
            entry = ctk.CTkEntry(scroll, textvariable=var)
            entry.grid(row=r, column=1, sticky="ew", padx=4, pady=2)
            def browse(v=var):
                path = tkinter.filedialog.askdirectory()
                if path:
                    v.set(path)
            ctk.CTkButton(scroll, text="Browse", width=60, command=browse).grid(row=r, column=2, padx=(4, 8), pady=2)

        def add_switch(label, key_path):
            r = next_row()
            ctk.CTkLabel(scroll, text=label, anchor="w").grid(row=r, column=0, sticky="w", padx=(8, 4), pady=2)
            var = tkinter.BooleanVar(value=bool(self._nested_get(key_path)))
            self._settings_vars[key_path] = var
            ctk.CTkSwitch(scroll, text="", variable=var, onvalue=True, offvalue=False).grid(
                row=r, column=1, sticky="w", padx=4, pady=2)

        def add_combo(label, key_path, options):
            r = next_row()
            ctk.CTkLabel(scroll, text=label, anchor="w").grid(row=r, column=0, sticky="w", padx=(8, 4), pady=2)
            var = tkinter.StringVar(value=str(self._nested_get(key_path)))
            self._settings_vars[key_path] = var
            ctk.CTkComboBox(scroll, values=options, variable=var).grid(
                row=r, column=1, sticky="w", padx=4, pady=2)

        def add_json_textbox(label, key_path):
            r = next_row()
            ctk.CTkLabel(scroll, text=label, anchor="nw").grid(row=r, column=0, sticky="nw", padx=(8, 4), pady=2)
            value = self._nested_get(key_path)
            text_widget = ctk.CTkTextbox(scroll, height=80)
            text_widget.insert("1.0", json.dumps(value, indent=2))
            text_widget.grid(row=r, column=1, columnspan=2, sticky="ew", padx=4, pady=2)
            self._settings_vars[key_path] = text_widget

        # ── General ───────────────────────────────────────────────────────────
        section_label("General")
        divider()
        add_path_entry("Download Path", ("global", "general", "download_path"))
        add_combo("Download Quality", ("global", "general", "download_quality"), QUALITY_OPTIONS)
        add_entry("Search Limit", ("global", "general", "search_limit"))

        # ── Artist Downloading ────────────────────────────────────────────────
        section_label("Artist Downloading")
        divider()
        add_switch("Return Credited Albums", ("global", "artist_downloading", "return_credited_albums"))
        add_switch("Skip Already Downloaded (Separate)", ("global", "artist_downloading", "separate_tracks_skip_downloaded"))

        # ── Formatting ────────────────────────────────────────────────────────
        section_label("Formatting")
        divider()
        add_entry("Album Format", ("global", "formatting", "album_format"), "{name}{explicit}")
        add_entry("Playlist Format", ("global", "formatting", "playlist_format"), "{name}{explicit}")
        add_entry("Track Filename Format", ("global", "formatting", "track_filename_format"), "{album_artist} - {name}")
        add_entry("Single Full Path Format", ("global", "formatting", "single_full_path_format"), "{artist} - {name}")
        add_switch("Enable Zero-Fill (Track Numbers)", ("global", "formatting", "enable_zfill"))
        add_switch("Force Album Format", ("global", "formatting", "force_album_format"))

        # ── Codecs ────────────────────────────────────────────────────────────
        section_label("Codecs")
        divider()
        add_switch("Proprietary Codecs", ("global", "codecs", "proprietary_codecs"))
        add_switch("Spatial Codecs", ("global", "codecs", "spatial_codecs"))

        # ── Module Defaults ───────────────────────────────────────────────────
        section_label("Module Defaults")
        divider()
        add_entry("Lyrics Module", ("global", "module_defaults", "lyrics"), "default")
        add_entry("Covers Module", ("global", "module_defaults", "covers"), "default")
        add_entry("Credits Module", ("global", "module_defaults", "credits"), "default")

        # ── Lyrics ────────────────────────────────────────────────────────────
        section_label("Lyrics")
        divider()
        add_switch("Embed Lyrics", ("global", "lyrics", "embed_lyrics"))
        add_switch("Embed Synced Lyrics", ("global", "lyrics", "embed_synced_lyrics"))
        add_switch("Save Synced Lyrics (.lrc)", ("global", "lyrics", "save_synced_lyrics"))

        # ── Covers ────────────────────────────────────────────────────────────
        section_label("Covers")
        divider()
        add_switch("Embed Cover", ("global", "covers", "embed_cover"))
        add_combo("Main Compression", ("global", "covers", "main_compression"), COMPRESSION_OPTIONS)
        add_entry("Main Resolution", ("global", "covers", "main_resolution"))
        add_switch("Save External Cover", ("global", "covers", "save_external"))
        add_combo("External Format", ("global", "covers", "external_format"), EXTERNAL_FORMAT_OPTIONS)
        add_combo("External Compression", ("global", "covers", "external_compression"), COMPRESSION_OPTIONS)
        add_entry("External Resolution", ("global", "covers", "external_resolution"))
        add_switch("Save Animated Cover", ("global", "covers", "save_animated_cover"))

        # ── Playlist ──────────────────────────────────────────────────────────
        section_label("Playlist")
        divider()
        add_switch("Save M3U", ("global", "playlist", "save_m3u"))
        add_combo("M3U Paths", ("global", "playlist", "paths_m3u"), M3U_PATH_OPTIONS)
        add_switch("Extended M3U", ("global", "playlist", "extended_m3u"))

        # ── Advanced ──────────────────────────────────────────────────────────
        section_label("Advanced")
        divider()
        add_switch("Advanced Login System", ("global", "advanced", "advanced_login_system"))
        add_switch("Keep Original After Conversion", ("global", "advanced", "conversion_keep_original"))
        add_entry("Cover Variance Threshold", ("global", "advanced", "cover_variance_threshold"))
        add_switch("Debug Mode", ("global", "advanced", "debug_mode"))
        add_switch("Disable Subscription Checks", ("global", "advanced", "disable_subscription_checks"))
        add_switch("Enable Undesirable Conversions", ("global", "advanced", "enable_undesirable_conversions"))
        add_switch("Ignore Existing Files", ("global", "advanced", "ignore_existing_files"))
        add_switch("Ignore Different Artists", ("global", "advanced", "ignore_different_artists"))
        add_json_textbox("Codec Conversions (JSON)", ("global", "advanced", "codec_conversions"))
        add_json_textbox("Conversion Flags (JSON)", ("global", "advanced", "conversion_flags"))

        # ── Modules ───────────────────────────────────────────────────────────
        modules = self._settings_data.get("modules", {})
        if modules:
            section_label("Modules")
            divider()
            for module_name, module_cfg in modules.items():
                ctk.CTkLabel(scroll, text=f"[{module_name}]", anchor="w",
                             font=ctk.CTkFont(size=12, weight="bold")).grid(
                    row=next_row(), column=0, columnspan=3, sticky="w", padx=(8, 4), pady=(8, 2))
                for key, value in module_cfg.items():
                    r = next_row()
                    ctk.CTkLabel(scroll, text=f"  {key}", anchor="w").grid(
                        row=r, column=0, sticky="w", padx=(16, 4), pady=2)
                    var = tkinter.StringVar(value=str(value))
                    self._settings_vars[("modules", module_name, key)] = var
                    entry = ctk.CTkEntry(scroll, textvariable=var,
                                        show="*" if "password" in key.lower() else "")
                    entry.grid(row=r, column=1, sticky="ew", padx=4, pady=2)

        # ── Save button ───────────────────────────────────────────────────────
        save_row = next_row()
        ctk.CTkFrame(scroll, height=1, fg_color="#3a3a3a").grid(
            row=save_row, column=0, columnspan=3, sticky="ew", pady=(16, 4))
        ctk.CTkButton(scroll, text="Save Settings", width=140, command=self._save_settings).grid(
            row=next_row(), column=0, columnspan=3, pady=(4, 16))

    # ── Settings helpers ──────────────────────────────────────────────────────

    def _nested_get(self, key_path):
        obj = self._settings_data
        for k in key_path:
            if isinstance(obj, dict) and k in obj:
                obj = obj[k]
            else:
                return ""
        return obj

    def _nested_set(self, key_path, value):
        obj = self._settings_data
        for k in key_path[:-1]:
            obj = obj[k]
        obj[key_path[-1]] = value

    def _save_settings(self):
        for key_path, var in self._settings_vars.items():
            # CTkTextbox — parse as JSON
            if isinstance(var, ctk.CTkTextbox):
                raw = var.get("1.0", "end").strip()
                try:
                    value = json.loads(raw)
                except json.JSONDecodeError:
                    self._show_error(f"Invalid JSON for {' > '.join(str(k) for k in key_path)}")
                    return
                self._nested_set(key_path, value)
                continue

            raw = var.get()

            # Determine target type from existing value
            existing = self._nested_get(key_path)
            if isinstance(existing, bool) or isinstance(var, tkinter.BooleanVar):
                self._nested_set(key_path, bool(var.get()))
            elif isinstance(existing, int):
                try:
                    self._nested_set(key_path, int(raw))
                except ValueError:
                    self._show_error(f"Expected integer for {' > '.join(str(k) for k in key_path)}")
                    return
            elif isinstance(existing, float):
                try:
                    self._nested_set(key_path, float(raw))
                except ValueError:
                    self._show_error(f"Expected number for {' > '.join(str(k) for k in key_path)}")
                    return
            else:
                self._nested_set(key_path, raw)

        save_settings(self._settings_data)
        self._show_info("Settings saved.")

    def _show_error(self, message):
        win = ctk.CTkToplevel(self)
        win.title("Error")
        win.geometry("360x120")
        win.grab_set()
        ctk.CTkLabel(win, text=message, wraplength=320).pack(pady=20)
        ctk.CTkButton(win, text="OK", command=win.destroy).pack()

    def _show_info(self, message):
        win = ctk.CTkToplevel(self)
        win.title("Info")
        win.geometry("280x100")
        win.grab_set()
        ctk.CTkLabel(win, text=message).pack(pady=20)
        ctk.CTkButton(win, text="OK", command=win.destroy).pack()

    # ── Updates Tab ───────────────────────────────────────────────────────────

    def _build_updates_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)

        # Version info row
        info_frame = ctk.CTkFrame(parent, fg_color="transparent")
        info_frame.grid(row=0, column=0, sticky="ew", pady=(12, 4), padx=8)
        info_frame.grid_columnconfigure(1, weight=1)
        info_frame.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(info_frame, text="Current version:", anchor="w").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self._upd_current_lbl = ctk.CTkLabel(info_frame, text=__version__, anchor="w",
                                              font=ctk.CTkFont(weight="bold"))
        self._upd_current_lbl.grid(row=0, column=1, sticky="w")

        ctk.CTkLabel(info_frame, text="Latest version:", anchor="w").grid(row=0, column=2, sticky="w", padx=(20, 6))
        self._upd_latest_lbl = ctk.CTkLabel(info_frame, text="—", anchor="w",
                                             font=ctk.CTkFont(weight="bold"))
        self._upd_latest_lbl.grid(row=0, column=3, sticky="w")

        # Status label
        self._upd_status_lbl = ctk.CTkLabel(parent, text="", anchor="w", text_color="#8b949e")
        self._upd_status_lbl.grid(row=1, column=0, sticky="w", padx=8, pady=(0, 4))

        # Release notes
        ctk.CTkLabel(parent, text="Release notes:", anchor="w").grid(row=2, column=0, sticky="w", padx=8, pady=(4, 2))
        self._upd_notes = ctk.CTkTextbox(parent, height=220, state="disabled")
        self._upd_notes.grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 8))

        # Progress bar (hidden until download starts)
        self._upd_progress = ctk.CTkProgressBar(parent)
        self._upd_progress.set(0)
        self._upd_progress.grid(row=4, column=0, sticky="ew", padx=8, pady=(0, 6))
        self._upd_progress.grid_remove()

        # Buttons
        btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_frame.grid(row=5, column=0, sticky="w", padx=8, pady=(4, 12))

        self._upd_check_btn = ctk.CTkButton(btn_frame, text="Check for Updates",
                                             width=160, command=self._check_updates)
        self._upd_check_btn.pack(side="left", padx=(0, 10))

        self._upd_install_btn = ctk.CTkButton(btn_frame, text="Download & Install",
                                               width=160, state="disabled",
                                               command=self._download_and_install)
        self._upd_install_btn.pack(side="left")

        self._upd_asset_url = None   # filled by _check_updates
        self._upd_asset_name = None

    def _check_updates(self):
        self._upd_check_btn.configure(state="disabled")
        self._upd_status_lbl.configure(text="Checking…", text_color="#8b949e")
        self._upd_install_btn.configure(state="disabled")
        self._upd_asset_url = None
        self._upd_asset_name = None

        def worker():
            try:
                req = urllib.request.Request(
                    _GH_API_LATEST,
                    headers={"Accept": "application/vnd.github+json",
                             "User-Agent": f"OrpheusDL/{__version__}"},
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode())

                tag = data.get("tag_name", "")
                latest = tag.lstrip("v")
                notes = data.get("body", "") or ""
                assets = data.get("assets", [])

                # Pick platform-appropriate asset
                asset_url = None
                asset_name = None
                if sys.platform == "win32":
                    for a in assets:
                        if a["name"].endswith(".exe"):
                            asset_url = a["browser_download_url"]
                            asset_name = a["name"]
                            break
                else:
                    # Prefer AppImage, fall back to deb
                    for a in assets:
                        if a["name"].endswith(".AppImage"):
                            asset_url = a["browser_download_url"]
                            asset_name = a["name"]
                            break
                    if not asset_url:
                        for a in assets:
                            if a["name"].endswith(".deb"):
                                asset_url = a["browser_download_url"]
                                asset_name = a["name"]
                                break

                self.after(0, lambda: self._on_check_done(latest, notes, asset_url, asset_name))
            except Exception as exc:
                self.after(0, lambda: self._on_check_error(str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_check_done(self, latest, notes, asset_url, asset_name):
        self._upd_check_btn.configure(state="normal")
        self._upd_latest_lbl.configure(text=latest if latest else "unknown")

        self._upd_notes.configure(state="normal")
        self._upd_notes.delete("1.0", "end")
        self._upd_notes.insert("1.0", notes or "(no release notes)")
        self._upd_notes.configure(state="disabled")

        try:
            is_newer = latest and parse_version(latest) > parse_version(__version__)
        except Exception:
            is_newer = False

        if is_newer:
            self._upd_status_lbl.configure(
                text=f"Update available: {latest}", text_color="#3fb950")
            if asset_url:
                self._upd_asset_url = asset_url
                self._upd_asset_name = asset_name
                self._upd_install_btn.configure(state="normal")
            else:
                self._upd_status_lbl.configure(
                    text=f"Update available ({latest}) — no binary asset found for this platform.",
                    text_color="#d29922")
        else:
            self._upd_status_lbl.configure(
                text="You are up to date.", text_color="#3fb950")

    def _on_check_error(self, msg):
        self._upd_check_btn.configure(state="normal")
        self._upd_status_lbl.configure(text=f"Check failed: {msg}", text_color="#f85149")

    def _download_and_install(self):
        if not self._upd_asset_url:
            return

        self._upd_install_btn.configure(state="disabled")
        self._upd_check_btn.configure(state="disabled")
        self._upd_status_lbl.configure(text="Downloading…", text_color="#8b949e")
        self._upd_progress.set(0)
        self._upd_progress.grid()

        asset_url = self._upd_asset_url
        asset_name = self._upd_asset_name or "update"

        def worker():
            try:
                tmp_dir = tempfile.mkdtemp(prefix="orpheusdl_update_")
                dest = os.path.join(tmp_dir, asset_name)

                def reporthook(count, block_size, total_size):
                    if total_size > 0:
                        frac = min(count * block_size / total_size, 1.0)
                        self.after(0, lambda f=frac: self._upd_progress.set(f))

                urllib.request.urlretrieve(asset_url, dest, reporthook=reporthook)
                self.after(0, lambda: self._upd_progress.set(1.0))
                self.after(0, lambda: self._run_installer(dest))
            except Exception as exc:
                self.after(0, lambda: self._on_install_error(str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _run_installer(self, path):
        self._upd_status_lbl.configure(text="Launching installer…", text_color="#8b949e")
        try:
            if sys.platform == "win32":
                subprocess.Popen([path, "/SILENT"])
                self.after(1500, sys.exit)
            elif path.endswith(".AppImage"):
                os.chmod(path, 0o755)
                # Replace current AppImage if running as one, otherwise just open
                current = os.environ.get("APPIMAGE", "")
                if current and os.path.isfile(current):
                    shutil.copy2(path, current)
                    os.chmod(current, 0o755)
                    self._upd_status_lbl.configure(
                        text="Updated. Restart the app to use the new version.", text_color="#3fb950")
                else:
                    subprocess.Popen([path])
                    self.after(1500, sys.exit)
            elif path.endswith(".deb"):
                subprocess.Popen(["pkexec", "dpkg", "-i", path])
                self._upd_status_lbl.configure(
                    text="Installer launched. Restart the app after installation.", text_color="#3fb950")
            else:
                self._upd_status_lbl.configure(
                    text=f"Downloaded to {path} — install manually.", text_color="#d29922")
        except Exception as exc:
            self._on_install_error(str(exc))
        finally:
            self._upd_check_btn.configure(state="normal")

    def _on_install_error(self, msg):
        self._upd_check_btn.configure(state="normal")
        self._upd_install_btn.configure(state="normal")
        self._upd_progress.grid_remove()
        self._upd_status_lbl.configure(text=f"Install failed: {msg}", text_color="#f85149")


if __name__ == "__main__":
    app = App()
    app.mainloop()
