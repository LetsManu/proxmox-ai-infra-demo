from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import init_db, session_scope
from .models import VirtualMachine
from .routes import ai, plans, platform, promotion, validation, vms
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
                               windows=os_family_for(vm.spec.get("template", "")) == "windows")
    log.warning("Starting in %s mode", "LIVE" if settings.live_mode else "MOCK")
    yield


app = FastAPI(title="Proxmox AI Infra Console API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

for r in (vms.router, plans.router, validation.router, promotion.router, platform.router, ai.router):
    app.include_router(r)
