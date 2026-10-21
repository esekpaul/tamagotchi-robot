#!/usr/bin/env python3
"""
Nodul LLM & Conversatie (Tamagotchi AI Brain)
Proiect Sincretic: Robot Tamagotchi
Conecteaza utilizatorul cu modelul local llama.cpp
"""

import json
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class TamagotchiLLMNode(Node):
    def __init__(self):
        super().__init__('tamagotchi_llm_node')

        # Cai catre executabile si model
        self.llama_bin_dir = os.path.expanduser('~/llama.cpp/build/bin')
        self.model_path = os.path.expanduser('~/llama.cpp/models/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf')
        self.server_url = 'http://127.0.0.1:8080/v1/chat/completions'
        self.server_process = None

        # Asiguram ca serverul llama-server ruleaza
        self.ensure_llama_server()

        # Starea curenta a robotului primita de la state_node
        self.stare_curenta = {
            'hrana': 80,
            'energie': 70,
            'fericire': 75,
            'sanatate': 100,
            'stare': 'treaz'
        }

        # -------------------------------------------------------------
        # Topicuri ROS 2
        # -------------------------------------------------------------
        # 1. Ascultam starea de la state_node
        self.status_sub = self.create_subscription(
            String,
            '/tamagotchi/status',
            self.status_callback,
            10
        )

        # 2. Ascultam mesaje text de la utilizator (daca vin din alt nod/topic)
        self.input_sub = self.create_subscription(
            String,
            '/tamagotchi/user_input',
            self.user_input_callback,
            10
        )

        # 3. Publicam actiunile decise catre state_node
        self.action_pub = self.create_publisher(String, '/tamagotchi/action', 10)

        # 4. Publicam ce zice robotul (pentru interfata / afisaj)
        self.speech_pub = self.create_publisher(String, '/tamagotchi/speech', 10)

        self.get_logger().info('Nodul Tamagotchi LLM a pornit!')
        self.get_logger().info('Asculta starea pe: /tamagotchi/status')
        self.get_logger().info('Trimite comenzi pe: /tamagotchi/action')

        # Pornim firul de executie pentru citirea textului din tastatura (Terminal Chat)
        self.chat_thread = threading.Thread(target=self.terminal_chat_loop, daemon=True)
        self.chat_thread.start()

    def ensure_llama_server(self):
        """Verifica daca llama-server e pornit pe 8080; daca nu, il porneste automat."""
        try:
            req = urllib.request.Request('http://127.0.0.1:8080/health')
            with urllib.request.urlopen(req, timeout=1) as resp:
                if resp.status == 200:
                    self.get_logger().info('llama-server ruleaza deja pe http://127.0.0.1:8080')
                    return
        except Exception:
            pass

        # Daca nu raspunde, pornim procesul llama-server
        server_bin = os.path.join(self.llama_bin_dir, 'llama-server')
        if os.path.exists(server_bin) and os.path.exists(self.model_path):
            self.get_logger().info('Pornim automat llama-server in fundal...')
            cmd = [
                server_bin,
                '-m', self.model_path,
                '--port', '8080',
                '-c', '2048'
            ]
            self.server_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            # Asteptam 2-3 secunde pana se initializeaza
            time.sleep(2.5)
            self.get_logger().info('llama-server a fost initializat cu succes!')
        else:
            self.get_logger().warn('Nu am gasit llama-server sau modelul. Se va incerca fallback.')

    def status_callback(self, msg: String):
        """Actualizeaza starea interna cand state_node publica modificari."""
        try:
            self.stare_curenta = json.loads(msg.data)
        except Exception as e:
            self.get_logger().error(f'Eroare la parsarea starii: {e}')

    def user_input_callback(self, msg: String):
        """Proceseaza un mesaj sosit prin topicul /tamagotchi/user_input."""
        self.process_message(msg.data)

    def process_message(self, user_text: str):
        """Trimite mesajul catre LLM, afiseaza raspunsul si trimite actiunea catre robot."""
        user_text = user_text.strip()
        if not user_text:
            return

        hrana = self.stare_curenta.get('hrana', 50)
        energie = self.stare_curenta.get('energie', 50)
        fericire = self.stare_curenta.get('fericire', 50)
        sanatate = self.stare_curenta.get('sanatate', 100)
        stare_somn = self.stare_curenta.get('stare', 'treaz')

        system_prompt = (
            "Tu esti un animalut de companie robot (un Tamagotchi inteligent).\n"
            f"Starea ta biologica curenta este: Hrana={hrana}%, Energie={energie}%, Fericire={fericire}%, Sanatate={sanatate}%, Mod={stare_somn}.\n"
            "Instructiuni obligatorii:\n"
            "1. Raspunde utilizatorului scurt, dragut si empatic in limba romana (maxim 2 fraze), ca un catelus/pisica robot.\n"
            "2. Pe ultima linie a raspunsului tau, scrie OBLIGATORIU actiunea corespunzatoare in formatul:\n"
            "   ACTIUNE: <FEED/PLAY/SLEEP/WAKE/HEAL/NONE>\n"
            "   - FEED: cand utilizatorul iti da mancare sau cand ceri hrana pentru ca iti e foame.\n"
            "   - PLAY: cand utilizatorul se joaca cu tine sau cand ai energie si vrei joaca.\n"
            "   - SLEEP: cand utilizatorul iti spune sa dormi sau cand esti foarte obosit.\n"
            "   - WAKE: cand utilizatorul te trezeste.\n"
            "   - HEAL: cand iei un medicament sau te vindeci.\n"
            "   - NONE: pentru o simpla vorba fara actiune specifica.\n"
        )

        reply, action = self.ask_llm(system_prompt, user_text)

        # Afisam in terminal
        print(f"\n🐶 Tamagotchi: {reply}")
        if action and action != 'NONE':
            print(f"⚡ Actiune declansata: [{action.upper()}]")
        print("Tu: ", end="", flush=True)

        # Publicam ce zice robotul pe topicul de vorbire
        speech_msg = String()
        speech_msg.data = reply
        self.speech_pub.publish(speech_msg)

        # Daca exista o actiune, o trimitem pe topicul /tamagotchi/action
        if action and action != 'NONE':
            action_msg = String()
            action_msg.data = action.lower()
            self.action_pub.publish(action_msg)

    def ask_llm(self, system_prompt: str, user_text: str):
        """Interogheaza llama-server (OpenAI API local)."""
        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text}
            ],
            "max_tokens": 120,
            "temperature": 0.7
        }

        try:
            req = urllib.request.Request(
                self.server_url,
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                result = json.loads(response.read().decode('utf-8'))
                raw_content = result['choices'][0]['message']['content'].strip()

                return self.parse_reply_and_action(raw_content, user_text)
        except Exception as e:
            self.get_logger().warn(f'Eroare comunicare llama-server: {e}. Folosesc raspuns de rezerva.')
            return self.fallback_response(user_text)

    def parse_reply_and_action(self, raw_content: str, user_text: str):
        """Extrage raspunsul curat si actiunea (FEED/PLAY/SLEEP/WAKE/HEAL/NONE)."""
        action = 'NONE'

        match = re.search(r'ACTIUNE:\s*([A-Za-z]+)', raw_content, re.IGNORECASE)
        if match:
            action = match.group(1).upper()
            clean_reply = re.sub(r'ACTIUNE:\s*[A-Za-z]+', '', raw_content, flags=re.IGNORECASE).strip()
        else:
            clean_reply = raw_content

        # Reguli suplimentare de siguranta daca modelul uita sa puna tag-ul
        u_lower = user_text.lower()
        if action == 'NONE':
            if any(w in u_lower for w in ['mananca', 'papa', 'mancare', 'hrana', 'mar', 'biscuit']):
                action = 'FEED'
            elif any(w in u_lower for w in ['joaca', 'minge', 'alearga', 'sari', 'prinde']):
                action = 'PLAY'
            elif any(w in u_lower for w in ['somn', 'culca-te', 'dormi', 'noapte buna', 'nani']):
                action = 'SLEEP'
            elif any(w in u_lower for w in ['trezeste-te', 'buna dimineata', 'scoala-te']):
                action = 'WAKE'
            elif any(w in u_lower for w in ['medicament', 'pastila', 'doctor', 'vindeca']):
                action = 'HEAL'

        return clean_reply, action

    def fallback_response(self, user_text: str):
        """Raspuns deterministic daca LLM-ul nu a raspuns."""
        u = user_text.lower()
        if 'mananca' in u or 'hrana' in u:
            return "Ham! Multumesc pentru mancare, e delicioasa!", "FEED"
        if 'joaca' in u or 'minge' in u:
            return "Ham ham! Imi place sa ma joc cu tine!", "PLAY"
        if 'dormi' in u or 'somn' in u:
            return "Zzz... ma pun la somn acum.", "SLEEP"
        if 'trez' in u:
            return "Ham! M-am trezit plin de energie!", "WAKE"
        if 'sanatate' in u or 'medicament' in u:
            return "Multumesc de doctorie, ma simt mai bine!", "HEAL"
        return "Ham! Te aud si sunt bucuros ca esti aici!", "NONE"

    def terminal_chat_loop(self):
        """Bucla interactiva din terminal: citeste tastatura utilizatorului."""
        time.sleep(1.0)
        print("\n==========================================================")
        print("🤖 TAMAGOTCHI AI CHAT (Scrie un mesaj si apasa Enter)")
        print("   Exemple: 'Iti este foame?', 'Ia un mar!', 'Hai la joaca!', 'Du-te la culcare'")
        print("==========================================================")
        while rclpy.ok():
            try:
                user_msg = input("\nTu: ")
                if user_msg.strip():
                    self.process_message(user_msg)
            except (EOFError, KeyboardInterrupt):
                break

    def destroy_node(self):
        if self.server_process:
            self.server_process.terminate()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = TamagotchiLLMNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
