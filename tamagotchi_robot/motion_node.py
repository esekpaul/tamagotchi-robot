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
from sensor_msgs.msg import LaserScan


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

        # Subscriber pentru LiDAR (/scan) pentru turul arenei si evitarea obstacolelor
        self.latest_scan = None
        self.scan_sub = self.create_subscription(
            LaserScan,
            '/scan',
            self.scan_callback,
            10
        )

        self.animatie_in_curs = False
        self.stop_current_action = False

        self.get_logger().info(f'Nodul Tamagotchi Motion a pornit! (Mod: {"TwistStamped" if self.use_stamped else "Twist"})')
        self.get_logger().info('Asculta actiuni pe: /tamagotchi/action')
        self.get_logger().info('Asculta senzor LiDAR pe: /scan')
        self.get_logger().info('Trimite miscari pe: /cmd_vel')

    def scan_callback(self, msg: LaserScan):
        """Salveaza ultima scanare LiDAR receptionata."""
        self.latest_scan = msg

    def action_callback(self, msg: String):
        actiune = msg.data.strip().lower()

        # Daca robotul doarme sau se cere oprirea, oprim orice miscare imediat
        if actiune in ['sleep', 'dormi', 'somn', 'stop', 'stai', 'oprire']:
            self.stop_current_action = True
            self.stop_robot()
            self.animatie_in_curs = False
            self.get_logger().info('Robotul s-a oprit pe loc.')
            return

        # Daca ruleaza deja o animatie, nu o intrerupem decat pentru sleep/stop
        if self.animatie_in_curs:
            self.get_logger().info(f'Ignor actiunea "{actiune}", o alta miscare este deja in curs.')
            return

        self.stop_current_action = False

        # --- Comanda speciala: Turul arenei (Wall Following) ---
        if actiune in ['arena_tour', 'turul_arenei', 'tura_arena', 'wall_follow']:
            threading.Thread(target=self.animatie_turul_arenei, daemon=True).start()
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

    def animatie_turul_arenei(self):
        """
        1. Identifica cel mai apropiat punct de peretele arenei folosind LiDAR (/scan).
        2. Se orienteaza cu fata spre acel perete.
        3. Avanseaza cu viteza marita pana la marginea arenei (~0.42m).
        4. Vreaza stanga la 90 grade (pozitionand peretele pe dreapta).
        5. Da turul arenei urmarind peretele (Right Wall Following) la viteza marita (~0.22 m/s).
        """
        self.animatie_in_curs = True
        self.stop_current_action = False
        self.get_logger().info('Incep comanda: TURUL ARENEI!')

        # Asteptam scanarea LiDAR daca nu este inca disponibila
        timeout_scan = time.time() + 3.0
        while self.latest_scan is None and time.time() < timeout_scan and not self.stop_current_action:
            time.sleep(0.05)

        if self.latest_scan is None or self.stop_current_action:
            self.get_logger().warn('Nu s-au receptionat date de la LiDAR (/scan) pentru turul arenei.')
            self.animatie_in_curs = False
            return

        # --- FAZA 1: Orientare spre cel mai apropiat perete ---
        self.get_logger().info('Faza 1: Caut cel mai apropiat perete al arenei...')
        ranges = list(self.latest_scan.ranges)
        curatate = []
        for idx, r in enumerate(ranges):
            if math.isnan(r) or math.isinf(r) or r < 0.12 or r > 5.0:
                curatate.append((100.0, idx))
            else:
                curatate.append((r, idx))

        dist_min, idx_min = min(curatate, key=lambda x: x[0])
        self.get_logger().info(f'Cel mai apropiat perete: {dist_min:.2f}m la unghiul de {idx_min} grade.')

        # Calculam unghiul relativ de rotatie
        if idx_min <= 180:
            unghi_rotatie_deg = float(idx_min)
        else:
            unghi_rotatie_deg = float(idx_min - 360)

        # Ne rotim cu fata spre cel mai apropiat perete
        if abs(unghi_rotatie_deg) > 5.0:
            directie = 1.0 if unghi_rotatie_deg > 0 else -1.0
            viteza_rot = 1.5 * directie
            durata_rot = abs(math.radians(unghi_rotatie_deg) / 1.5)
            self.get_logger().info(f'Ma rotesc spre perete: {unghi_rotatie_deg:.1f} grade ({durata_rot:.1f}s)...')
            self.trimite_viteza(linear_x=0.0, angular_z=viteza_rot, durata_secunde=durata_rot)

        if self.stop_current_action:
            self.stop_robot()
            self.animatie_in_curs = False
            return

        # --- FAZA 2: Inaintare spre perete la viteza marita ---
        self.get_logger().info('Faza 2: Avansez cu viteza marita spre perete...')
        viteza_inaintare = 0.22  # Viteza marita pentru TurtleBot3
        dist_tinta = 0.42       # Distanta tinta fata de perete (m)

        timp_start = time.time()
        while (time.time() - timp_start < 15.0) and not self.stop_current_action and rclpy.ok():
            if self.latest_scan:
                scan_ranges = self.latest_scan.ranges
                front_vals = []
                for i in range(-15, 16):
                    r = scan_ranges[i % 360]
                    if not (math.isnan(r) or math.isinf(r) or r < 0.12):
                        front_vals.append(r)
                d_front = min(front_vals) if front_vals else 1.0
            else:
                d_front = 1.0

            if d_front <= dist_tinta:
                self.get_logger().info(f'Am ajuns langa perete ({d_front:.2f}m)!')
                break

            self.trimite_viteza_instant(linear_x=viteza_inaintare, angular_z=0.0)
            time.sleep(0.05)

        self.stop_robot()
        time.sleep(0.2)

        if self.stop_current_action:
            self.animatie_in_curs = False
            return

        # --- FAZA 3: Aliniere paralela cu peretele (viraj stanga 90 grade) ---
        self.get_logger().info('Faza 3: Virez la stanga pentru a incepe turul cu peretele in dreapta...')
        durata_90 = (math.pi / 2.0) / 1.4
        self.trimite_viteza(linear_x=0.0, angular_z=1.4, durata_secunde=durata_90)
        self.stop_robot()
        time.sleep(0.2)

        if self.stop_current_action:
            self.animatie_in_curs = False
            return

        # --- FAZA 4: Turul propriu-zis al arenei (Wall Following) la viteza marita ---
        self.get_logger().info('Faza 4: Dau turul arenei pe langa perete!')
        durata_tur = 60.0  # Durata turului complet (secunde)
        start_tur = time.time()
        d_perete_dorita = 0.38

        while (time.time() - start_tur < durata_tur) and not self.stop_current_action and rclpy.ok():
            if not self.latest_scan:
                time.sleep(0.05)
                continue

            scan_ranges = self.latest_scan.ranges

            # Sector Frontal (-25..+25 grade)
            front_sector = [scan_ranges[i % 360] for i in range(-25, 26)
                            if not (math.isnan(scan_ranges[i % 360]) or math.isinf(scan_ranges[i % 360]) or scan_ranges[i % 360] < 0.12)]
            d_front = min(front_sector) if front_sector else 2.0

            # Sector Dreapta-Fata (285..330 grade)
            front_right_sector = [scan_ranges[i] for i in range(285, 331)
                                  if not (math.isnan(scan_ranges[i]) or math.isinf(scan_ranges[i]) or scan_ranges[i] < 0.12)]
            d_front_right = min(front_right_sector) if front_right_sector else 2.0

            # Sector Dreapta (250..285 grade)
            right_sector = [scan_ranges[i] for i in range(250, 286)
                            if not (math.isnan(scan_ranges[i]) or math.isinf(scan_ranges[i]) or scan_ranges[i] < 0.12)]
            d_right = min(right_sector) if right_sector else 2.0

            # Logica de control reactiv pe langa perete:
            if d_front < 0.42 or d_front_right < 0.32:
                # Se apropie de un colt de perete -> viraj spre stanga
                lin = 0.08
                ang = 1.4
            elif d_right < 0.28:
                # Prea aproape de peretele din dreapta -> corectie stanga
                lin = 0.20
                ang = 0.65
            elif d_right > 0.62:
                # Depasire de colt / perete prea departe -> cauta peretele spre dreapta
                lin = 0.16
                ang = -0.75
            else:
                # Viteza marita in linie dreapta de-a lungul peretelui
                eroare = d_right - d_perete_dorita
                ang = -1.6 * eroare
                ang = max(-0.8, min(0.8, ang))
                lin = 0.22

            self.trimite_viteza_instant(linear_x=lin, angular_z=ang)
            time.sleep(0.05)

        self.stop_robot()
        self.animatie_in_curs = False
        self.get_logger().info('Turul arenei s-a finalizat!')

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
        while time.time() < sfarsit and rclpy.ok() and not self.stop_current_action:
            self.trimite_viteza_instant(linear_x, angular_z)
            time.sleep(0.05)

    def trimite_viteza_instant(self, linear_x: float, angular_z: float):
        """Trimite un singur cadru de comanda de viteza."""
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
