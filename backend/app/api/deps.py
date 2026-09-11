"""FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.config import Settings, get_settings
from app.k8s.client import Capabilities, KubeClients, get_clients, probe_capabilities

SettingsDep = Annotated[Settings, Depends(get_settings)]
ClientsDep = Annotated[KubeClients, Depends(get_clients)]
CapabilitiesDep = Annotated[Capabilities, Depends(probe_capabilities)]
