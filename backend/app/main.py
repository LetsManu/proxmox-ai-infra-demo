from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .auth import auth_enabled, auth_middleware
from .config import get_settings
from .database import init_db, session_scope
from .models import VirtualMachine
from .routes import ai, auth, plans, platform, promotion, proposals, stacks, validation, vms
from .services.proxmox_service import MockProxmox, get_proxmox
from .services.template_service import os_family_for
from .workers.job_runner import recover_interrupted_jobs

log = logging.getLogger("proxmox-ai-infra")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    init_db()
    recover_interrupted_jobs()
    px = get_proxmox(settings)
    if isinstance(px, MockProxmox):
        # Rehydrate the simulated cluster from the database after a restart.
        with session_scope() as db:
            for vm in db.query(VirtualMachine).all():
                px.register_vm(vm.vmid, vm.name, vm.environment,
                               windows=os_family_for(vm.spec.get("template", "")) == "windows",
                               kind=vm.spec.get("kind", "vm"))
    log.warning("Starting %s in %s mode", __version__, "LIVE" if settings.live_mode else "MOCK")
    if not auth_enabled(settings):
        log.warning("AUTH_MODE=none: no sign-in, everyone has every role. Use only on localhost; "
                    "set AUTH_MODE=oidc or ldap for shared use (docs/authentication.md).")
    yield


app = FastAPI(title="Proxmox AI Infra Console API", version=__version__, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)
app.middleware("http")(auth_middleware)

for r in (auth.router, vms.router, plans.router, validation.router, promotion.router, platform.router, proposals.router,
          stacks.router, ai.router):
    app.include_router(r)
