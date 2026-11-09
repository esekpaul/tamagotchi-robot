#!/usr/bin/env python3
"""
Nodul de Miscare si Comportamente Fizice (Tamagotchi Motion Node)
Proiect Sincretic: Robot Tamagotchi
Traduce actiunile primite de la LLM/Stare in miscari fizice de inalta precizie pe /cmd_vel.
Caracteristici avansate:
- Control in bucla inchisa pe baza Odometriei (/odom) pentru rotatii si viraje la grad fix (360° per rotatie, 90° viraj).
- Preemptiune automata: o comanda noua opreste curat miscarea anterioara si o executa imediat pe cea noua.
- Protectie anti-coliziune cu senzorul LiDAR (/scan) la mersul inainte.
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
        self.active_thread = None
        self.motion_lock = threading.Lock()

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

    def _get_sector_min(self, deg_start: int, deg_end: int, default_val: float = 2.0) -> float:
        """Returneaza distanta minima valida dintr-un sector unghiular LiDAR [deg_start, deg_end]."""
        if not self.latest_scan or not self.latest_scan.ranges:
            return default_val
        ranges = self.latest_scan.ranges
        n = len(ranges)
        if n == 0:
            return default_val

        vals = []
        for deg in range(deg_start, deg_end + 1):
            idx = int(round((deg % 360) * n / 360.0)) % n
            val = ranges[idx]
            if not (math.isnan(val) or math.isinf(val) or val < 0.12):
                vals.append(val)
        return min(vals) if vals else default_val

    def _start_new_motion(self, target_fn, args=()):
        """Opreste curat orice miscare anterioara si lanseaza noua miscare intr-un fir dedicat."""
        def runner():
            with self.motion_lock:
                self.stop_current_action = False
                self.animatie_in_curs = True
                try:
                    target_fn(*args)
                finally:
                    self.stop_robot()
                    self.animatie_in_curs = False

        # Daca o miscare este in curs, o intrerupem imediat pentru a da prioritate noii comenzi
        if self.animatie_in_curs:
            self.stop_current_action = True
            self.stop_robot()

        t = threading.Thread(target=runner, daemon=True)
        self.active_thread = t
        t.start()

    def action_callback(self, msg: String):
        actiune = msg.data.strip().lower()

        # 1. Oprire de urgenta sau intrare in modul somn
        if actiune in ['sleep', 'dormi', 'somn', 'stop', 'stai', 'oprire', 'frana']:
            self.stop_current_action = True
            self.stop_robot()
            self.animatie_in_curs = False
            self.get_logger().info('🛑 Oprire imediata! Motoarele au fost decuplate.')
            return

        # 2. Turul arenei (Wall Following autonom)
        if actiune in ['arena_tour', 'turul_arenei', 'tura_arena', 'wall_follow']:
            self._start_new_motion(self.animatie_turul_arenei)
            return

        # 3. Rotatii de N ori (ex: rotate:3, rotate:5, rotate:10)
        match_rot = re.match(r'^(?:rotate|rot|spin|invarte|invart|rotatie|rotire|rasuceste|rasucire):?(\d+)?$', actiune)
        if match_rot:
            nr_rotatii = int(match_rot.group(1)) if match_rot.group(1) else 1
            self._start_new_motion(self.animatie_rotatii, (nr_rotatii,))
            return

        # 4. Comenzi de translatie si deplasare
        if actiune in ['forward', 'inainte', 'fata', 'mergi_fata']:
            self._start_new_motion(self.animatie_mers, (0.8, 0.20, "inainte"))
        elif actiune in ['backward', 'inapoi', 'spate', 'mergi_spate']:
            self._start_new_motion(self.animatie_mers, (0.8, -0.20, "inapoi"))
        elif actiune in ['forward_backward', 'fata_spate', 'fa_spate']:
            self._start_new_motion(self.animatie_fata_spate)
        elif actiune in ['turn_left', 'stanga', 'vira_stanga']:
            self._start_new_motion(self.animatie_viraj, (90.0, 1))
        elif actiune in ['turn_right', 'dreapta', 'vira_dreapta']:
            self._start_new_motion(self.animatie_viraj, (90.0, -1))

        # 5. Comportamente specifice Tamagotchi
        elif actiune in ['play', 'joaca']:
            self._start_new_motion(self.animatie_joaca)
        elif actiune in ['feed', 'hrana', 'mananca']:
            self._start_new_motion(self.animatie_bucurie_mancare)
        elif actiune in ['wake', 'trezire']:
            self._start_new_motion(self.animatie_trezire)
        elif actiune in ['heal', 'medicament']:
            self._start_new_motion(self.animatie_recunostinta)

    def _executa_viraj_intern(self, grade: float, directie: int):
        """
        Functie interna: vireaza un numar exact de grade (directie: 1=stanga, -1=dreapta)
        fara a reseta flag-ul global animatie_in_curs (sigur pentru apel din animatie_turul_arenei).
        """
        dir_text = "stanga" if directie > 0 else "dreapta"
        self.get_logger().info(f'🔄 Virez {grade:.1f}° spre {dir_text}...')

        viteza_rot = 1.4 * directie
        radiani_tinta = math.radians(grade)
        unghi_acumulat = 0.0

        if self.odom_ready:
            last_yaw = self.current_yaw
            timeout = time.time() + max(5.0, (radiani_tinta / 1.0) + 2.0)
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

    def animatie_rotatii(self, numar_rotatii: int):
        """
        Efectueaza exact N rotatii complete (N x 360 grade).
        Foloseste bucla inchisa pe odometrie pentru precizie absoluta.
        """
        numar_rotatii = min(20, max(1, numar_rotatii))
        self.get_logger().info(f'🌀 Incep rotatie de {numar_rotatii} ori (Control de precizie /odom)...')

        viteza_rotatie = 1.6  # rad/s (~91.7 grade/s)
        total_unghi_necesar = numar_rotatii * 2.0 * math.pi
        unghi_acumulat = 0.0

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
            durata_totala = numar_rotatii * (2.0 * math.pi / viteza_rotatie)
            self.trimite_viteza(linear_x=0.0, angular_z=viteza_rotatie, durata_secunde=durata_totala)

        self.stop_robot()
        if not self.stop_current_action:
            self.get_logger().info(f'✅ Am finalizat cu succes cele {numar_rotatii} rotatii!')

    def animatie_viraj(self, grade: float, directie: int):
        """Vireaza un numar exact de grade (1=stanga, -1=dreapta)."""
        self._executa_viraj_intern(grade, directie)
        if not self.stop_current_action:
            dir_text = "stanga" if directie > 0 else "dreapta"
            self.get_logger().info(f'✅ Viraj {grade:.0f}° spre {dir_text} incheiat!')

    def animatie_mers(self, distanta_metri: float, viteza: float, descriere: str):
        """Deplaseaza robotul pe o distanta data (inainte sau inapoi) cu protectie LiDAR la obstacole."""
        self.get_logger().info(f'🚗 Merg {descriere} ({distanta_metri}m la viteza {viteza:.2f} m/s)...')

        if self.odom_ready:
            start_x, start_y = self.current_pos
            dist_parcursa = 0.0
            timeout = time.time() + (abs(distanta_metri / viteza) * 2.5) + 3.0

            while (dist_parcursa < distanta_metri) and not self.stop_current_action and rclpy.ok() and (time.time() < timeout):
                # Protectie anti-coliziune cu LiDAR:
                if viteza > 0 and self._get_sector_min(-22, 22, 2.0) < 0.28:
                    self.get_logger().warn('⚠️ Obstacol detectat in fata la <28cm! Opresc preventiv.')
                    break
                elif viteza < 0 and self._get_sector_min(158, 202, 2.0) < 0.28:
                    self.get_logger().warn('⚠️ Obstacol detectat in spate la <28cm! Opresc preventiv.')
                    break

                self.trimite_viteza_instant(linear_x=viteza, angular_z=0.0)
                time.sleep(0.02)
                cur_x, cur_y = self.current_pos
                dist_parcursa = math.hypot(cur_x - start_x, cur_y - start_y)
        else:
            durata = abs(distanta_metri / viteza)
            self.trimite_viteza(linear_x=viteza, angular_z=0.0, durata_secunde=durata)

        self.stop_robot()
        if not self.stop_current_action:
            self.get_logger().info(f'✅ Mers {descriere} incheiat!')

    def animatie_fata_spate(self):
        """Mers rapid inainte si inapoi (comportament jucaus)."""
        self.get_logger().info('🐾 Execut dansul fata-spate...')

        for _ in range(2):
            if self.stop_current_action:
                break
            self.trimite_viteza(linear_x=0.20, angular_z=0.0, durata_secunde=1.0)
            self.trimite_viteza(linear_x=-0.20, angular_z=0.0, durata_secunde=1.0)

        self.stop_robot()

    def animatie_turul_arenei(self):
        """
        Navigatie autonoma completa - Turul Arenei la viteza marita (Wall Following):
        1. Citeste LiDAR-ul (/scan) si localizeaza cel mai apropiat perete/obstacol.
        2. Se orienteaza cu precizie cu fata spre acel punct.
        3. Avanseaza cu viteza marita (0.22 m/s) pana la ~40 cm de obstacol.
        4. Vireaza stanga 90° pentru a plasa peretele pe partea dreapta.
        5. Urmareste conturul arenei (Right-Wall Following reactiv) timp de 60 secunde.
        """
        self.get_logger().info('🏁 INCEP COMANDA: TURUL ARENEI!')

        timeout_wait = time.time() + 3.0
        while self.latest_scan is None and time.time() < timeout_wait and not self.stop_current_action:
            time.sleep(0.05)

        if self.latest_scan is None or self.stop_current_action:
            self.get_logger().warn('Nu s-au putut receptiona date de la senzorul LiDAR (/scan).')
            return

        # --- FAZA 1: Localizarea celui mai apropiat perete ---
        self.get_logger().info('Faza 1: Identific cel mai apropiat perete al arenei...')
        ranges = list(self.latest_scan.ranges)
        n = len(ranges)
        curatate = []
        for idx, r in enumerate(ranges):
            if math.isnan(r) or math.isinf(r) or r < 0.12 or r > 5.0:
                curatate.append((100.0, idx))
            else:
                curatate.append((r, idx))

        dist_min, idx_min = min(curatate, key=lambda x: x[0])
        deg_min = (idx_min * 360.0 / n) if n > 0 else float(idx_min)
        self.get_logger().info(f'Perete detectat la distanta de {dist_min:.2f}m, directia {deg_min:.0f}°.')

        if deg_min <= 180.0:
            unghi_rot_deg = deg_min
        else:
            unghi_rot_deg = deg_min - 360.0

        # Ne rotim direct spre perete
        if abs(unghi_rot_deg) > 4.0:
            directie = 1 if unghi_rot_deg > 0 else -1
            self._executa_viraj_intern(abs(unghi_rot_deg), directie)

        if self.stop_current_action:
            return

        # --- FAZA 2: Deplasare rapida spre perete ---
        self.get_logger().info('Faza 2: Avansez cu viteza marita spre perete...')
        viteza_rapida = 0.22
        dist_stop_perete = 0.42

        start_approach = time.time()
        while (time.time() - start_approach < 15.0) and not self.stop_current_action and rclpy.ok():
            d_front = self._get_sector_min(-20, 20, 1.0)
            if d_front <= dist_stop_perete:
                self.get_logger().info(f'Am ajuns la perete ({d_front:.2f}m)!')
                break

            self.trimite_viteza_instant(linear_x=viteza_rapida, angular_z=0.0)
            time.sleep(0.04)

        self.stop_robot()
        time.sleep(0.15)

        if self.stop_current_action:
            return

        # --- FAZA 3: Aliniere paralela cu peretele (viraj 90° stanga) ---
        self.get_logger().info('Faza 3: Mă aliniez paralel cu peretele...')
        self._executa_viraj_intern(90.0, directie=1)
        time.sleep(0.15)

        if self.stop_current_action:
            return

        # --- FAZA 4: Urmarirea peretelui (Right Wall Following) la viteza marita ---
        self.get_logger().info('Faza 4: Rulez de-a lungul peretelui arenei!')
        durata_tur = 60.0
        start_tur = time.time()
        d_tinta_perete = 0.38

        while (time.time() - start_tur < durata_tur) and not self.stop_current_action and rclpy.ok():
            if not self.latest_scan:
                time.sleep(0.04)
                continue

            d_f = self._get_sector_min(-25, 25, 2.0)
            d_fl = self._get_sector_min(25, 65, 2.0)
            d_fr = self._get_sector_min(285, 335, 2.0)
            d_r = self._get_sector_min(250, 285, 2.0)

            # Algoritm reactiv de navigatie cu protectie la colturi stranse si stalpi
            if d_f < 0.30:
                # Foarte aproape frontal -> rotire pe loc spre stanga (evita blocarea)
                lin = 0.0
                ang = 1.5
            elif d_f < 0.44 or d_fr < 0.33:
                # Obstacol sau colt frontal -> viraj stanga prompt
                lin = 0.08
                ang = 1.45
            elif d_fl < 0.28:
                # Prea aproape de un stalp in stanga-fata -> corecteaza usor dreapta
                lin = 0.12
                ang = -0.9
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
        if not self.stop_current_action:
            self.get_logger().info('🏆 Turul arenei a fost finalizat cu succes!')

    def animatie_joaca(self):
        """Dansul bucuriei: rotiri stanga-dreapta si o pirueta completa."""
        self.get_logger().info('🎉 Dansul fericirii!')

        self.trimite_viteza(linear_x=0.0, angular_z=1.8, durata_secunde=0.8)
        self.trimite_viteza(linear_x=0.0, angular_z=-1.8, durata_secunde=0.8)
        self.trimite_viteza(linear_x=0.10, angular_z=2.5, durata_secunde=1.2)

        self.stop_robot()

    def animatie_bucurie_mancare(self):
        """Miscare scurta inainte-inapoi (da din coada si multumeste)."""
        self.get_logger().info('🍖 Bucurie pentru mancare!')

        for _ in range(2):
            if self.stop_current_action:
                break
            self.trimite_viteza(linear_x=0.15, angular_z=0.0, durata_secunde=0.5)
            self.trimite_viteza(linear_x=-0.15, angular_z=0.0, durata_secunde=0.5)

        self.stop_robot()

    def animatie_trezire(self):
        """Trezire: intindere usoara si privire in jur."""
        self.get_logger().info('☀️ Trezire si intindere!')

        self.trimite_viteza(linear_x=0.05, angular_z=0.8, durata_secunde=0.6)
        self.trimite_viteza(linear_x=0.05, angular_z=-0.8, durata_secunde=0.6)

        self.stop_robot()

    def animatie_recunostinta(self):
        """Rotire blanda si inclinare de recunostinta."""
        self.trimite_viteza(linear_x=0.0, angular_z=0.8, durata_secunde=1.0)
        self.stop_robot()

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
