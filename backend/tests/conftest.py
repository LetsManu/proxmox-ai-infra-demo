import os
import sys
import tempfile

# Configure before any `app` import: mock mode, throwaway DB and workspace, fast mock jobs.
_tmp = tempfile.mkdtemp(prefix="pxai-test-")
_repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.update({
    "LIVE_MODE": "false",
    "DATABASE_URL": f"sqlite:///{_tmp}/test.db",
    "WORKSPACE_DIR": f"{_tmp}/ws",
    "MOCK_SPEED": "50",
    "AI_PROVIDER": "none",
    "ANTHROPIC_API_KEY": "",
    "UBUNTU_2404_IMAGE_URL": "https://images.example.invalid/noble-server-cloudimg-amd64.img",
    "DEBIAN_12_IMAGE_URL": "https://images.example.invalid/debian-12-genericcloud-amd64.qcow2",
    "DEBIAN_12_CT_URL": "https://templates.example.invalid/system/debian-12-standard_12.7-1_amd64.tar.zst",
    "UBUNTU_2404_CT_URL": "https://templates.example.invalid/system/ubuntu-24.04-standard_24.04-2_amd64.tar.zst",
    "ANSIBLE_DIR": os.path.join(_repo, "infra", "ansible"),
    "EXTRA_PROFILE_DIRS": os.path.join(_repo, "profiles"),
    "PACKAGE_DENYLIST": "telnetd",
})
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import init_db  # noqa: E402

init_db()  # unit tests that call services directly need the tables too
