"""Run the Revelator API server."""

import os
import uvicorn

if __name__ == "__main__":
    # PORT is overridable so we can dodge whatever already holds :8000 on this
    # laptop. When hosting revelator.site the named tunnel points at this port.
    port = int(os.environ.get("PORT", "8000"))
    reload = os.environ.get("RELOAD", "1") != "0"
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=reload)
