#!/usr/bin/env bash
# Script de pornire completa pentru Proiectul Sincretic: Robot Tamagotchi
set -e

source /opt/ros/jazzy/setup.bash
if [ -f "$HOME/ros2_ws/install/setup.bash" ]; then
    source "$HOME/ros2_ws/install/setup.bash"
fi

export ROS_DOMAIN_ID=99
export TURTLEBOT3_MODEL=burger
export GZ_VERSION=harmonic

echo "🚀 Pornim Simulatorul Gazebo (TurtleBot3 World)..."
ros2 launch turtlebot3_gazebo turtlebot3_world.launch.py &
GZ_PID=$!

sleep 3

echo "🧬 Pornim nodurile Tamagotchi (State, Motion, Vision Standby)..."
ros2 launch tamagotchi_robot tamagotchi.launch.py &
NODES_PID=$!

sleep 2

echo "🤖 Deschidem consola interactiva Tamagotchi LLM & Voice..."
if command -v gnome-terminal >/dev/null 2>&1; then
    gnome-terminal --geometry=90x32 --title="Tamagotchi LLM & Voice Control" -- bash -c "source /opt/ros/jazzy/setup.bash && source $HOME/ros2_ws/install/setup.bash && export ROS_DOMAIN_ID=99 TURTLEBOT3_MODEL=burger GZ_VERSION=harmonic && ros2 run tamagotchi_robot llm_node; exec bash"
    wait $GZ_PID
else
    ros2 run tamagotchi_robot llm_node
fi

kill $NODES_PID $GZ_PID 2>/dev/null || true
