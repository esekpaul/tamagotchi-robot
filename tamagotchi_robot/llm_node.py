#!/usr/bin/env python3
"""
Nodul LLM, Chat si Comenzi Vocale (Tamagotchi LLM Node)
Proiect Sincretic: Robot Tamagotchi
Integreaza:
1. Meniu interactiv cu toate comenzile simplificate (text, scurtaturi numerice si voce).
2. Normalizare si clasificare avansata a limbajului natural in limba romana.
3. Recunoasterea impecabila a tuturor comenzilor (rotatii de N ori, turul arenei, miscari, nevoi biologice).
4. Control la cerere al camerei video (porneste camera / opreste camera) cu reactie fizica directa la zambet sau tristete.
5. Conversatie inteligenta cu model local LLM (Qwen / LLaMA) prin llama-server.
6. Mod vocal (Push-to-Talk) si sinteza vocala (Text-to-Speech) in limba romana.
"""

import os
import re
import time
import json
import urllib.request
import subprocess
import threading
import unicodedata
import numpy as np
import rclpy
from rclpy.node import Node
from std_msgs.msg import String


def normalize_romanian(text: str) -> str:
    """Normalizeaza textul in limba romana eliminand diacriticele si transformand numeralele in cifre."""
    t = text.lower()
    t = t.replace('ă', 'a').replace('â', 'a').replace('î', 'i').replace('ș', 's').replace('ț', 't')
    t = ''.join(c for c in unicodedata.normalize('NFD', t) if unicodedata.category(c) != 'Mn')
    t = re.sub(r'[^\w\s]', ' ', t)

    num_map = {
        'douazeci': '20',
        'nouasprezece': '19', 'nouaspe': '19',
        'optsprezece': '18', 'optspe': '18',
        'saptesprezece': '17', 'saptespe': '17',
        'saisprezece': '16', 'saispe': '16',
        'cincisprezece': '15', 'cinspe': '15',
        'paisprezece': '14', 'patrusprezece': '14', 'paispe': '14',
        'treisprezece': '13', 'treispe': '13',
        'doisprezece': '12', 'douasprezece': '12', 'doispe': '12',
        'unsprezece': '11', 'unspe': '11',
        'zece': '10',
        'noua': '9',
        'opt': '8',
        'sapte': '7',
        'sase': '6',
        'cinci': '5',
        'patru': '4',
        'trei': '3',
        'doua': '2', 'doi': '2',
        'una': '1', 'unu': '1', 'un': '1', 'o': '1'
    }

    words = t.split()
    converted = [num_map.get(w, w) for w in words]
    return ' '.join(converted)


class TamagotchiLLMNode(Node):
    def __init__(self):
        super().__init__('tamagotchi_llm_node')

        self.server_url = "http://127.0.0.1:8080/v1/chat/completions"
        self.health_url = "http://127.0.0.1:8080/health"
        self.llama_bin = os.path.expanduser("~/llama.cpp/build/bin/llama-server")
        self.model_path = os.path.expanduser("~/llama.cpp/models/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf")
        self.server_process = None

        # Verificam sau pornim llama-server
        self.ensure_llama_server()

        # Starea biologica curenta a Tamagotchi-ului
        self.stare_curenta = {
            'hrana': 80,
            'energie': 90,
            'fericire': 75,
            'sanatate': 100,
            'stare': 'treaz'
        }

        # Subscriptii
        self.status_sub = self.create_subscription(
            String,
            '/tamagotchi/status',
            self.status_callback,
            10
        )

        self.user_input_sub = self.create_subscription(
            String,
            '/tamagotchi/user_input',
            self.user_input_callback,
            10
        )

        # Subscriptie pentru recunoasterea emotiilor faciale
        self.latest_emotion = None
        self.latest_emotion_confidence = 0.0
        self.latest_emotion_time = 0.0
        self.camera_is_on = False
        self.is_recording_voice = False
        self.last_reacted_emotion = None
        self.last_emotion_reaction_time = 0.0

        self.emotion_sub = self.create_subscription(
            String,
            '/tamagotchi/emotion',
            self.emotion_callback,
            10
        )

        # Publicare comenzi, control camera si sinteza vocala
        self.action_pub = self.create_publisher(String, '/tamagotchi/action', 10)
        self.speech_pub = self.create_publisher(String, '/tamagotchi/speech', 10)
        self.vision_ctrl_pub = self.create_publisher(String, '/tamagotchi/vision_control', 10)

        self.get_logger().info('=' * 60)
        self.get_logger().info('🤖 Nodul Tamagotchi LLM & Voice a pornit cu succes!')
        self.get_logger().info('=' * 60)

        # Fir de executie pentru terminal interactiv
        self.chat_thread = threading.Thread(target=self.terminal_chat_loop, daemon=True)
        self.chat_thread.start()

    def print_menu(self):
        """Afiseaza meniul complet cu toate comenzile simplificate in terminal."""
        cam_status = "PORNITĂ 🟢" if self.camera_is_on else "OPRITĂ 🔴"
        print("\n" + "=" * 74)
        print("🤖 MENIU COMENZI SIMPLIFICATE — ROBOT TAMAGOTCHI")
        print("=" * 74)
        print(" 🕹️  [MIȘCARE & NAVIGAȚIE ÎN SIMULATOR]")
        print("   1  sau  fata            -> Mergi în față (cu protecție LiDAR)")
        print("   2  sau  spate           -> Mergi în spate")
        print("   3  sau  fata spate      -> Plimbare înainte și înapoi")
        print("   4  sau  stanga          -> Virează 90° la stânga")
        print("   5  sau  dreapta         -> Virează 90° la dreapta")
        print("   6  sau  invarte         -> Fă o rotație completă (360°)")
        print("   7  sau  invarte 5       -> Învârte-te de N ori (ex: invarte 3, invarte 10)")
        print("   8  sau  tur             -> Fă turul arenei autonom (LiDAR Wall-Follow)")
        print("   0  sau  stop            -> Oprire de urgență pe loc!")
        print("-" * 74)
        print(" 🐶 [NEVOI BIOLOGICE TAMAGOTCHI]")
        print("   9  sau  mananca         -> Hrănește robotul (+25% Hrană, +10% Fericire)")
        print("  10  sau  joaca           -> Dansul bucuriei (+25% Fericire)")
        print("  11  sau  dormi           -> Pune robotul la somn (reface energia)")
        print("  12  sau  trezirea        -> Trezește robotul")
        print("  13  sau  doctor          -> Dă-i medicament (+35% Sănătate)")
        print("  14  sau  stare           -> Afișează starea biologică curentă")
        print("-" * 74)
        print(f" 📷 [CAMERĂ AI & VOCE]  (Stare cameră: {cam_status})")
        print("   c  sau  porneste camera -> Pornește / Oprește camera (zâmbet=dans, trist=piruetă)")
        print("   v  sau  voce            -> Vorbește la microfon (4 secunde)")
        print("   m  sau  meniu           -> Afișează din nou acest meniu")
        print("=" * 74)

    def ensure_llama_server(self):
        """Verifica daca serverul ruleaza sau il porneste automat si asteapta sa devina activ."""
        if self._check_llama_health():
            self.get_logger().info('llama-server ruleaza deja pe http://127.0.0.1:8080')
            return

        if os.path.exists(self.llama_bin) and os.path.exists(self.model_path):
            self.get_logger().info('Pornim automat llama-server in fundal...')
            cmd = [
                self.llama_bin,
                "-m", self.model_path,
                "-c", "2048",
                "--port", "8080",
                "-t", "4",
                "-ngl", "0"
            ]
            self.server_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(24):
                time.sleep(0.5)
                if self._check_llama_health():
                    self.get_logger().info('llama-server a fost initializat cu succes!')
                    return
            self.get_logger().warn('llama-server a pornit, dar inca incarca modelul in fundal.')

    def _check_llama_health(self) -> bool:
        try:
            req = urllib.request.Request(self.health_url)
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def status_callback(self, msg: String):
        """Actualizeaza starea interna din state_node."""
        try:
            self.stare_curenta = json.loads(msg.data)
        except Exception:
            pass

    def user_input_callback(self, msg: String):
        """Primeste mesaje de la nodul extern de voce."""
        text = msg.data.strip()
        if text:
            print(f"\n[Microfon Extern]: {text}")
            self.process_message(text)

    def emotion_callback(self, msg: String):
        """
        Cand camera este PORNITA, conecteaza direct emotia detectata (zambet / tristete)
        cu reactia fizica a robotului in simulator!
        """
        try:
            data = json.loads(msg.data)
            new_emotion = data.get('emotion')

            if new_emotion == 'camera_closed':
                self.camera_is_on = False
                self.last_reacted_emotion = None
                return

            self.camera_is_on = True
            self.latest_emotion = new_emotion
            self.latest_emotion_confidence = data.get('confidence', 0.0)
            self.latest_emotion_time = time.time()

            if self.is_recording_voice or self.stare_curenta.get('stare') == 'doarme':
                return

            now = time.time()
            if new_emotion == 'neutral':
                self.last_reacted_emotion = 'neutral'
                return

            if (new_emotion != self.last_reacted_emotion) or (now - self.last_emotion_reaction_time > 7.0):
                if new_emotion == 'happy':
                    self.last_reacted_emotion = 'happy'
                    self.last_emotion_reaction_time = now
                    reply = "Ham ham! Te văd zâmbind! Hai să dansăm!"
                    action = "play"
                elif new_emotion == 'sad':
                    self.last_reacted_emotion = 'sad'
                    self.last_emotion_reaction_time = now
                    reply = "Ham... Te văd trist! Fac o piruetă să te înveselesc!"
                    action = "rotate:1"
                else:
                    return

                print(f"\n🐶 Tamagotchi: {reply}")
                print(f"⚡ Acțiune declanșată: [{action.upper()}]")
                print("Comandă ('m'=meniu, 'v'=voce, 'c'=cameră): ", end="", flush=True)

                speech_msg = String()
                speech_msg.data = reply
                self.speech_pub.publish(speech_msg)

                action_msg = String()
                action_msg.data = action
                self.action_pub.publish(action_msg)

                self.speak_audio(reply)
        except Exception:
            pass

    def send_vision_control(self, command: str):
        """Trimite o comanda ('start', 'stop', 'toggle') catre vision_node."""
        msg = String()
        msg.data = command
        self.vision_ctrl_pub.publish(msg)
        if command in ['start', 'on']:
            self.camera_is_on = True
            self.last_reacted_emotion = None
        elif command in ['stop', 'off']:
            self.camera_is_on = False
            self.last_reacted_emotion = None
        elif command == 'toggle':
            self.camera_is_on = not self.camera_is_on
            self.last_reacted_emotion = None

    def classify_intent(self, user_text: str):
        """
        Clasifica intentia utilizatorului cu maxima precizie folosind normalizarea limbii romane.
        Returneaza (raspuns_tamagotchi, cod_actiune).
        """
        norm = normalize_romanian(user_text).strip()

        # 0A. COMENZI EXPLICITE DE OPRIRE / INCHIDERE CAMERA
        pat_cam_off = (
            r'\b(?:oprest\w*|inchid\w*|dezactiveaz\w*|stinge|oprire)\s+(?:camera|video|webcam\w*)\b'
            r'|\b(?:camera|video)\s+(?:off|oprit\w*|inchis\w*)\b'
            r'|\bnu\s+ma\s+mai\s+privi\b'
        )
        if re.search(pat_cam_off, norm):
            return "CAMERA_OFF", "camera_off"

        # 0B. COMENZI DE PORNIRE CAMERA / CITIRE EXPRESIE FACIALA
        pat_cam_on = (
            r'\b(?:pornest\w*|deschid\w*|activeaz\w*|aprinde|pornire)\s+(?:camera|video|webcam\w*)\b'
            r'|\b(?:camera|video)\s+(?:on|pornit\w*|deschis\w*|activ\w*)\b'
            r'|\bpriveste\w*\b|\buita\s+te\s+la\s+mine\b|\bcum\s+arat\b'
            r'|\bce\s+emotie\s+am\b|\bciteste\s+(?:mi\s+)?(?:fata|expresia|emotia)\b'
            r'|\bvezi\s+fata\s+mea\b|\bscaneaza\s+(?:mi\s+)?fata\b|^camera$'
        )
        if re.search(pat_cam_on, norm):
            return "CAMERA_ON", "camera_on"

        # 1. OPRIRE DE URGENTA / STOP MOTOARE
        if any(w in norm.split() for w in ['stop', 'stai', 'oprire', 'frana', 'franeaza']) or re.search(r'\boprest', norm):
            return "Ham! M-am oprit pe loc!", "stop"

        # 2. TURUL ARENEI (WALL FOLLOWING AUTONOM)
        pat_arena = r'\btur\w*\b.*?\baren\w*\b|\baren\w*\b.*?\btur\w*\b|pe\s+langa\s+perete|urmeaz\w*\s+perete|ocol\w*\s+arena|inconjoar\w*\s+arena|(?:da|fa)\s+(?:o|1)?\s*tur\w*|^tur(?:ul|a)?$'
        if re.search(pat_arena, norm):
            return "Ham ham! Merg la cel mai apropiat perete și încep turul arenei cu viteză mărită! Privește-mă!", "arena_tour"

        # 3. ROTATII (SPECIFICE sau SIMPLE)
        rot_roots = r'(?:rot|invart|rasuc|piruet|spin|titirez)'
        mA = re.search(rot_roots + r'.*?(\d+)\s*(?:ori|rotati|rotiri|piruet|tur|dat)?', norm)
        if mA:
            nr = min(20, max(1, int(mA.group(1))))
            reply = "Ham! Fac o rotație completă pentru tine! Privește-mă!" if nr == 1 else f"Ham ham! Mă rotesc de {nr} ori plin de energie! Privește-mă!"
            return reply, f"rotate:{nr}"

        mB = re.search(r'(\d+)\s*(?:ori\s+)?' + rot_roots, norm)
        if mB:
            nr = min(20, max(1, int(mB.group(1))))
            reply = "Ham! Fac o rotație completă pentru tine! Privește-mă!" if nr == 1 else f"Ham ham! Mă rotesc de {nr} ori plin de energie! Privește-mă!"
            return reply, f"rotate:{nr}"

        if re.search(r'\b' + rot_roots, norm):
            return "Ham! Fac o rotație completă pentru tine!", "rotate:1"

        # 4. MISCARE FATA-SPATE
        if 'fata spate' in norm or 'inainte si inapoi' in norm or 'fata si spate' in norm:
            return "Ham ham! Mă plimb puțin înainte și înapoi!", "forward_backward"

        # 5. INAINTE / IN FATA (inclusiv comanda simpla 'fata' sau 'inainte')
        if re.search(r'\b(?:in\s+fata|inainte|avanseaz\w*|fugi\s+in\s+fata|mergi\s+drept|hai\s+in\s+fata|mergi\s+inainte)\b|^fata$|^mergi\s+fata$', norm):
            return "Ham! Merg înainte cu atenție!", "forward"

        # 6. INAPOI / IN SPATE (inclusiv comanda simpla 'spate' sau 'inapoi')
        if re.search(r'\b(?:in\s+spate|inapoi|cu\s+spatele|marsarier|da\s+te\s+in\s+spate|da\s+te\s+inapoi|mergi\s+inapoi|spate)\b', norm):
            return "Bip-bip-bip! Merg cu spatele!", "backward"

        # 7. VIRAJE STANGA / DREAPTA
        if re.search(r'\b(?:stanga|la\s+stanga|spre\s+stanga|vira\s+stanga)\b', norm):
            return "Ham! Virez la stânga!", "turn_left"
        if re.search(r'\b(?:dreapta|la\s+dreapta|spre\s+dreapta|vira\s+dreapta)\b', norm):
            return "Ham! Virez la dreapta!", "turn_right"

        # 8. HRANA / FEED
        if re.search(r'\b(?:mananc\w*|papa|mancar\w*|hrana|hranest\w*|mar|pizza|biscuit|bobite|os|pofta\s+buna)\b', norm):
            return "Ham! Mulțumesc mult pentru mâncărică, e delicioasă!", "feed"

        # 9. JOACA / PLAY
        if re.search(r'\b(?:joac\w*|ming\w*|prind\w*|alearg\w*|sari\w*|danseaz\w*|dans\w*|sa\s+ne\s+jucam)\b', norm):
            return "Ham ham! Hai la joacă, abia așteptam să ne distrăm!", "play"

        # 10. SOMN / SLEEP
        if re.search(r'\b(?:culc\w*|dorm\w*|somn|noapte\s+buna|nani|odihn\w*)\b', norm):
            return "Zzz... noapte bună, mă pun la somn să-mi refac energia...", "sleep"

        # 11. TREZIRE / WAKE
        if re.search(r'\b(?:trez\w*|buna\s+dimineata|scoal\w*|trezirea)\b', norm):
            return "Bună dimineața! M-am trezit plin de viață!", "wake"

        # 12. SANATATE / HEAL
        if re.search(r'\b(?:medicament\w*|pastil\w*|doctor\w*|vindec\w*|sirop\w*|vitamin\w*)\b', norm):
            return "Mulțumesc pentru doctorie, mă simt mult mai sănătos!", "heal"

        # 13. STATUS / INTREBARI DESPRE STARE
        if re.search(r'\b(?:ce\s+faci|cum\s+esti|cum\s+te\s+simti|ce\s+mai\s+faci|iti\s+este\s+foame|esti\s+flamand|esti\s+obosit|esti\s+fericit|esti\s+sanatos|stare|status)\b', norm):
            hrana = self.stare_curenta.get('hrana', 80)
            energie = self.stare_curenta.get('energie', 90)
            fericire = self.stare_curenta.get('fericire', 75)
            sanatate = self.stare_curenta.get('sanatate', 100)
            return f"Ham! Sunt vesel! Hrana mea este {hrana}%, energia {energie}%, sănătatea {sanatate}% și sunt {fericire}% fericit!", "status"

        return None, None

    def process_message(self, user_text: str):
        """Proceseaza mesajul (vocal sau text) al utilizatorului."""
        user_text = user_text.strip()
        if not user_text:
            return

        stare_somn = self.stare_curenta.get('stare', 'treaz')

        reply, action = self.classify_intent(user_text)

        if action == 'camera_on':
            self.send_vision_control('start')
            print("📷 [Cameră pornită]")
            return

        elif action == 'camera_off':
            self.send_vision_control('stop')
            print("📷 [Cameră oprită]")
            return

        if stare_somn == 'doarme' and action not in ['wake', 'heal', 'feed', 'sleep', 'stop', None]:
            reply = "Zzz... Sforăi... Robotul doarme adânc! Spune-mi 'Trezește-te!' (sau '12') mai întâi dacă vrei să mă mișc!"
            action = 'NONE'

        elif not action or action == 'status':
            hrana = self.stare_curenta.get('hrana', 80)
            energie = self.stare_curenta.get('energie', 90)
            fericire = self.stare_curenta.get('fericire', 75)
            sanatate = self.stare_curenta.get('sanatate', 100)

            if action == 'status':
                pass
            else:
                system_prompt = (
                    "Ești un cățeluș robot simpatic (un Tamagotchi inteligent și afectuos).\n"
                    f"Starea ta fizică acum: Hrană={hrana}%, Energie={energie}%, Fericire={fericire}%, Sănătate={sanatate}%, Stare={stare_somn}.\n"
                    "Reguli stricte:\n"
                    "1. Răspunde MEREU scurt, vesel și dragălaș în limba română (maxim 2 propoziții), ca un animăluț devotat ('Ham ham!').\n"
                    "2. Nu spune NICIODATĂ că ești o simulare sau un model AI. Ești un cățeluș robot real!\n"
                    "3. Pe ultima linie scrie: ACTIUNE: <FEED/PLAY/SLEEP/WAKE/HEAL/FORWARD/BACKWARD/TURN_LEFT/TURN_RIGHT/ROTATE:N/ARENA_TOUR/NONE>.\n"
                )
                llm_reply, llm_action = self.ask_llm(system_prompt, user_text)
                if llm_reply:
                    reply = llm_reply
                    action = llm_action

        if not reply:
            reply = "Ham ham! Sunt aici, animăluțul tău robot! Mă bucur să vorbim!"
            action = 'NONE'

        if action and action.lower() == 'wake':
            self.stare_curenta['stare'] = 'treaz'
        elif action and action.lower() == 'sleep':
            self.stare_curenta['stare'] = 'doarme'

        print(f"\n🐶 Tamagotchi: {reply}")
        if action and action not in ['NONE', 'status']:
            print(f"⚡ Acțiune declanșată: [{action.upper()}]")

        speech_msg = String()
        speech_msg.data = reply
        self.speech_pub.publish(speech_msg)

        if action and action not in ['NONE', 'status']:
            action_msg = String()
            action_msg.data = action.lower()
            self.action_pub.publish(action_msg)

        self.speak_audio(reply)

    def ask_llm(self, system_prompt: str, user_text: str):
        """Interogheaza llama-server local."""
        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text}
            ],
            "max_tokens": 60,
            "temperature": 0.7
        }

        try:
            req = urllib.request.Request(
                self.server_url,
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                result = json.loads(response.read().decode('utf-8'))
                raw_content = result['choices'][0]['message']['content'].strip()

                action = 'NONE'
                match = re.search(r'ACTIUNE:\s*([A-Za-z0-9_:]+)', raw_content, re.IGNORECASE)
                if match:
                    action = match.group(1).upper()
                    clean_reply = re.sub(r'ACTIUNE:\s*[A-Za-z0-9_:]+', '', raw_content, flags=re.IGNORECASE).strip()
                else:
                    clean_reply = raw_content.strip()

                text_ciudat = any(w in clean_reply.lower() for w in ['nu are niciun', 'simulatie', 'model ai', 'nu pot face'])
                if not clean_reply or text_ciudat:
                    clean_reply = "Ham ham! Sunt cățelușul tău robot, gata de distracție!"

                return clean_reply, action
        except Exception:
            return None, 'NONE'

    def listen_microphone(self, durata_secunde=4.0):
        """Inregistreaza si transcrie comanda vocala in limba romana."""
        self.is_recording_voice = True
        try:
            subprocess.run(['spd-say', '-S'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.15)
        except Exception:
            pass

        wav_path = '/tmp/tamagotchi_chat_voice.wav'
        cmd = [
            'arecord',
            '-d', str(int(durata_secunde)),
            '-f', 'S16_LE',
            '-r', '16000',
            '-c', '1',
            wav_path
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            import speech_recognition as sr
            r = sr.Recognizer()
            r.energy_threshold = 300
            r.dynamic_energy_threshold = True

            with sr.AudioFile(wav_path) as source:
                audio = r.record(source)

            text = r.recognize_google(audio, language='ro-RO')
            return text.strip()
        except Exception:
            return None
        finally:
            self.is_recording_voice = False

    def speak_audio(self, text: str):
        """Reda raspunsul robotului vocal prin difuzoare (TTS)."""
        try:
            clean_text = re.sub(r'[^\w\s.,!?-]', '', text).strip()
            if clean_text:
                subprocess.Popen(['spd-say', '-l', 'ro', '-r', '15', clean_text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def terminal_chat_loop(self):
        """Bucla interactiva din terminal cu meniu complet si scurtaturi."""
        time.sleep(1.0)
        self.print_menu()

        # Mapare scurtaturi numerice -> comenzi simplificate
        shortcuts = {
            '0': 'stop',
            '1': 'mergi in fata',
            '2': 'mergi in spate',
            '3': 'fata spate',
            '4': 'stanga',
            '5': 'dreapta',
            '6': 'invarte',
            '7': 'invarte 5',
            '8': 'fa turul arenei',
            '9': 'mananca',
            '10': 'joaca',
            '11': 'dormi',
            '12': 'trezirea',
            '13': 'doctor',
            '14': 'stare',
        }

        while rclpy.ok():
            try:
                user_msg = input("\nComandă ('m'=meniu, 'v'=voce, 'c'=cameră, 0-14 sau text): ").strip()
                if not user_msg:
                    continue

                low = user_msg.lower()
                if low in ['m', 'meniu', 'help', '?']:
                    self.print_menu()
                elif low in ['v', 'mic', 'voce', 'rec']:
                    print("🔴 ASCULTĂM... Vorbește clar la microfon acum (4 secunde)!")
                    text_vocal = self.listen_microphone(durata_secunde=4.0)
                    if text_vocal:
                        print(f"🎤 Am auzit comanda: \"{text_vocal}\"")
                        self.process_message(text_vocal)
                    else:
                        print("⚠️ Nu am deslușit comanda. Asigură-te că microfonul este deschis și vorbește mai tare.")
                elif low in ['c', 'cam']:
                    if not self.camera_is_on:
                        self.process_message("pornește camera")
                    else:
                        self.process_message("oprește camera")
                elif low in shortcuts:
                    self.process_message(shortcuts[low])
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
