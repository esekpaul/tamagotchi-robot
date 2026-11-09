#!/usr/bin/env bash
# =============================================================================
set -Eeuo pipefail

ROS_DISTRO=jazzy
DEFAULT_WS="$HOME/ros2_ws"
DEFAULT_DOMAIN_ID=0
LOG_FILE="$HOME/ros2_setup.log"
BASHRC="$HOME/.bashrc"
MARK_BEGIN="# >>> ROS2 student setup >>>"
MARK_END="# <<< ROS2 student setup <<<"
MIN_DISK_GB=15
ASSUME_YES=0

for arg in "$@"; do
  case "$arg" in
    -y|--yes) ASSUME_YES=1 ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg"; exit 1 ;;
  esac
done

# ----------------------------------------------------------------- output ----
if [ -t 1 ]; then
  C_BLUE=$'\e[1;34m'; C_GREEN=$'\e[1;32m'; C_YELLOW=$'\e[1;33m'; C_RED=$'\e[1;31m'; C_OFF=$'\e[0m'
else
  C_BLUE=""; C_GREEN=""; C_YELLOW=""; C_RED=""; C_OFF=""
fi
STEP_NUM=0
STEP_TOTAL=9
CURRENT_STEP="start"

step() { STEP_NUM=$((STEP_NUM + 1)); CURRENT_STEP="$*"; echo; echo "${C_BLUE}==> [${STEP_NUM}/${STEP_TOTAL}] $*${C_OFF}"; }
info() { echo "    $*"; }
ok()   { echo "${C_GREEN}    OK: $*${C_OFF}"; }
warn() { echo "${C_YELLOW}    WARNING: $*${C_OFF}"; }
die()  { echo "${C_RED}ERROR: $*${C_OFF}" >&2; exit 1; }

on_error() {
  local code=$?
  echo
  echo "${C_RED}=====================================================================${C_OFF}"
  echo "${C_RED} Installation FAILED during step: ${CURRENT_STEP}${C_OFF}"
  echo "${C_RED} (exit code ${code}, line ${BASH_LINENO[0]})${C_OFF}"
  echo
  echo " What to do:"
  echo "   1. Check your internet connection."
  echo "   2. Run the script again - it is safe to re-run:  bash $0"
  echo "   3. If it still fails, send this file to your teacher: ${LOG_FILE}"
  echo "${C_RED}=====================================================================${C_OFF}"
  exit "$code"
}
trap on_error ERR

# Everything also goes into the log file.
exec > >(tee -a "$LOG_FILE") 2>&1
echo "----- $(date) : setup_ros2_jazzy.sh started -----"

APT_OPTS=(-y -o DPkg::Lock::Timeout=600 -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold)
apt_install() {
  local i
  for i in 1 2 3; do
    if sudo DEBIAN_FRONTEND=noninteractive apt-get install "${APT_OPTS[@]}" --no-install-recommends "$@"; then
      return 0
    fi
    warn "apt-get install failed (attempt $i/3), retrying in 10s..."
    sleep 10
    sudo apt-get update -o DPkg::Lock::Timeout=600 || true
  done
  return 1
}
apt_update() { sudo apt-get update -o DPkg::Lock::Timeout=600; }

# Read a line from the keyboard even when the script is piped (curl ... | bash).
ask() {
  local prompt="$1" default="$2" answer=""
  if [ "$ASSUME_YES" -eq 1 ]; then echo "$default"; return; fi
  if (exec </dev/tty) 2>/dev/null; then
    read -r -p "$prompt" answer < /dev/tty || true
  else
    read -r -p "$prompt" answer || true
  fi
  echo "${answer:-$default}"
}

# ------------------------------------------------------- 1. pre-flight -------
step "Checking your computer"

[ "$(id -u)" -ne 0 ] || die "Do not run this script with sudo or as root. Run it as your normal user: bash $0"

[ -r /etc/os-release ] || die "Cannot detect your operating system."
. /etc/os-release
if [ "${ID:-}" != "ubuntu" ] || [ "${VERSION_CODENAME:-}" != "noble" ]; then
  die "This script requires Ubuntu 24.04 (noble). Detected: ${PRETTY_NAME:-unknown}"
fi
ok "Ubuntu 24.04 detected"

case "$(dpkg --print-architecture)" in
  amd64|arm64) ok "Architecture $(dpkg --print-architecture)";;
  *) die "Unsupported CPU architecture: $(dpkg --print-architecture)";;
esac

free_gb=$(df -Pk "$HOME" | awk 'NR==2 {print int($4/1024/1024)}')
if [ "$free_gb" -lt "$MIN_DISK_GB" ]; then
  die "Not enough disk space: ${free_gb} GB free, at least ${MIN_DISK_GB} GB needed."
fi
ok "${free_gb} GB free disk space"

info "Your password is needed to install software (sudo)."
sudo -v || die "sudo permission is required."

# Keep sudo alive during the whole install.
( while true; do sudo -n true 2>/dev/null; sleep 50; kill -0 "$$" 2>/dev/null || exit; done ) &
SUDO_KEEPALIVE_PID=$!
trap 'kill $SUDO_KEEPALIVE_PID 2>/dev/null || true' EXIT

# ------------------------------------------------------- 2. questions --------
step "Configuration"

DEFAULT_DOMAIN_ID="${ROS_DOMAIN_ID:-$DEFAULT_DOMAIN_ID}"
echo
echo "    ROS_DOMAIN_ID isolates your robots from your classmates' robots on the"
echo "    same network. Use the number your teacher gave you (0-101)."
while true; do
  DOMAIN_ID=$(ask "    Enter your ROS_DOMAIN_ID [${DEFAULT_DOMAIN_ID}]: " "$DEFAULT_DOMAIN_ID")
  if [[ "$DOMAIN_ID" =~ ^[0-9]+$ ]] && [ "$DOMAIN_ID" -ge 0 ] && [ "$DOMAIN_ID" -le 101 ]; then
    DOMAIN_ID=$((10#$DOMAIN_ID))
    break
  fi
  echo "${C_RED}    Invalid value '$DOMAIN_ID'. Please enter a whole number between 0 and 101.${C_OFF}"
  [ "$ASSUME_YES" -eq 0 ] || die "Invalid ROS_DOMAIN_ID: $DOMAIN_ID"
done

WS_INPUT=$(ask "    Workspace folder [${WS:-$DEFAULT_WS}]: " "${WS:-$DEFAULT_WS}")
WS_INPUT="${WS_INPUT/#\~/$HOME}"
case "$WS_INPUT" in /*) ;; *) WS_INPUT="$HOME/$WS_INPUT";; esac
WS="${WS_INPUT%/}"

TB3_MODEL="${TB3_MODEL:-burger}"

ok "ROS_DOMAIN_ID = $DOMAIN_ID"
ok "Workspace     = $WS"
ok "TurtleBot3    = $TB3_MODEL"
info "The rest of the installation runs automatically (20-40 min depending on internet)."

# ------------------------------------------------------- 3. locale -----------
step "Setting up UTF-8 locale"
apt_update
apt_install locales curl ca-certificates gnupg lsb-release software-properties-common
if ! locale -a 2>/dev/null | grep -qi '^en_US\.utf-\?8$'; then
  sudo locale-gen en_US en_US.UTF-8
fi
if ! grep -q 'UTF-8' /etc/default/locale 2>/dev/null; then
  sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
fi
export LANG=en_US.UTF-8
ok "Locale ready"

# ------------------------------------------------------- 4. repositories -----
step "Adding the ROS 2 package repository"
sudo add-apt-repository -y universe >/dev/null

if dpkg -s ros2-apt-source >/dev/null 2>&1; then
  ok "ROS 2 apt source already installed"
else
  # Find latest ros-apt-source release via the redirect (no GitHub API rate limit).
  ROS_APT_SOURCE_VERSION=$(curl -fsSLI -o /dev/null -w '%{url_effective}' \
      https://github.com/ros-infrastructure/ros-apt-source/releases/latest | sed 's#.*/##')
  [ -n "$ROS_APT_SOURCE_VERSION" ] || die "Could not reach github.com to download the ROS apt source."
  info "ros-apt-source version: $ROS_APT_SOURCE_VERSION"
  tmp_deb="$(mktemp --suffix=.deb)"
  curl -fsSL -o "$tmp_deb" \
    "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${ROS_APT_SOURCE_VERSION}/ros2-apt-source_${ROS_APT_SOURCE_VERSION}.${VERSION_CODENAME}_all.deb"
  sudo DEBIAN_FRONTEND=noninteractive apt-get install "${APT_OPTS[@]}" "$tmp_deb"
  rm -f "$tmp_deb"
  ok "ROS 2 apt source installed"
fi
apt_update
info "Upgrading existing system packages (recommended by ROS before install)..."
sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade "${APT_OPTS[@]}"

# ------------------------------------------------------- 5. packages ---------
step "Installing ROS 2 ${ROS_DISTRO}, Gazebo Harmonic and TurtleBot3 (large download)"
PKGS=(
  # ROS 2 core + GUI tools (RViz2, rqt)
  ros-${ROS_DISTRO}-desktop
  ros-dev-tools
  # Gazebo Harmonic + ROS bridge
  ros-${ROS_DISTRO}-ros-gz
  # TurtleBot3 robot + simulation
  ros-${ROS_DISTRO}-turtlebot3
  ros-${ROS_DISTRO}-turtlebot3-msgs
  ros-${ROS_DISTRO}-turtlebot3-simulations
  # Extra tools
  ros-${ROS_DISTRO}-teleop-twist-keyboard
  ros-${ROS_DISTRO}-rqt-graph
  ros-${ROS_DISTRO}-rqt-robot-steering
  ros-${ROS_DISTRO}-rqt-tf-tree
  ros-${ROS_DISTRO}-rqt-image-view
  ros-${ROS_DISTRO}-tf2-tools
  python3-colcon-common-extensions
  python3-rosdep
  python3-pip
  build-essential
  cmake
  git
)

# Recommends are wanted here (e.g. gz GUI plugins), so no --no-install-recommends.
for i in 1 2 3; do
  if sudo DEBIAN_FRONTEND=noninteractive apt-get install "${APT_OPTS[@]}" "${PKGS[@]}"; then
    break
  fi
  [ "$i" -lt 3 ] || die "Package installation failed 3 times."
  warn "Install failed (attempt $i/3), retrying in 15s..."
  sleep 15
  apt_update || true
done
ok "Packages installed"

# ------------------------------------------------------- 6. rosdep ----------
step "Initializing rosdep"
if [ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]; then
  sudo rosdep init
fi
rosdep update --rosdistro "$ROS_DISTRO"
ok "rosdep ready"

# ------------------------------------------------------- 7. workspace -------
step "Creating and building the workspace $WS"
mkdir -p "$WS/src"

# ROS setup scripts reference unset variables, so relax 'nounset' while sourcing.
set +u

# shellcheck disable=SC1090
source "/opt/ros/${ROS_DISTRO}/setup.bash"
(
  cd "$WS"
  rosdep install --from-paths src --ignore-src -y -r --rosdistro "$ROS_DISTRO" || warn "rosdep could not resolve some dependencies"
  colcon build --symlink-install
)
set -u
ok "Workspace built"

# ------------------------------------------------------- 8. bashrc ----------
step "Configuring your terminal (~/.bashrc)"
touch "$BASHRC"

# Remove a previous block (re-run safe), then append a fresh one.
if grep -qF "$MARK_BEGIN" "$BASHRC"; then
  cp "$BASHRC" "$BASHRC.bak.ros2setup"
  sed -i "/^${MARK_BEGIN}\$/,/^${MARK_END}\$/d" "$BASHRC"
fi
cat >> "$BASHRC" <<EOF
${MARK_BEGIN}

# Added by setup_ros2_jazzy.sh - re-run the script to change these values.
source /opt/ros/${ROS_DISTRO}/setup.bash
if [ -f "${WS}/install/setup.bash" ]; then source "${WS}/install/setup.bash"; fi
export ROS_DOMAIN_ID=${DOMAIN_ID}
export TURTLEBOT3_MODEL=${TB3_MODEL}
export GZ_VERSION=harmonic
if [ -f /usr/share/colcon_argcomplete/hook/colcon-argcomplete.bash ]; then source /usr/share/colcon_argcomplete/hook/colcon-argcomplete.bash; fi
if [ -f /usr/share/colcon_cd/function/colcon_cd.sh ]; then source /usr/share/colcon_cd/function/colcon_cd.sh; export _colcon_cd_root="${WS}"; fi
alias ws='cd "${WS}"'
alias cb='(cd "${WS}" && colcon build --symlink-install) && source "${WS}/install/setup.bash"'
alias tb3_sim='ros2 launch turtlebot3_gazebo turtlebot3_world.launch.py'
alias tb3_empty='ros2 launch turtlebot3_gazebo empty_world.launch.py'
alias tb3_house='ros2 launch turtlebot3_gazebo turtlebot3_house.launch.py'
alias tb3_teleop='ros2 run turtlebot3_teleop teleop_keyboard'
${MARK_END}
EOF
ok "Terminal configured (ROS is sourced automatically in every new terminal)"

# ------------------------------------------------------- 9. self-test -------
step "Testing the installation"
set +u

# shellcheck disable=SC1090
source "$WS/install/setup.bash"
set -u
export ROS_DOMAIN_ID="$DOMAIN_ID" TURTLEBOT3_MODEL="$TB3_MODEL"

FAILED=0
for pkg in turtlebot3_gazebo turtlebot3_teleop ros_gz_sim rviz2 teleop_twist_keyboard; do
  if ros2 pkg prefix "$pkg" >/dev/null 2>&1; then ok "package $pkg found"; else warn "package $pkg NOT found"; FAILED=1; fi
done
if command -v gz >/dev/null 2>&1 && gz sim --version >/dev/null 2>&1; then
  ok "Gazebo $(gz sim --version 2>/dev/null | head -n1)"
else
  warn "Gazebo (gz sim) not working"; FAILED=1
fi

# Talker / listener communication test.
out=$(mktemp)
timeout 15 ros2 run demo_nodes_cpp listener > "$out" 2>&1 &
lpid=$!
sleep 2
timeout 8 ros2 run demo_nodes_cpp talker >/dev/null 2>&1 || true
wait "$lpid" 2>/dev/null || true
if grep -q "I heard" "$out"; then ok "ROS 2 communication works (talker -> listener)"; else warn "talker/listener test did not receive messages"; FAILED=1; fi
rm -f "$out"

echo
if [ "$FAILED" -eq 0 ]; then
  echo "${C_GREEN}=====================================================================${C_OFF}"
  echo "${C_GREEN}  INSTALLATION COMPLETE!${C_OFF}"
  echo "${C_GREEN}=====================================================================${C_OFF}"
else
  echo "${C_YELLOW}=====================================================================${C_OFF}"
  echo "${C_YELLOW}  Installation finished WITH WARNINGS (see above).${C_OFF}"
  echo "${C_YELLOW}  Send ${LOG_FILE} to your teacher if something does not work.${C_OFF}"
  echo "${C_YELLOW}=====================================================================${C_OFF}"
fi
cat <<EOF

  ROS_DOMAIN_ID : ${DOMAIN_ID}
  Workspace     : ${WS}
  Log file      : ${LOG_FILE}

  >>> CLOSE THIS TERMINAL AND OPEN A NEW ONE <<<  (or run: source ~/.bashrc)

  Then try:
     tb3_sim         start Gazebo with the TurtleBot3 world
     tb3_teleop      (in a 2nd terminal) drive the robot with the keyboard
     rviz2           3D visualization
     rqt_graph       see nodes and topics
     cb              build your workspace (${WS})

EOF

