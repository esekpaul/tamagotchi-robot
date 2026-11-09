import os
from glob import glob
from setuptools import find_packages, setup

package_name = 'tamagotchi_robot'

setup(
    name=package_name,
    version='1.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml', 'README.md']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'models'), glob('models/*.onnx')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='esek',
    maintainer_email='esek@local',
    description='Proiect Sincretic: Robot Tamagotchi autonom in ROS 2 Jazzy si Gazebo',
    license='MIT',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'state_node = tamagotchi_robot.state_node:main',
            'llm_node = tamagotchi_robot.llm_node:main',
            'motion_node = tamagotchi_robot.motion_node:main',
            'voice_node = tamagotchi_robot.voice_node:main',
            'vision_node = tamagotchi_robot.vision_node:main',
        ],
    },
)
