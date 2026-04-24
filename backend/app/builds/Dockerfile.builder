# Builder image for cross-compiling Windows .exe from Linux hosts.
#
# Based on tobix/pywine (Wine + Windows Python). We install PyInstaller, UPX,
# and the agent's runtime requirements so each build is cache-warm. The agent
# source itself is mounted at /build at run time and is NOT baked in.
#
# Build:
#   docker build -t rmm-builder:latest -f Dockerfile.builder .
#
# Run (normally invoked by PyInstallerWorker, not by hand):
#   docker run --rm -v /path/to/staged/workdir:/build -w /build rmm-builder:latest \
#     pyinstaller --clean --noconfirm rmm-agent.spec

FROM tobix/pywine:3.12

# UPX for --upx compression. tobix/pywine is Debian-based.
RUN apt-get update && apt-get install -y --no-install-recommends upx-ucl \
    && rm -rf /var/lib/apt/lists/*

# Install PyInstaller + agent runtime deps into the Windows Python.
# The `wine` prefix runs Windows Python; `pip` inside resolves Windows wheels.
# We pre-install runtime deps so `pyinstaller` can analyze them without a network
# call at build time — important for an air-gapped / reproducible build worker.
RUN wine pip install --no-cache-dir \
        pyinstaller==6.10.0 \
        psutil==6.0.0 \
        websockets==13.1 \
        httpx==0.27.2

# `pyinstaller` in PATH should invoke Wine's PyInstaller transparently via the
# base image's entrypoint shim. Verify the install.
RUN wine pyinstaller --version

WORKDIR /build
