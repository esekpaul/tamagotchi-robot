#!/usr/bin/env python3
"""
Nodul de Stare Biologica (Tamagotchi State Node)
Proiect Sincretic: Robot Tamagotchi
Simuleaza ciclul biologic si nevoile de viata ale animatului robot:
1. Hrana (0-100%)
2. Energie (0-100%)
3. Fericire (0-100%)
4. Sanatate (0-100%)
5. Mod: Treaz / Adormit
Publica periodic starea pe /tamagotchi/status si reactioneaza la actiuni primite pe /tamagotchi/action.
"""

import json
import random
import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class TamagotchiStateNode(Node):
    def __init__(self):
        super().__init__('tamagotchi_state_node')

        # 1. Variabile de stare initiala
        self.hrana = 80       # Nivelul de satietate
        self.energie = 90     # Nivelul de energie
        self.fericire = 75    # Nivelul de buna dispozitie
        self.sanatate = 100   # Starea generala de sanatate
        self.este_adormit = False

        # 2. Topicuri ROS 2
        self.status_publisher = self.create_publisher(String, '/tamagotchi/status', 10)
        self.action_subscription = self.create_subscription(
            String,
            '/tamagotchi/action',
            self.action_callback,
            10
        )

        # 3. Timer pentru evolutia biologica in timp (la fiecare 3 secunde)
        self.timer_period = 3.0
        self.timer = self.create_timer(self.timer_period, self.life_cycle_tick)

        self.get_logger().info('=' * 60)
        self.get_logger().info('🧬 Nodul Tamagotchi State (Ciclul Biologic) a pornit!')
        self.get_logger().info('   - Publica starea la fiecare 3s pe: /tamagotchi/status')
        self.get_logger().info('   - Asculta actiuni pe: /tamagotchi/action')
        self.get_logger().info('=' * 60)

    def life_cycle_tick(self):
        """Simuleaza trecerea timpului si consumul metabolic de resurse."""
        if self.este_adormit:
            # In timpul somnului, energia si sanatatea se refac
            self.energie = min(100, self.energie + 6)
            self.hrana = max(0, self.hrana - 1)
            self.sanatate = min(100, self.sanatate + 2)

            if self.energie >= 100:
                self.este_adormit = False
                self.get_logger().info('☀️ Energia a atins 100%! Tamagotchi s-a trezit automat odihnit!')
        else:
            # Cand este treaz, consuma treptat resurse
            self.hrana = max(0, self.hrana - 1)
            self.fericire = max(0, self.fericire - 1)
            self.energie = max(0, self.energie - 1)

            # Daca e foarte infometat sau epuizat, sanatatea scade
            if self.hrana < 20 or self.energie < 15:
                self.sanatate = max(0, self.sanatate - 2)

        # Pachetul de stare in format JSON
        stare_dict = {
            'hrana': self.hrana,
            'energie': self.energie,
            'fericire': self.fericire,
            'sanatate': self.sanatate,
            'stare': 'doarme' if self.este_adormit else 'treaz'
        }

        msg = String()
        msg.data = json.dumps(stare_dict)
        self.status_publisher.publish(msg)

    def action_callback(self, msg: String):
        """Actualizeaza nevoile biologice in functie de actiunea executata."""
        actiune = msg.data.strip().lower()

        if actiune in ['feed', 'hrana', 'mananca']:
            self.hrana = min(100, self.hrana + 25)
            self.fericire = min(100, self.fericire + 10)
            self.get_logger().info(f'🍖 Tamagotchi a mancat cu pofta! (+25 Hrana={self.hrana}%, +10 Fericire={self.fericire}%)')

        elif actiune in ['play', 'joaca']:
            if self.este_adormit:
                self.get_logger().info('Robotul doarme! Trezeste-l mai intai pentru joaca.')
            elif self.energie < 15:
                self.get_logger().info('Robotul este prea epuizat pentru joaca. Pune-l la somn!')
            else:
                self.fericire = min(100, self.fericire + 25)
                self.energie = max(0, self.energie - 10)
                self.hrana = max(0, self.hrana - 5)
                self.get_logger().info(f'🎾 S-a jucat cu entuziasm! (+25 Fericire={self.fericire}%, -10 Energie={self.energie}%)')

        elif actiune in ['sleep', 'dormi', 'somn']:
            self.este_adormit = True
            self.get_logger().info('💤 Tamagotchi s-a culcat. (Refacere energie activa)')

        elif actiune in ['wake', 'trezire']:
            self.este_adormit = False
            self.get_logger().info('☀️ Tamagotchi s-a trezit!')

        elif actiune in ['heal', 'medicament', 'doctor']:
            self.sanatate = min(100, self.sanatate + 35)
            self.get_logger().info(f'💊 A primit medicament! (+35 Sanatate={self.sanatate}%)')

        elif actiune in ['arena_tour', 'turul_arenei', 'tura_arena', 'wall_follow']:
            if not self.este_adormit:
                self.fericire = min(100, self.fericire + 25)
                self.energie = max(0, self.energie - 15)
                self.get_logger().info(f'🏆 Turul arenei in executie! (+25 Fericire={self.fericire}%, -15 Energie={self.energie}%)')

        elif actiune.startswith('rotate') or actiune in ['forward', 'backward', 'forward_backward', 'turn_left', 'turn_right', 'inainte', 'inapoi', 'fata_spate', 'stanga', 'dreapta']:
            if not self.este_adormit:
                self.fericire = min(100, self.fericire + 10)
                self.energie = max(0, self.energie - 5)
                self.get_logger().info(f'🤸 Miscare executata: "{actiune}" (+10 Fericire={self.fericire}%, -5 Energie={self.energie}%)')

        elif actiune in ['stop', 'stai', 'oprire', 'frana']:
            self.get_logger().info('🛑 Oprire confirmata in State Node.')


def main(args=None):
    rclpy.init(args=args)
    node = TamagotchiStateNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
