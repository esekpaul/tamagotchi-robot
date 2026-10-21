#!/usr/bin/env python3
"""
Fisierul Launch pentru Tamagotchi Robot
Porneste automat nodul de stare si nodul de miscare
"""

from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        # 1. Nodul de Stare Interna
        Node(
            package='tamagotchi_robot',
            executable='state_node',
            name='tamagotchi_state',
            output='screen'
        ),
        # 2. Nodul de Miscare / Animatii Robot
        Node(
            package='tamagotchi_robot',
            executable='motion_node',
            name='tamagotchi_motion',
            output='screen'
        ),
    ])
