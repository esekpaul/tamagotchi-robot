#!/usr/bin/env python3
"""
Nodul de Miscare si Comportamente Fizice (Tamagotchi Motion Node)
Proiect Sincretic: Robot Tamagotchi
Traduce actiunile primite de la LLM/Stare in miscari fizice pe topicul /cmd_vel (in Gazebo sau pe robot)
Suporta comenzi specifice: rotatii de N ori, mers inainte, mers inapoi, fata-spate, viraje stanga/dreapta.
Compatibil ROS 2 Jazzy (TwistStamped) si Humble (Twist).
"""

import math
import os
import re
import time
import threading
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from geometry_msgs.msg import Twist, TwistStamped


class TamagotchiMotionNode(Node):
    def __init__(self):
        super().__init__('tamagotchi_motion_node')

        # In ROS 2 Jazzy, TurtleBot3 foloseste TwistStamped. In Humble foloseste Twist.
        self.ros_distro = os.environ.get('ROS_DISTRO', 'jazzy')
        if self.ros_distro == 'humble':
            self.use_stamped = False
            self.cmd_vel_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        else:
            self.use_stamped = True
            self.cmd_vel_pub = self.create_publisher(TwistStamped, '/cmd_vel', 10)

        # Subscriber pentru actiuni de la LLM sau state_node
        self.action_sub = self.create_subscription(
            String,
            '/tamagotchi/action',
            self.action_callback,
            10
        )

        self.animatie_in_curs = False

        self.get_logger().info(f'Nodul Tamagotchi Motion a pornit! (Mod: {"TwistStamped" if self.use_stamped else "Twist"})')
        self.get_logger().info('Asculta actiuni pe: /tamagotchi/action')
        self.get_logger().info('Trimite miscari pe: /cmd_vel')

    def action_callback(self, msg: String):
        actiune = msg.data.strip().lower()

        # Daca robotul doarme, oprim orice miscare imediat
        if actiune in ['sleep', 'dormi', 'somn']:
            self.stop_robot()
            self.get_logger().info('Robotul doarme: motoarele sunt oprite complet.')
            return

        # Daca ruleaza deja o animatie, nu o intrerupem decat pentru sleep
        if self.animatie_in_curs:
            self.get_logger().info(f'Ignor actiunea "{actiune}", o alta miscare este deja in curs.')
            return

        # --- Verificare comenzi cu parametri (de ex: rotate:3) ---
        match_rot = re.match(r'^(?:rotate|spin|invarte|rotatie):?(\d+)?$', actiune)
        if match_rot:
            nr_rotatii = int(match_rot.group(1)) if match_rot.group(1) else 1
            threading.Thread(target=self.animatie_rotatii, args=(nr_rotatii,), daemon=True).start()
            return

        # --- Comenzi de directie si deplasare ---
        if actiune in ['forward', 'inainte', 'fata', 'mergi_fata']:
            threading.Thread(target=self.animatie_mers, args=(0.18, 2.0, "inainte"), daemon=True).start()
        elif actiune in ['backward', 'inapoi', 'spate', 'mergi_spate']:
            threading.Thread(target=self.animatie_mers, args=(-0.18, 2.0, "inapoi"), daemon=True).start()
        elif actiune in ['forward_backward', 'fata_spate', 'fa_spate']:
            threading.Thread(target=self.animatie_fata_spate, daemon=True).start()
        elif actiune in ['turn_left', 'stanga', 'vira_stanga']:
            threading.Thread(target=self.animatie_viraj, args=(90, 1), daemon=True).start()
        elif actiune in ['turn_right', 'dreapta', 'vira_dreapta']:
            threading.Thread(target=self.animatie_viraj, args=(90, -1), daemon=True).start()

        # --- Comportamente Tamagotchi de baza ---
        elif actiune in ['play', 'joaca']:
            threading.Thread(target=self.animatie_joaca, daemon=True).start()
        elif actiune in ['feed', 'hrana', 'mananca']:
            threading.Thread(target=self.animatie_bucurie_mancare, daemon=True).start()
        elif actiune in ['wake', 'trezire']:
            threading.Thread(target=self.animatie_trezire, daemon=True).start()
        elif actiune in ['heal', 'medicament']:
            threading.Thread(target=self.animatie_recunostinta, daemon=True).start()

    def animatie_rotatii(self, numar_rotatii: int):
        """Efectueaza exact N rotatii complete (360 grade fiecare)."""
        self.animatie_in_curs = True
        viteza_unghiulara = 1.6  # rad/s (~91 grade/secunda)
        # 1 rotatie completa = 2 * pi radiani
        timp_per_rotatie = (2 * math.pi) / viteza_unghiulara
        durata_totala = numar_rotatii * timp_per_rotatie

        self.get_logger().info(f'Execut {numar_rotatii} rotatie/rotatii complete (Timp total: {durata_totala:.1f}s)')
        self.trimite_viteza(linear_x=0.0, angular_z=viteza_unghiulara, durata_secunde=durata_totala)
        self.stop_robot()
        self.animatie_in_curs = False

    def animatie_mers(self, viteza_lineara: float, durata_secunde: float, descriere: str):
        """Merge in linie dreapta (inainte sau inapoi)."""
        self.animatie_in_curs = True
        self.get_logger().info(f'Merg {descriere} timp de {durata_secunde} secunde...')
        self.trimite_viteza(linear_x=viteza_lineara, angular_z=0.0, durata_secunde=durata_secunde)
        self.stop_robot()
        self.animatie_in_curs = False

    def animatie_fata_spate(self):
        """Merge in fata, apoi in spate de 2 ori consecutiv."""
        self.animatie_in_curs = True
        self.get_logger().info('Execut miscare fata-spate...')
        for i in range(2):
            self.trimite_viteza(linear_x=0.18, angular_z=0.0, durata_secunde=1.2)
            self.trimite_viteza(linear_x=-0.18, angular_z=0.0, durata_secunde=1.2)
        self.stop_robot()
        self.animatie_in_curs = False

    def animatie_viraj(self, grade: float, directie: int):
        """Vireaza un anumit numar de grade (1 = stanga, -1 = dreapta)."""
        self.animatie_in_curs = True
        dir_text = "stanga" if directie > 0 else "dreapta"
        viteza_unghiulara = 1.4 * directie
        radiani = math.radians(grade)
        durata = abs(radiani / viteza_unghiulara)

        self.get_logger().info(f'Virez {grade} grade spre {dir_text}...')
        self.trimite_viteza(linear_x=0.0, angular_z=viteza_unghiulara, durata_secunde=durata)
        self.stop_robot()
        self.animatie_in_curs = False

    def animatie_joaca(self):
        """Dansul fericirii: se invarte stanga-dreapta si face o pirueta."""
        self.animatie_in_curs = True
        self.get_logger().info('Animatie: Dansul fericirii (joaca)!')

        # 1. Rotatie spre stanga
        self.trimite_viteza(linear_x=0.0, angular_z=1.8, durata_secunde=1.0)
        # 2. Rotatie spre dreapta
        self.trimite_viteza(linear_x=0.0, angular_z=-1.8, durata_secunde=1.0)
        # 3. Pirueta
        self.trimite_viteza(linear_x=0.1, angular_z=2.5, durata_secunde=1.5)

        self.stop_robot()
        self.animatie_in_curs = False

    def animatie_bucurie_mancare(self):
        """Miscare scurta inainte-inapoi (da din coada si multumeste)."""
        self.animatie_in_curs = True
        self.get_logger().info('Animatie: Multumire pentru mancare!')

        for _ in range(2):
            self.trimite_viteza(linear_x=0.15, angular_z=0.0, durata_secunde=0.5)
            self.trimite_viteza(linear_x=-0.15, angular_z=0.0, durata_secunde=0.5)

        self.stop_robot()
        self.animatie_in_curs = False

    def animatie_trezire(self):
        """Se intinde si priveste stanga-dreapta."""
        self.animatie_in_curs = True
        self.get_logger().info('Animatie: Trezire si intindere!')

        self.trimite_viteza(linear_x=0.05, angular_z=0.8, durata_secunde=0.8)
        self.trimite_viteza(linear_x=0.05, angular_z=-0.8, durata_secunde=0.8)

        self.stop_robot()
        self.animatie_in_curs = False

    def animatie_recunostinta(self):
        """O mica rotire blanda si oprire."""
        self.animatie_in_curs = True
        self.trimite_viteza(linear_x=0.0, angular_z=0.6, durata_secunde=1.2)
        self.stop_robot()
        self.animatie_in_curs = False

    def trimite_viteza(self, linear_x: float, angular_z: float, durata_secunde: float):
        """Trimite continuu mesaje de viteza timp de durata specificata."""
        sfarsit = time.time() + durata_secunde
        while time.time() < sfarsit and rclpy.ok():
            if self.use_stamped:
                msg = TwistStamped()
                msg.header.stamp = self.get_clock().now().to_msg()
                msg.header.frame_id = 'base_link'
                msg.twist.linear.x = float(linear_x)
                msg.twist.angular.z = float(angular_z)
                self.cmd_vel_pub.publish(msg)
            else:
                msg = Twist()
                msg.linear.x = float(linear_x)
                msg.angular.z = float(angular_z)
                self.cmd_vel_pub.publish(msg)
            time.sleep(0.05)

    def stop_robot(self):
        """Trimite viteza 0 pentru a opri rotile robotului."""
        if self.use_stamped:
            msg = TwistStamped()
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.header.frame_id = 'base_link'
            self.cmd_vel_pub.publish(msg)
        else:
            msg = Twist()
            self.cmd_vel_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = TamagotchiMotionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.stop_robot()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
