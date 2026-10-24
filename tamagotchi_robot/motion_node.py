#!/usr/bin/env python3
"""
Nodul de Miscare si Comportamente Fizice (Tamagotchi Motion Node)
Proiect Sincretic: Robot Tamagotchi
Traduce actiunile primite de la LLM/Stare in miscari fizice de inalta precizie pe /cmd_vel.
Caracteristici avansate:
- Control in bucla inchisa pe baza Odometriei (/odom) pentru rotatii si viraje la grad fix (360° per rotatie, 90° viraj).
- Turul arenei complet autonom folosind senzorul LiDAR (/scan) la viteza sporita (Wall Following).
- Oprire de urgenta imediata (stop / sleep).
- Compatibil ROS 2 Jazzy (TwistStamped) si Humble (Twist).
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
from sensor_msgs.msg import LaserScan
from nav_msgs.msg import Odometry


def normalize_angle(angle: float) -> float:
    """Normalizeaza un unghi in intervalul [-pi, pi]."""
    while angle > math.pi:
        angle -= 2.0 * math.pi
    while angle < -math.pi:
        angle += 2.0 * math.pi
    return angle


def quat_to_yaw(q) -> float:
    """Converteste un quaternion ROS in unghiul Yaw (radiani)."""
    siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
    cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny_cosp, cosy_cosp)


class TamagotchiMotionNode(Node):
    def __init__(self):
        super().__init__('tamagotchi_motion_node')

        # Formatul de viteza: Jazzy foloseste TwistStamped, Humble Twist
        self.ros_distro = os.environ.get('ROS_DISTRO', 'jazzy')
        self.use_stamped = (self.ros_distro != 'humble')

        if self.use_stamped:
            self.cmd_vel_pub = self.create_publisher(TwistStamped, '/cmd_vel', 10)
        else:
            self.cmd_vel_pub = self.create_publisher(Twist, '/cmd_vel', 10)

        # Topicuri de intrare
        self.action_sub = self.create_subscription(
            String,
            '/tamagotchi/action',
            self.action_callback,
            10
        )

        self.latest_scan = None
        self.scan_sub = self.create_subscription(
            LaserScan,
            '/scan',
            self.scan_callback,
            10
        )

        self.current_yaw = 0.0
        self.current_pos = (0.0, 0.0)
        self.odom_ready = False
        self.odom_sub = self.create_subscription(
            Odometry,
            '/odom',
            self.odom_callback,
            10
        )

        self.animatie_in_curs = False
        self.stop_current_action = False

        self.get_logger().info('=' * 60)
        self.get_logger().info('🤖 Nodul Tamagotchi Motion a pornit cu succes!')
        self.get_logger().info(f'   - Format viteza: {"TwistStamped" if self.use_stamped else "Twist"}')
        self.get_logger().info('   - Asculta actiuni pe: /tamagotchi/action')
        self.get_logger().info('   - Senzor LiDAR activ: /scan')
        self.get_logger().info('   - Odometrie de precizie: /odom')
        self.get_logger().info('=' * 60)

    def odom_callback(self, msg: Odometry):
        """Actualizeaza pozitia si orientarea curenta din odometrie."""
        self.current_yaw = quat_to_yaw(msg.pose.pose.orientation)
        self.current_pos = (msg.pose.pose.position.x, msg.pose.pose.position.y)
        self.odom_ready = True

    def scan_callback(self, msg: LaserScan):
        """Actualizeaza ultima scanare LiDAR receptionata."""
        self.latest_scan = msg

    def action_callback(self, msg: String):
        actiune = msg.data.strip().lower()

        # 1. Oprire de urgenta sau intrare in modul somn
        if actiune in ['sleep', 'dormi', 'somn', 'stop', 'stai', 'oprire', 'frana']:
            self.stop_current_action = True
            self.stop_robot()
            self.animatie_in_curs = False
            self.get_logger().info('🛑 Oprire imediata! Motoarele au fost decuplate.')
            return

        # 2. Daca ruleaza deja o miscare, ignoram comanda noua pana la finalizare
        if self.animatie_in_curs:
            self.get_logger().info(f'Ignor actiunea "{actiune}", o alta miscare este deja in desfasurare.')
            return

        self.stop_current_action = False

        # 3. Turul arenei (Wall Following autonom)
        if actiune in ['arena_tour', 'turul_arenei', 'tura_arena', 'wall_follow']:
            threading.Thread(target=self.animatie_turul_arenei, daemon=True).start()
            return

        # 4. Rotatii de N ori (ex: rotate:3, rotate:5, rotate:10)
        match_rot = re.match(r'^(?:rotate|rot|spin|invarte|invart|rotatie|rotire|rasuceste|rasucire):?(\d+)?$', actiune)
        if match_rot:
            nr_rotatii = int(match_rot.group(1)) if match_rot.group(1) else 1
            threading.Thread(target=self.animatie_rotatii, args=(nr_rotatii,), daemon=True).start()
            return

        # 5. Comenzi de translatie si deplasare
        if actiune in ['forward', 'inainte', 'fata', 'mergi_fata']:
            threading.Thread(target=self.animatie_mers, args=(0.8, 0.20, "inainte"), daemon=True).start()
        elif actiune in ['backward', 'inapoi', 'spate', 'mergi_spate']:
            threading.Thread(target=self.animatie_mers, args=(0.8, -0.20, "inapoi"), daemon=True).start()
        elif actiune in ['forward_backward', 'fata_spate', 'fa_spate']:
            threading.Thread(target=self.animatie_fata_spate, daemon=True).start()
        elif actiune in ['turn_left', 'stanga', 'vira_stanga']:
            threading.Thread(target=self.animatie_viraj, args=(90.0, 1), daemon=True).start()
        elif actiune in ['turn_right', 'dreapta', 'vira_dreapta']:
            threading.Thread(target=self.animatie_viraj, args=(90.0, -1), daemon=True).start()

        # 6. Comportamente specifice Tamagotchi
        elif actiune in ['play', 'joaca']:
            threading.Thread(target=self.animatie_joaca, daemon=True).start()
        elif actiune in ['feed', 'hrana', 'mananca']:
            threading.Thread(target=self.animatie_bucurie_mancare, daemon=True).start()
        elif actiune in ['wake', 'trezire']:
            threading.Thread(target=self.animatie_trezire, daemon=True).start()
        elif actiune in ['heal', 'medicament']:
            threading.Thread(target=self.animatie_recunostinta, daemon=True).start()

    def animatie_rotatii(self, numar_rotatii: int):
        """
        Efectueaza exact N rotatii complete (N x 360 grade).
        Foloseste bucla inchisa pe odometrie pentru precizie absoluta (nu depinde de ceasul CPU).
        """
        self.animatie_in_curs = True
        self.stop_current_action = False
        numar_rotatii = min(20, max(1, numar_rotatii))

        self.get_logger().info(f'🌀 Incep rotatie de {numar_rotatii} ori (Control de precizie /odom)...')

        viteza_rotatie = 1.6  # rad/s (~91.7 grade/s)
        total_unghi_necesar = numar_rotatii * 2.0 * math.pi
        unghi_acumulat = 0.0

        # Daca odometria este disponibila, folosim bucla inchisa de inalta precizie
        if self.odom_ready:
            last_yaw = self.current_yaw
            timeout_max = time.time() + (numar_rotatii * 6.0) + 10.0

            while (unghi_acumulat < total_unghi_necesar) and not self.stop_current_action and rclpy.ok() and (time.time() < timeout_max):
                self.trimite_viteza_instant(linear_x=0.0, angular_z=viteza_rotatie)
                time.sleep(0.02)
                delta = normalize_angle(self.current_yaw - last_yaw)
                unghi_acumulat += abs(delta)
                last_yaw = self.current_yaw
        else:
            # Fallback pe durata temporala daca odom lipseste
            durata_totala = numar_rotatii * (2.0 * math.pi / viteza_rotatie)
            self.trimite_viteza(linear_x=0.0, angular_z=viteza_rotatie, durata_secunde=durata_totala)

        self.stop_robot()
        self.animatie_in_curs = False
        self.get_logger().info(f'✅ Am finalizat cu succes cele {numar_rotatii} rotatii!')

    def animatie_viraj(self, grade: float, directie: int):
        """
        Vireaza un numar exact de grade (directie: 1=stanga, -1=dreapta).
        Control in bucla inchisa prin odometrie.
        """
        self.animatie_in_curs = True
        self.stop_current_action = False
        dir_text = "stanga" if directie > 0 else "dreapta"
        self.get_logger().info(f'🔄 Virez {grade}° spre {dir_text}...')

        viteza_rot = 1.4 * directie
        radiani_tinta = math.radians(grade)
        unghi_acumulat = 0.0

        if self.odom_ready:
            last_yaw = self.current_yaw
            timeout = time.time() + 5.0
            while (unghi_acumulat < radiani_tinta) and not self.stop_current_action and rclpy.ok() and (time.time() < timeout):
                self.trimite_viteza_instant(linear_x=0.0, angular_z=viteza_rot)
                time.sleep(0.02)
                delta = normalize_angle(self.current_yaw - last_yaw)
                unghi_acumulat += abs(delta)
                last_yaw = self.current_yaw
        else:
            durata = abs(radiani_tinta / 1.4)
            self.trimite_viteza(linear_x=0.0, angular_z=viteza_rot, durata_secunde=durata)

        self.stop_robot()
        self.animatie_in_curs = False
        self.get_logger().info(f'✅ Viraj {grade}° spre {dir_text} incheiat!')

    def animatie_mers(self, distanta_metri: float, viteza: float, descriere: str):
        """Deplaseaza robotul pe o distanta data (inainte sau inapoi) folosind odometria."""
        self.animatie_in_curs = True
        self.stop_current_action = False
        self.get_logger().info(f'🚗 Merg {descriere} ({distanta_metri}m la viteza {viteza:.2f} m/s)...')

        if self.odom_ready:
            start_x, start_y = self.current_pos
            dist_parcursa = 0.0
            timeout = time.time() + (abs(distanta_metri / viteza) * 2.0) + 3.0

            while (dist_parcursa < distanta_metri) and not self.stop_current_action and rclpy.ok() and (time.time() < timeout):
                self.trimite_viteza_instant(linear_x=viteza, angular_z=0.0)
                time.sleep(0.02)
                cur_x, cur_y = self.current_pos
                dist_parcursa = math.hypot(cur_x - start_x, cur_y - start_y)
        else:
            durata = abs(distanta_metri / viteza)
            self.trimite_viteza(linear_x=viteza, angular_z=0.0, durata_secunde=durata)

        self.stop_robot()
        self.animatie_in_curs = False
        self.get_logger().info(f'✅ Mers {descriere} incheiat!')

    def animatie_fata_spate(self):
        """Mers rapid inainte si inapoi (comportament jucaus)."""
        self.animatie_in_curs = True
        self.stop_current_action = False
        self.get_logger().info('🐾 Execut dansul fata-spate...')

        for _ in range(2):
            if self.stop_current_action:
                break
            self.trimite_viteza(linear_x=0.20, angular_z=0.0, durata_secunde=1.0)
            self.trimite_viteza(linear_x=-0.20, angular_z=0.0, durata_secunde=1.0)

        self.stop_robot()
        self.animatie_in_curs = False

    def animatie_turul_arenei(self):
        """
        Navigatie autonoma completa - Turul Arenei la viteza marita (Wall Following):
        1. Citeste LiDAR-ul (/scan) si localizeaza cel mai apropiat perete.
        2. Se orienteaza cu precizie cu fata spre acel punct.
        3. Avanseaza cu viteza marita (0.22 m/s) pana la 40 cm de perete.
        4. Vreaza stanga 90° pentru a plasa peretele pe partea dreapta.
        5. Urmareste conturul arenei (Right-Wall Following reactiv) timp de 60 secunde.
        """
        self.animatie_in_curs = True
        self.stop_current_action = False
        self.get_logger().info('🏁 INCEP COMANDA: TURUL ARENEI!')

        # Asteptam scanarea LiDAR daca e necesar
        timeout_wait = time.time() + 3.0
        while self.latest_scan is None and time.time() < timeout_wait and not self.stop_current_action:
            time.sleep(0.05)

        if self.latest_scan is None or self.stop_current_action:
            self.get_logger().warn('Nu s-au putut receptiona date de la senzorul LiDAR (/scan).')
            self.animatie_in_curs = False
            return

        # --- FAZA 1: Localizarea celui mai apropiat perete ---
        self.get_logger().info('Faza 1: Identific cel mai apropiat perete al arenei...')
        ranges = list(self.latest_scan.ranges)
        curatate = []
        for idx, r in enumerate(ranges):
            if math.isnan(r) or math.isinf(r) or r < 0.12 or r > 5.0:
                curatate.append((100.0, idx))
            else:
                curatate.append((r, idx))

        dist_min, idx_min = min(curatate, key=lambda x: x[0])
        self.get_logger().info(f'Perete detectat la distanta de {dist_min:.2f}m, directia {idx_min}°.')

        # Calculam unghiul relativ de rotire
        if idx_min <= 180:
            unghi_rot_deg = float(idx_min)
        else:
            unghi_rot_deg = float(idx_min - 360)

        # Ne rotim direct spre perete
        if abs(unghi_rot_deg) > 4.0:
            directie = 1 if unghi_rot_deg > 0 else -1
            self.animatie_viraj(abs(unghi_rot_deg), directie)

        if self.stop_current_action:
            self.animatie_in_curs = False
            return

        # --- FAZA 2: Deplasare rapida spre perete ---
        self.get_logger().info('Faza 2: Avansez cu viteza marita spre perete...')
        viteza_rapida = 0.22  # Viteza marita
        dist_stop_perete = 0.42

        start_approach = time.time()
        while (time.time() - start_approach < 15.0) and not self.stop_current_action and rclpy.ok():
            if self.latest_scan:
                scan_ranges = self.latest_scan.ranges
                front_ranges = []
                for i in range(-20, 21):
                    val = scan_ranges[i % 360]
                    if not (math.isnan(val) or math.isinf(val) or val < 0.12):
                        front_ranges.append(val)
                d_front = min(front_ranges) if front_ranges else 1.0
            else:
                d_front = 1.0

            if d_front <= dist_stop_perete:
                self.get_logger().info(f'Am ajuns la perete ({d_front:.2f}m)!')
                break

            self.trimite_viteza_instant(linear_x=viteza_rapida, angular_z=0.0)
            time.sleep(0.04)

        self.stop_robot()
        time.sleep(0.2)

        if self.stop_current_action:
            self.animatie_in_curs = False
            return

        # --- FAZA 3: Aliniere paralela cu peretele (viraj 90° stanga) ---
        self.get_logger().info('Faza 3: Mă aliniez paralel cu peretele...')
        self.animatie_viraj(90.0, directie=1)
        time.sleep(0.2)

        if self.stop_current_action:
            self.animatie_in_curs = False
            return

        # --- FAZA 4: Urmarirea peretelui (Right Wall Following) la viteza marita ---
        self.get_logger().info('Faza 4: Rulez de-a lungul peretelui arenei!')
        durata_tur = 60.0  # Durata unei ture complete
        start_tur = time.time()
        d_tinta_perete = 0.38

        while (time.time() - start_tur < durata_tur) and not self.stop_current_action and rclpy.ok():
            if not self.latest_scan:
                time.sleep(0.04)
                continue

            scan = self.latest_scan.ranges

            # Frontal (-25° la +25°)
            front = [scan[i % 360] for i in range(-25, 26)
                     if not (math.isnan(scan[i % 360]) or math.isinf(scan[i % 360]) or scan[i % 360] < 0.12)]
            d_f = min(front) if front else 2.0

            # Dreapta-Fata (285° la 330°)
            fr_right = [scan[i] for i in range(285, 331)
                        if not (math.isnan(scan[i]) or math.isinf(scan[i]) or scan[i] < 0.12)]
            d_fr = min(fr_right) if fr_right else 2.0

            # Dreapta (250° la 285°)
            right = [scan[i] for i in range(250, 286)
                     if not (math.isnan(scan[i]) or math.isinf(scan[i]) or scan[i] < 0.12)]
            d_r = min(right) if right else 2.0

            # Algoritm reactiv de navigatie
            if d_f < 0.42 or d_fr < 0.32:
                # Obstacol sau colt frontal -> viraj stanga prompt
                lin = 0.08
                ang = 1.45
            elif d_r < 0.28:
                # Prea aproape de peretele din dreapta -> distantare stanga
                lin = 0.20
                ang = 0.65
            elif d_r > 0.62:
                # Colt deschis / depasire perete -> cautare perete dreapta
                lin = 0.16
                ang = -0.75
            else:
                # Urmarire proportionala lina la viteza maxima (0.22 m/s)
                eroare = d_r - d_tinta_perete
                ang = -1.6 * eroare
                ang = max(-0.8, min(0.8, ang))
                lin = 0.22

            self.trimite_viteza_instant(linear_x=lin, angular_z=ang)
            time.sleep(0.04)

        self.stop_robot()
        self.animatie_in_curs = False
        self.get_logger().info('🏆 Turul arenei a fost finalizat cu succes!')

    def animatie_joaca(self):
        """Dansul bucuriei: rotiri stanga-dreapta si o pirueta completa."""
        self.animatie_in_curs = True
        self.stop_current_action = False
        self.get_logger().info('🎉 Dansul fericirii!')

        self.trimite_viteza(linear_x=0.0, angular_z=1.8, durata_secunde=0.8)
        self.trimite_viteza(linear_x=0.0, angular_z=-1.8, durata_secunde=0.8)
        self.trimite_viteza(linear_x=0.10, angular_z=2.5, durata_secunde=1.2)

        self.stop_robot()
        self.animatie_in_curs = False

    def animatie_bucurie_mancare(self):
        """Miscare scurta inainte-inapoi (da din coada si multumeste)."""
        self.animatie_in_curs = True
        self.stop_current_action = False
        self.get_logger().info('🍖 Bucurie pentru mancare!')

        for _ in range(2):
            if self.stop_current_action:
                break
            self.trimite_viteza(linear_x=0.15, angular_z=0.0, durata_secunde=0.5)
            self.trimite_viteza(linear_x=-0.15, angular_z=0.0, durata_secunde=0.5)

        self.stop_robot()
        self.animatie_in_curs = False

    def animatie_trezire(self):
        """Trezire: intindere usoara si privire in jur."""
        self.animatie_in_curs = True
        self.stop_current_action = False
        self.get_logger().info('☀️ Trezire si intindere!')

        self.trimite_viteza(linear_x=0.05, angular_z=0.8, durata_secunde=0.6)
        self.trimite_viteza(linear_x=0.05, angular_z=-0.8, durata_secunde=0.6)

        self.stop_robot()
        self.animatie_in_curs = False

    def animatie_recunostinta(self):
        """Rotire blanda si inclinare de recunostinta."""
        self.animatie_in_curs = True
        self.stop_current_action = False
        self.trimite_viteza(linear_x=0.0, angular_z=0.8, durata_secunde=1.0)
        self.stop_robot()
        self.animatie_in_curs = False

    def trimite_viteza(self, linear_x: float, angular_z: float, durata_secunde: float):
        """Trimite comenzi de viteza la frecventa de 20 Hz timp de durata_secunde."""
        sfarsit = time.time() + durata_secunde
        while time.time() < sfarsit and rclpy.ok() and not self.stop_current_action:
            self.trimite_viteza_instant(linear_x, angular_z)
            time.sleep(0.05)

    def trimite_viteza_instant(self, linear_x: float, angular_z: float):
        """Trimite un singur cadru de viteza conform distributiei ROS 2."""
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

    def stop_robot(self):
        """Opreste complet rotile robotului."""
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
