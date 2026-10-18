import os
import sys
import tempfile

# Configure before any `app` import: mock mode, throwaway DB and workspace, fast mock jobs.
_tmp = tempfile.mkdtemp(prefix="pxai-test-")
os.environ.update({
    "LIVE_MODE": "false",
    "DATABASE_URL": f"sqlite:///{_tmp}/test.db",
    "WORKSPACE_DIR": f"{_tmp}/ws",
    "MOCK_SPEED": "50",
    "AI_PROVIDER": "none",
    "ANTHROPIC_API_KEY": "",
})
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
