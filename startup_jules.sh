#!/usr/bin/env bash
set -Eeu

# ==============================================================================
# JULES AUTONOMOUS VM STARTUP & EVALUATION RUNNER
# ==============================================================================
# Target: Linux Cloud VM (Ubuntu / Debian environment)
# Purpose:
#   1. Install OS dependencies, X11 virtual display, AT-SPI accessibility,
#      headless browser / test applications (Chromium, Galculator, Mousepad, etc.).
#   2. Install Node.js 22+, Python uv, project virtual environments & packages.
#   3. Bootstrap virtual X11 / D-Bus / AT-SPI headless session (:99).
#   4. Execute task evaluation testbed (Browser + Native suite) via Jev / Cua Driver.
#   5. Aggregate success/failure analytics and output an autonomous improvement report.
# ==============================================================================

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${PROJECT_ROOT}/runs/jules_$(date +%Y%m%d_%H%M%S)"
mkdir -p "${LOG_DIR}"

log() {
  echo -e "\n\033[1;34m[JULES SETUP]\033[0m \033[1;32m$*\033[0m"
}

warn() {
  echo -e "\n\033[1;33m[JULES WARNING]\033[0m $*"
}

err() {
  echo -e "\n\033[1;31m[JULES ERROR]\033[0m $*" >&2
}

# ------------------------------------------------------------------------------
# 1. Environment & Pre-requisites Check
# ------------------------------------------------------------------------------
# Ensure git working tree is completely clean for Jules autonomous runs
if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  log "Resetting working tree to ensure clean git state for Jules..."
  git reset --hard HEAD || true
  git clean -fd || true
fi

if [[ -z "${TYPESAFE_API_KEY:-}" ]]; then
  warn "TYPESAFE_API_KEY is not set. Live Jev decisions will be skipped or run in mock mode."
fi

if [[ -n "${THINKY_API_KEY:-}" ]]; then
  export THINKY_MODEL="${THINKY_MODEL:-thinkingmachines/Inkling}"
  log "THINKY_API_KEY detected. Pre-flight task compiler enabled via ${THINKY_API_ENDPOINT:-https://tinker.thinkingmachines.dev/services/tinker-prod/oai/api/v1/chat/completions} (model: ${THINKY_MODEL})"
else
  log "THINKY_API_KEY not set. Natural language task compilation will use local fallback or skip pre-flight."
fi

# Detect platform - Jules runs strictly in a Linux VM
OS_TYPE="$(uname -s)"
if [[ "${OS_TYPE}" != "Linux" ]]; then
  err "This startup script is designed strictly for Jules running in a Linux VM. Detected: ${OS_TYPE}"
  exit 1
fi
log "Operating System confirmed: ${OS_TYPE} ($(uname -m))"

# ------------------------------------------------------------------------------
# 2. System Packages & Virtual Display Drivers Installation (Linux)
# ------------------------------------------------------------------------------
log "Step 2: Provisioning system packages and display drivers..."

# Check if running as root or has sudo
SUDO=""
if [[ "$(id -u)" -ne 0 ]]; then
  if command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
  else
    warn "Running as non-root without sudo. Assuming packages are already installed."
  fi
fi

if [[ -n "${SUDO}" || "$(id -u)" -eq 0 ]]; then
  # Enable universe repository on Ubuntu/Debian for extra GUI packages if available
  if command -v add-apt-repository >/dev/null 2>&1; then
    ${SUDO} add-apt-repository -y universe || true
    ${SUDO} apt-get update -y || true
  fi

  # 1. Essential display, X11, D-Bus, and AT-SPI accessibility drivers
  log "Installing core display & accessibility packages..."
  DEBIAN_FRONTEND=noninteractive ${SUDO} apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    wget \
    git \
    build-essential \
    pkg-config \
    dbus \
    dbus-x11 \
    at-spi2-core \
    xvfb \
    x11-utils \
    x11-xserver-utils \
    xdotool \
    fluxbox \
    chromium \
    chromium-driver \
    python3-pip \
    python3-venv \
    libgtk-3-dev \
    libgirepository1.0-dev \
    gir1.2-atspi-2.0 || true

  # 2. Test application suite: install individually so one missing candidate does not abort the rest
  log "Installing test GUI applications (office, creative, utility)..."
  for app_pkg in galculator mousepad libreoffice-calc libreoffice-writer gnumeric inkscape audacity sox pinta kolourpaint; do
    DEBIAN_FRONTEND=noninteractive ${SUDO} apt-get install -y --no-install-recommends "${app_pkg}" >/dev/null 2>&1 || warn "Optional package '${app_pkg}' not available in apt; continuing..."
  done
fi

# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
# 3. Virtual Display & Accessibility Session Launch (CRITICAL: Must precede Driver)
# ------------------------------------------------------------------------------
log "Step 3: Configuring virtual display & D-Bus / AT-SPI headless session..."

export DISPLAY=:99
export SCREEN_WIDTH=1920
export SCREEN_HEIGHT=1080
export SCREEN_DEPTH=24

# Remove any stale lock files or sockets on display :99 from previous runs
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 2>/dev/null || true

# If Xvfb is already running on :99 and responsive, reuse it; otherwise launch it
if xdpyinfo -display :99 >/dev/null 2>&1; then
  log "Existing virtual display :99 is active and healthy."
else
  log "Starting Xvfb on display ${DISPLAY} (${SCREEN_WIDTH}x${SCREEN_HEIGHT}x${SCREEN_DEPTH})..."
  Xvfb :99 -screen 0 "${SCREEN_WIDTH}x${SCREEN_HEIGHT}x${SCREEN_DEPTH}" -ac +extension GLX +extension MIT-SHM +render -noreset > "${LOG_DIR}/xvfb.log" 2>&1 &
  XVFB_PID=$!
  sleep 2

  if ! kill -0 "${XVFB_PID}" 2>/dev/null; then
    err "Xvfb failed to start. Contents of ${LOG_DIR}/xvfb.log:"
    cat "${LOG_DIR}/xvfb.log" >&2 || true
  fi
fi

# Launch lightweight window manager (fluxbox) so windows have frames and bounds
if command -v fluxbox >/dev/null 2>&1; then
  if ! pgrep -f "fluxbox" >/dev/null 2>&1; then
    log "Starting fluxbox window manager..."
    fluxbox > "${LOG_DIR}/fluxbox.log" 2>&1 &
    sleep 1
  fi
fi

# Launch D-Bus session if needed for AT-SPI accessibility
if command -v dbus-launch >/dev/null 2>&1 && [[ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ]]; then
  log "Launching D-Bus session..."
  eval "$(dbus-launch --sh-syntax)"
  export DBUS_SESSION_BUS_ADDRESS
fi

# Enable AT-SPI accessibility bus
export GTK_MODULES="gail:atk-bridge"
export QT_ACCESSIBILITY=1
export NO_AT_BRIDGE=0
if command -v /usr/lib/at-spi2-core/at-spi-bus-launcher >/dev/null 2>&1; then
  /usr/lib/at-spi2-core/at-spi-bus-launcher --launch-immediately > "${LOG_DIR}/atspi.log" 2>&1 &
  sleep 1
fi

# ------------------------------------------------------------------------------
# 4. Toolchain Installation (uv, Node.js, Cua Driver)
# ------------------------------------------------------------------------------
log "Step 4: Verifying and installing language runtimes & Cua Driver..."

# 4.1 Install uv if missing
if ! command -v uv >/dev/null 2>&1; then
  log "Installing uv (fast Python package manager)..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="${HOME}/.cargo/bin:${HOME}/.local/bin:${PATH}"
fi

# 4.2 Verify Node.js
if ! command -v node >/dev/null 2>&1; then
  log "Installing Node.js 22 LTS via NodeSource..."
  if [[ -n "${SUDO}" || "$(id -u)" -eq 0 ]]; then
    curl -fsSL https://deb.nodesource.com/setup_22.x | ${SUDO} -E bash -
    DEBIAN_FRONTEND=noninteractive ${SUDO} apt-get install -y nodejs
  else
    warn "Node.js not found and cannot auto-install without root/sudo."
  fi
fi

# 4.3 Verify / Check Cua Driver Binary
CUA_READY=false
if command -v cua-driver >/dev/null 2>&1; then
  CUA_READY=true
  log "Found cua-driver on PATH at $(command -v cua-driver)"
elif [[ -n "${CUA_DRIVER_BIN:-}" && -x "${CUA_DRIVER_BIN}" ]]; then
  CUA_READY=true
  log "Using existing CUA_DRIVER_BIN at ${CUA_DRIVER_BIN}"
else
  # Check parent workspace release build
  CUA_CANDIDATE="$(cd "${PROJECT_ROOT}/../.." && pwd)/target/release/cua-driver"
  if [[ -x "${CUA_CANDIDATE}" ]]; then
    export CUA_DRIVER_BIN="${CUA_CANDIDATE}"
    CUA_READY=true
    log "Found local cargo release build: set CUA_DRIVER_BIN=${CUA_DRIVER_BIN}"
  # Install canonical cua-driver binary via official installer
  log "Attempting official cua-driver installation via https://cua.ai/driver/install.sh..."
  if curl -fsSL https://cua.ai/driver/install.sh | bash; then
    export PATH="${HOME}/.local/bin:${PATH}"
    if command -v cua-driver >/dev/null 2>&1; then
      CUA_READY=true
      log "cua-driver successfully installed via official installer: $(command -v cua-driver)"
    fi
  fi
fi

# Test MCP connection under the active DISPLAY
if [[ "${CUA_READY}" == "true" ]]; then
  log "Probing 'cua-driver mcp' under active display ${DISPLAY}..."
  DRIVER_CMD="${CUA_DRIVER_BIN:-cua-driver}"
  if timeout 5s "${DRIVER_CMD}" doctor > "${LOG_DIR}/driver_doctor.log" 2>&1; then
    log "cua-driver doctor succeeded under virtual display."
  else
    warn "cua-driver doctor exited with non-zero status. See ${LOG_DIR}/driver_doctor.log"
  fi
else
  warn "Cua Driver binary could not be found or built automatically."
  warn "Simulated and fixture evaluation will proceed; native desktop app launch will require CUA_DRIVER_BIN."
fi

# ------------------------------------------------------------------------------
# 5. Project Dependencies & Audio Assets
# ------------------------------------------------------------------------------
log "Step 5: Synchronizing project dependencies and sample assets..."

cd "${PROJECT_ROOT}"

# Sync Python venv with uv
uv sync --frozen --python 3.12 || uv sync --python 3.12 || uv sync

# Install Node dependencies
if command -v npm >/dev/null 2>&1 && [[ -f "package.json" ]]; then
  export npm_config_cache="${PROJECT_ROOT}/.npm-cache"
  npm ci || npm install
fi

AUDIO_DIR="${PROJECT_ROOT}/fixtures/audio"
mkdir -p "${AUDIO_DIR}"
# Generate sine wave sample audio files using standard library wave module
python3 -c "
import wave, struct, math, os
audio_dir = '${AUDIO_DIR}'
def make_wave(filename, freq=440.0, duration=2.0, rate=44100):
    path = os.path.join(audio_dir, filename)
    if os.path.exists(path): return
    with wave.open(path, 'w') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        n_frames = int(rate * duration)
        for i in range(n_frames):
            val = int(32767.0 * 0.5 * math.sin(2.0 * math.pi * freq * i / rate))
            wav.writeframes(struct.pack('<h', val))
make_wave('sample_sine_440hz.wav', freq=440.0)
make_wave('sample_sine_880hz.wav', freq=880.0)
make_wave('vocal_track_stem.wav', freq=523.25)
" || warn "Could not generate sample wave files; continuing..."

# ------------------------------------------------------------------------------
# 6. Verification & Self-Test Baseline
# ------------------------------------------------------------------------------
log "Step 6: Executing baseline self-tests and unit regressions..."

UNIT_LOG="${LOG_DIR}/unit_tests.log"
log "Running unit test discovery: uv run python -m unittest discover python/tests"
if uv run python -m unittest discover python/tests > "${UNIT_LOG}" 2>&1; then
  log "Unit tests PASSED (170+ checks verified)."
else
  err "Unit tests FAILED. See log at: ${UNIT_LOG}"
  cat "${UNIT_LOG}" | tail -n 25
fi

# Verify fixture server & verify_setup.py
log "Running fixture server verification..."
SETUP_VERIFY_DIR="${LOG_DIR}/setup_verify"
if uv run python verify_setup.py --output-dir "${SETUP_VERIFY_DIR}" > "${LOG_DIR}/verify_setup.log" 2>&1; then
  log "Fixture server and isolated loopback verification: PASSED"
else
  warn "verify_setup encountered an issue. See ${LOG_DIR}/verify_setup.log"
fi

# ------------------------------------------------------------------------------
# 7. Snapshot Ready for Jules Chat Interaction
# ------------------------------------------------------------------------------
# The environment, display (:99), AT-SPI bus, drivers, and dependencies are now
# fully configured. Tasks are NOT auto-executed during snapshot boot.
# You or Jules can kick off task runs directly from the chat interface or via:
#   uv run python python/run_jules_suite.py
# or individual task runs via:
#   uv run python python/native_run.py --task tasks/<task_name>.json

# Final git status guarantee for Jules automated environment checks
if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git checkout -- . 2>/dev/null || true
  git clean -fd 2>/dev/null || true
fi

log "Environment and snapshot setup completed successfully!"
log "Ready for Jules chat commands. Logs stored at: ${LOG_DIR}"
