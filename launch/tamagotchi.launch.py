#!/usr/bin/env python3
"""
Fisierul Launch pentru Tamagotchi Robot
Porneste automat:
1. Nodul de Stare Biologica (state_node)
2. Nodul de Miscare / Control Fizic (motion_node)
3. Nodul de Viziune Artificiala in mod STANDBY / la cerere (vision_node)
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
        # 3. Nodul de Viziune Faciala (porneste cu camera OPRITA in standby, activabil la comanda)
        Node(
            package='tamagotchi_robot',
            executable='vision_node',
            name='tamagotchi_vision',
            output='screen'
        ),
    ])
