#!/usr/bin/env python3
"""
Nodul de Miscare si Comportamente Fizice (Tamagotchi Motion Node)
Proiect Sincretic: Robot Tamagotchi
Traduce actiunile primite de la LLM/Stare in miscari fizice pe topicul /cmd_vel (in Gazebo sau pe robot)
"""

import time
import threading
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from geometry_msgs.msg import Twist


class TamagotchiMotionNode(Node):
    def __init__(self):
        super().__init__('tamagotchi_motion_node')

        # Publisher pentru comenzile de viteza ale rotilor robotului
        self.cmd_vel_pub = self.create_publisher(Twist, '/cmd_vel', 10)

        # Subscriber pentru actiuni de la LLM sau state_node
        self.action_sub = self.create_subscription(
            String,
            '/tamagotchi/action',
            self.action_callback,
            10
        )

        self.animatie_in_curs = False

        self.get_logger().info('Nodul Tamagotchi Motion a pornit!')
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
            return

        # Pornim animatia potrivita intr-un thread separat ca sa nu blocam nodul
        if actiune in ['play', 'joaca']:
            threading.Thread(target=self.animatie_joaca, daemon=True).start()
        elif actiune in ['feed', 'hrana', 'mananca']:
            threading.Thread(target=self.animatie_bucurie_mancare, daemon=True).start()
        elif actiune in ['wake', 'trezire']:
            threading.Thread(target=self.animatie_trezire, daemon=True).start()
        elif actiune in ['heal', 'medicament']:
            threading.Thread(target=self.animatie_recunostinta, daemon=True).start()

    def animatie_joaca(self):
        """Dansul fericirii: se invarte vesel stanga-dreapta si face o pirueta."""
        self.animatie_in_curs = True
        self.get_logger().info('Animatie: Dansul fericirii (joaca)!')

        # 1. Rotatie rapida spre stanga
        self.trimite_viteza(linear_x=0.0, angular_z=1.8, durata_secunde=1.0)
        # 2. Rotatie rapida spre dreapta
        self.trimite_viteza(linear_x=0.0, angular_z=-1.8, durata_secunde=1.0)
        # 3. Pirueta completa
        self.trimite_viteza(linear_x=0.1, angular_z=2.5, durata_secunde=1.5)

        self.stop_robot()
        self.animatie_in_curs = False

    def animatie_bucurie_mancare(self):
        """Miscare inainte-inapoi (da din coada si multumeste)."""
        self.animatie_in_curs = True
        self.get_logger().info('Animatie: Multumire pentru mancare!')

        for _ in range(2):
            self.trimite_viteza(linear_x=0.12, angular_z=0.0, durata_secunde=0.5)
            self.trimite_viteza(linear_x=-0.12, angular_z=0.0, durata_secunde=0.5)

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
        msg = Twist()
        msg.linear.x = float(linear_x)
        msg.angular.z = float(angular_z)

        sfarsit = time.time() + durata_secunde
        while time.time() < sfarsit and rclpy.ok():
            self.cmd_vel_pub.publish(msg)
            time.sleep(0.05)

    def stop_robot(self):
        """Trimite viteza 0 pentru a opri rotile robotului."""
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
