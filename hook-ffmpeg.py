# PyInstaller runtime hook for ffmpeg-python
# Pre-imports ffmpeg submodules in the correct order to avoid circular imports
import sys

try:
    import ffmpeg.nodes as _nodes
    sys.modules['ffmpeg.nodes'] = _nodes
    import ffmpeg
except Exception:
    pass
