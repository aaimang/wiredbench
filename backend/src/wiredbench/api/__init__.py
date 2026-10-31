"""API routers. The app includes exactly this list, and the security tests walk the same list."""

from wiredbench.api import assets, auth, catalog, engine, system, workspace

ROUTERS = (system.router, auth.router, catalog.router, workspace.router, assets.router, engine.router)
