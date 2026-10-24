#!/usr/bin/env python3
"""
Nodul de Stare Interna (Tamagotchi State Node)
Proiect Sincretic: Robot Tamagotchi
"""

import json
import random
import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class TamagotchiStateNode(Node):
    def __init__(self):
        super().__init__('tamagotchi_state_node')

        # -------------------------------------------------------------
        # 1. Definirea celor 4 nevoi de baza (valori intre 0 si 100)
        # -------------------------------------------------------------
        self.hrana = 80       # Scade in timp; se reface cand mananca
        self.energie = 70     # Scade la miscare/veghe; se reface in somn
        self.fericire = 75    # Scade daca e ignorat; creste prin joc/interactiune
        self.sanatate = 100   # Scade daca foamea/energia sunt critice; se reface prin somn/medicamente

        # Stare comportamentala: 'treaz' sau 'doarme'
        self.este_adormit = False

        # -------------------------------------------------------------
        # 2. Topicuri ROS 2
        # -------------------------------------------------------------
        # Publicam starea la fiecare 2 secunde pe topicul /tamagotchi/status
        self.status_publisher = self.create_publisher(String, '/tamagotchi/status', 10)

        # Ascultam comenzi/actiuni de la utilizator sau LLM pe /tamagotchi/action
        self.action_subscription = self.create_subscription(
            String,
            '/tamagotchi/action',
            self.action_callback,
            10
        )

        # -------------------------------------------------------------
        # 3. Timer pentru evolutia biologica in timp (la fiecare 2 secunde)
        # -------------------------------------------------------------
        self.timer_period = 2.0  # secunde
        self.timer = self.create_timer(self.timer_period, self.life_cycle_tick)

        self.get_logger().info('Nodul Tamagotchi State a pornit cu succes!')
        self.get_logger().info('Publica starea pe topicul: /tamagotchi/status')
        self.get_logger().info('Asculta actiuni pe topicul: /tamagotchi/action')

    def life_cycle_tick(self):
        """Metoda apelata la fiecare 2 secunde pentru a simula trecerea timpului."""
        if self.este_adormit:
            # Cand doarme, energia se reface treptat
            self.energie = min(100, self.energie + 6)
            self.hrana = max(0, self.hrana - 1)
            # Somnul ajuta si la recuperarea sanatatii
            self.sanatate = min(100, self.sanatate + 2)

            # Daca energia a ajuns la 100%, se trezeste automat
            if self.energie >= 100:
                self.este_adormit = False
                self.get_logger().info('Robotul s-a trezit odihnit!')
        else:
            # Cand este treaz, consuma resurse in timp
            self.hrana = max(0, self.hrana - 2)
            self.fericire = max(0, self.fericire - 2)
            self.energie = max(0, self.energie - 1)

            # Daca e foarte flamand sau epuizat, sanatatea incepe sa fie afectata
            if self.hrana < 20 or self.energie < 15:
                self.sanatate = max(0, self.sanatate - 3)
            elif random.random() < 0.05:
                # O sansa mica aleatoare sa prinda o mica raceala
                self.sanatate = max(0, self.sanatate - 5)

        # Construim pachetul de stare in format JSON
        stare_dict = {
            'hrana': self.hrana,
            'energie': self.energie,
            'fericire': self.fericire,
            'sanatate': self.sanatate,
            'stare': 'doarme' if self.este_adormit else 'treaz'
        }

        # Publicam mesajul pe topic
        msg = String()
        msg.data = json.dumps(stare_dict)
        self.status_publisher.publish(msg)

        # Log informativ in consola
        stare_str = f"Hrana: {self.hrana}% | Energie: {self.energie}% | Fericire: {self.fericire}% | Sanatate: {self.sanatate}% [{stare_dict['stare']}]"
        self.get_logger().info(f'Status Tamagotchi -> {stare_str}')

    def action_callback(self, msg: String):
        """Primeste actiuni (ex: feed, play, sleep, heal) trimise din tastatura sau de LLM."""
        actiune = msg.data.strip().lower()
        self.get_logger().info(f'Am primit actiunea: "{actiune}"')

        if actiune in ['feed', 'hrana', 'mananca']:
            self.hrana = min(100, self.hrana + 25)
            self.fericire = min(100, self.fericire + 5)
            self.get_logger().info('Yum! Robotul a fost hranit. (+25 Hrana)')

        elif actiune in ['play', 'joaca']:
            if self.este_adormit:
                self.get_logger().info('Robotul doarme! Trezeste-l mai intai pentru joaca.')
            elif self.energie < 15:
                self.get_logger().info('Robotul este prea obosit pentru joaca...')
            else:
                self.fericire = min(100, self.fericire + 25)
                self.energie = max(0, self.energie - 10)
                self.hrana = max(0, self.hrana - 5)
                self.get_logger().info('Super distractie! (+25 Fericire, -10 Energie)')

        elif actiune in ['sleep', 'dormi', 'somn']:
            self.este_adormit = True
            self.get_logger().info('Zzz... Robotul s-a pus la somn.')

        elif actiune in ['wake', 'trezire']:
            self.este_adormit = False
            self.get_logger().info('Robotul s-a trezit!')

        elif actiune in ['heal', 'medicament', 'doctor']:
            self.sanatate = min(100, self.sanatate + 30)
            self.get_logger().info('Robotul a primit medicament! (+30 Sanatate)')

        elif actiune.startswith('rotate') or actiune in ['forward', 'backward', 'forward_backward', 'turn_left', 'turn_right', 'inainte', 'inapoi', 'fata_spate', 'stanga', 'dreapta']:
            if not self.este_adormit:
                self.fericire = min(100, self.fericire + 10)
                self.energie = max(0, self.energie - 5)
                self.get_logger().info(f'Activitate fizica executata: "{actiune}"! (+10 Fericire, -5 Energie)')

        else:
            self.get_logger().warn(f'Actiune necunoscuta: {actiune}.')


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
