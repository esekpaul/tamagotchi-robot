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
            "Ești un cățeluș robot simpatic (un Tamagotchi inteligent și afectuos).\n"
            f"Starea ta fizică acum: Hrană={hrana}%, Energie={energie}%, Fericire={fericire}%, Sănătate={sanatate}%, Stare={stare_somn}.\n"
            "Reguli stricte:\n"
            "1. Răspunde MEREU scurt, vesel și dragălaș în limba română (maxim 2 propoziții), ca un animăluț devotat ('Ham ham!').\n"
            "2. Nu spune NICIODATĂ că ești o simulare sau un model AI. Ești un cățeluș robot real!\n"
            "3. Pe ultima linie OBLIGATORIU scrie exact: ACTIUNE: <FEED/PLAY/SLEEP/WAKE/HEAL/ROTATE:N/FORWARD/BACKWARD/FORWARD_BACKWARD/TURN_LEFT/TURN_RIGHT/ARENA_TOUR/STOP/NONE>.\n"
        )

        # Daca este o comanda directa de miscare, reactionam instant fara intarziere
        direct_reply, direct_action = self.check_direct_commands(user_text)
        if direct_action:
            reply, action = direct_reply, direct_action
        else:
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

        # Sinteza vocala (Text-to-Speech) prin difuzoare
        self.speak_audio(reply)

    def check_direct_commands(self, user_text: str):
        """Detecteaza comenzi specifice de miscare pentru reactie instantanee pe robot."""
        u = user_text.lower().strip()

        # Dictionar pentru numere scrise ca text in limba romana
        num_cuvinte = {
            'o': 1, 'una': 1, 'un': 1, 'doua': 2, 'două': 2, 'trei': 3,
            'patru': 4, 'cinci': 5, 'sase': 6, 'șase': 6, 'sapte': 7,
            'șapte': 7, 'opt': 8, 'noua': 9, 'nouă': 9, 'zece': 10
        }

        # 1. Rotatie de N ori (ex: "roteste-te de 3 ori", "rotește te de trei ori", "invarte-te de 2 ori")
        pat_rot_n = r'(?:rot|inv[aâ]rt).*?(\d+|' + '|'.join(num_cuvinte.keys()) + r')\s+ori'
        m_rot = re.search(pat_rot_n, u)
        if m_rot:
            val = m_rot.group(1)
            nr = int(val) if val.isdigit() else num_cuvinte.get(val, 1)
            return f"Ham ham! Mă rotesc de {nr} ori plin de energie! Privește-mă!", f"rotate:{nr}"

        # 2. Rotatie simpla (ex: "roteste-te", "rotește te", "roteste", "rotește", "invarte-te", "pirueta")
        if re.search(r'\b(?:rot|inv[aâ]rt|piruet)', u):
            return "Ham! Fac o rotație completă pentru tine!", "rotate:1"

        # 3. Miscare fata-spate
        if re.search(r'fa[tț][aă].*spate', u):
            return "Ham ham! Mă plimb puțin înainte și înapoi!", "forward_backward"

        # 4. Mergi in fata / inainte
        if re.search(r'(?:in|în)\s*fa[tț][aă]|(?:in|în)ainte|avanseaz[aă]|mergi\s+drept', u):
            return "Ham! Merg înainte cu atenție!", "forward"

        # 5. Mergi in spate / inapoi
        if re.search(r'(?:in|în)\s*spate|(?:in|în)apoi|cu\s+spatele', u):
            return "Bip-bip-bip! Merg cu spatele!", "backward"

        # 6. Viraj stanga / dreapta
        if re.search(r'st[aâ]nga', u):
            return "Ham! Virez la stânga!", "turn_left"
        if re.search(r'dreapta', u):
            return "Ham! Virez la dreapta!", "turn_right"

        # 7. Turul arenei / Ocoleste arena pe langa perete
        pat_arena = r'tur\w*\s+(?:de\s+|a\s+)?aren\w*|aren\w*.*tur\w*|pe\s+l[aâ]ng[aă]\s+perete|urmeaz[aă]\s+perete|ocol(?:ește|este)\s+arena|inconjoar[aă]\s+arena|(?:da|dă|fa|fă)\s+(?:o\s+)?tur[aă]|turul\s+arenei'
        if re.search(pat_arena, u):
            return "Ham ham! Merg la cel mai apropiat perete și încep turul arenei cu viteză mărită! Privește-mă!", "arena_tour"

        # 8. Oprire / Stop pe loc
        if any(w in u for w in ['stop', 'stai', 'oprire', 'opreste-te', 'oprește-te', 'stai pe loc']):
            return "Ham! M-am oprit pe loc!", "stop"

        return None, None

    def ask_llm(self, system_prompt: str, user_text: str):
        """Interogheaza llama-server (OpenAI API local)."""
        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text}
            ],
            "max_tokens": 50,
            "temperature": 0.7
        }

        try:
            req = urllib.request.Request(
                self.server_url,
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode('utf-8'))
                raw_content = result['choices'][0]['message']['content'].strip()

                return self.parse_reply_and_action(raw_content, user_text)
        except Exception as e:
            self.get_logger().warn(f'Eroare comunicare llama-server: {e}. Folosesc raspuns de rezerva.')
            return self.fallback_response(user_text)

    def parse_reply_and_action(self, raw_content: str, user_text: str):
        """Extrage raspunsul curat si actiunea, prioritizand comenzi specifice."""
        u_lower = user_text.lower()

        # --- 1. COMANDĂ SPECIFICĂ: Rotație de N ori (ex: "rotește-te de 3 ori") ---
        m_rot = re.search(r'(?:rot(?:e[sș]te|i)|[iî]nv[aâ]rte)(?:-te)?(?:\s+de)?\s+(\d+)\s+ori', u_lower)
        if m_rot:
            nr = int(m_rot.group(1))
            return f"Ham ham! Mă rotesc de {nr} ori plin de energie! Privește-mă!", f"rotate:{nr}"

        # --- 2. Rotație simplă / Piruetă ---
        if any(w in u_lower for w in ['roteste-te', 'rotește-te', 'invarte-te', 'învârte-te', 'pirueta', 'piruetă']):
            return "Ham! Fac o piruetă completă pentru tine!", "rotate:1"

        # --- 3. Mișcare față-spate ---
        if any(w in u_lower for w in ['fata-spate', 'față-spate', 'fata spate', 'față spate']):
            return "Ham ham! Mă plimb puțin înainte și înapoi!", "forward_backward"

        # --- 4. Mergi în față / înainte ---
        if any(w in u_lower for w in ['in fata', 'în față', 'inainte', 'înainte', 'mergi inainte', 'mergi înainte']):
            return "Ham! Merg înainte cu atenție!", "forward"

        # --- 5. Mergi în spate / înapoi ---
        if any(w in u_lower for w in ['in spate', 'în spate', 'inapoi', 'înapoi', 'cu spatele']):
            return "Bip-bip-bip! Merg cu spatele!", "backward"

        # --- 6. Viraj stânga / dreapta ---
        if any(w in u_lower for w in ['la stanga', 'la stânga', 'spre stanga', 'spre stânga']):
            return "Ham! Virez la stânga!", "turn_left"
        if any(w in u_lower for w in ['la dreapta', 'spre dreapta']):
            return "Ham! Virez la dreapta!", "turn_right"

        # --- 7. Turul arenei / mers pe langa perete ---
        pat_arena = r'tur\w*\s+(?:de\s+|a\s+)?aren\w*|aren\w*.*tur\w*|pe\s+l[aâ]ng[aă]\s+perete|urmeaz[aă]\s+perete|ocol(?:ește|este)\s+arena|inconjoar[aă]\s+arena|(?:da|dă|fa|fă)\s+(?:o\s+)?tur[aă]|turul\s+arenei'
        if re.search(pat_arena, u_lower):
            return "Ham ham! Merg la cel mai apropiat perete și încep turul arenei cu viteză mărită! Privește-mă!", "arena_tour"

        # --- 8. Oprire / Stop ---
        if any(w in u_lower for w in ['stop', 'stai', 'oprire', 'opreste-te', 'oprește-te', 'stai pe loc']):
            return "Ham! M-am oprit pe loc!", "stop"

        # --- 9. Extragere din răspunsul LLM ---
        action = 'NONE'
        match = re.search(r'ACTIUNE:\s*([A-Za-z0-9_:]+)', raw_content, re.IGNORECASE)
        if match:
            action = match.group(1).upper()
            clean_reply = re.sub(r'ACTIUNE:\s*[A-Za-z0-9_:]+', '', raw_content, flags=re.IGNORECASE).strip()
        else:
            clean_reply = raw_content.strip()

        # Reguli suplimentare de siguranta daca modelul uita sa puna tag-ul
        if action == 'NONE':
            if any(w in u_lower for w in ['mananca', 'papa', 'mancare', 'hrana', 'mar', 'biscuit', 'pizza']):
                action = 'FEED'
            elif any(w in u_lower for w in ['joaca', 'minge', 'alearga', 'sari', 'prinde']):
                action = 'PLAY'
            elif any(w in u_lower for w in ['somn', 'culca-te', 'dormi', 'noapte buna', 'nani']):
                action = 'SLEEP'
            elif any(w in u_lower for w in ['trezeste-te', 'buna dimineata', 'scoala-te']):
                action = 'WAKE'
            elif any(w in u_lower for w in ['medicament', 'pastila', 'doctor', 'vindeca']):
                action = 'HEAL'

        # Daca textul este gol sau modelul a raspuns mecanic
        default_replies = {
            'PLAY': "Ham ham! Hai la joacă, abia așteptam să ne distrăm!",
            'FEED': "Ham! Mulțumesc mult pentru mâncărică, e delicioasă!",
            'SLEEP': "Zzz... noapte bună, mă pun la somn să-mi refac energia...",
            'WAKE': "Bună dimineața! M-am trezit plin de viață!",
            'HEAL': "Mulțumesc pentru doctorie, mă simt mult mai sănătos!",
            'FORWARD': "Ham! Merg înainte cu pași mărunți!",
            'BACKWARD': "Ham! Merg cu spatele!",
            'FORWARD_BACKWARD': "Ham ham! Mă plimb înainte și înapoi!",
            'ARENA_TOUR': "Ham ham! Merg la cel mai apropiat perete și încep turul arenei!",
            'STOP': "Ham! M-am oprit pe loc!"
        }

        # Curatare daca textul e gol sau are fraze rigide
        text_ciudat = any(w in clean_reply.lower() for w in ['nu are niciun', 'simulatie', 'model ai', 'nu pot face'])
        if not clean_reply or text_ciudat:
            if action in default_replies:
                clean_reply = default_replies[action]
            elif any(w in u_lower for w in ['ce faci', 'cum esti', 'ce mai faci']):
                hrana = self.stare_curenta.get('hrana', 50)
                energie = self.stare_curenta.get('energie', 50)
                clean_reply = f"Ham! Sunt vesel! Hrana mea e la {hrana}%, iar energia la {energie}%. Cu ce ne jucăm azi?"
            else:
                clean_reply = "Ham ham! Sunt aici, animăluțul tău robot! Mă bucur să vorbim!"

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

    def listen_microphone(self, durata_secunde=3):
        """Inregistreaza si transcrie comanda vocala in limba romana."""
        wav_path = '/tmp/tamagotchi_chat_voice.wav'
        cmd = ['arecord', '-d', str(durata_secunde), '-f', 'S16_LE', '-r', '16000', '-c', '1', wav_path]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            import speech_recognition as sr
            r = sr.Recognizer()
            with sr.AudioFile(wav_path) as source:
                audio = r.record(source)
            return r.recognize_google(audio, language='ro-RO').strip()
        except Exception:
            return None

    def speak_audio(self, text: str):
        """Reda raspunsul robotului vocal prin difuzoare (Text-to-Speech)."""
        try:
            clean_text = re.sub(r'[^\w\s.,!?-]', '', text).strip()
            if clean_text:
                subprocess.Popen(['spd-say', '-l', 'ro', '-r', '15', clean_text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def terminal_chat_loop(self):
        """Bucla interactiva din terminal: citeste tastatura sau comanda vocala."""
        time.sleep(1.0)
        print("\n" + "=" * 65)
        print("🤖 TAMAGOTCHI AI CHAT (Tastatură & Control Vocal)")
        print("   Scrie un mesaj text SAU tastează 'v' pentru comandă VOCALĂ!")
        print("   Exemple: 'Rotește-te de 3 ori', 'Mergi în față', 'Hai la joacă'")
        print("=" * 65)
        while rclpy.ok():
            try:
                user_msg = input("\nTu (sau 'v' pt microfon): ").strip()
                if not user_msg:
                    continue

                if user_msg.lower() in ['v', 'mic', 'voce', 'rec']:
                    print("🔴 ASCULT... Vorbește acum la microfon! (3 secunde)")
                    text_vocal = self.listen_microphone(durata_secunde=3)
                    if text_vocal:
                        print(f"🎤 Am auzit: \"{text_vocal}\"")
                        self.process_message(text_vocal)
                    else:
                        print("⚠️ Nu am deslușit ce ai spus. Încearcă din nou!")
                else:
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
