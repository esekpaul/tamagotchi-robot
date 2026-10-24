#!/usr/bin/env python3
"""
Nodul LLM, Chat si Comenzi Vocale (Tamagotchi LLM Node)
Proiect Sincretic: Robot Tamagotchi
Integreaza:
1. Normalizare si clasificare avansata a limbajului natural in limba romana (text & voce).
2. Recunoasterea impecabila a tuturor comenzilor (rotatii de N ori, turul arenei, miscari, nevoi biologice).
3. Conversatie inteligenta cu model local LLM (Qwen / LLaMA) prin llama-server.
4. Mod vocal (Push-to-Talk) si sinteza vocala (Text-to-Speech) in limba romana.
"""

import os
import re
import time
import json
import urllib.request
import subprocess
import threading
import unicodedata
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

        # Publicare comenzi si sinteza vocala
        self.action_pub = self.create_publisher(String, '/tamagotchi/action', 10)
        self.speech_pub = self.create_publisher(String, '/tamagotchi/speech', 10)

        self.get_logger().info('=' * 60)
        self.get_logger().info('🤖 Nodul Tamagotchi LLM & Voice a pornit cu succes!')
        self.get_logger().info('   - Asculta starea pe: /tamagotchi/status')
        self.get_logger().info('   - Asculta voce externa pe: /tamagotchi/user_input')
        self.get_logger().info('   - Trimite actiuni pe: /tamagotchi/action')
        self.get_logger().info('=' * 60)

        # Fir de executie pentru terminal interactiv
        self.chat_thread = threading.Thread(target=self.terminal_chat_loop, daemon=True)
        self.chat_thread.start()

    def ensure_llama_server(self):
        """Verifica daca serverul ruleaza sau il porneste automat."""
        try:
            req = urllib.request.Request(self.health_url)
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if resp.status == 200:
                    self.get_logger().info('llama-server ruleaza deja pe http://127.0.0.1:8080')
                    return
        except Exception:
            pass

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
            time.sleep(2.5)
            self.get_logger().info('llama-server a fost initializat cu succes!')

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

    def classify_intent(self, user_text: str):
        """
        Clasifica intentia utilizatorului cu maxima precizie folosind normalizarea limbii romane.
        Returneaza (raspuns_tamagotchi, cod_actiune).
        """
        norm = normalize_romanian(user_text)

        # 1. OPRIRE DE URGENTA / STOP
        if any(w in norm.split() for w in ['stop', 'stai', 'oprire', 'frana', 'franeaza']) or re.search(r'\boprest', norm):
            return "Ham! M-am oprit pe loc!", "stop"

        # 2. TURUL ARENEI (WALL FOLLOWING AUTONOM)
        pat_arena = r'\btur\w*\b.*?\baren\w*\b|\baren\w*\b.*?\btur\w*\b|pe\s+langa\s+perete|urmeaz\w*\s+perete|ocol\w*\s+arena|inconjoar\w*\s+arena|(?:da|fa)\s+(?:o|1)?\s*tur\w*'
        if re.search(pat_arena, norm):
            return "Ham ham! Merg la cel mai apropiat perete și încep turul arenei cu viteză mărită! Privește-mă!", "arena_tour"

        # 3. ROTATII (SPECIFICE sau SIMPLE)
        rot_roots = r'(?:rot|invart|rasuc|piruet|spin|titirez)'
        # Pattern A: rotatie urmata de N ori / rotatii (ex: "invarte-te de 10 ori", "rasuceste-te de 5 ori")
        mA = re.search(rot_roots + r'.*?(\d+)\s*(?:ori|rotati|rotiri|piruet|tur)', norm)
        if mA:
            nr = min(20, max(1, int(mA.group(1))))
            reply = "Ham! Fac o rotație completă pentru tine! Privește-mă!" if nr == 1 else f"Ham ham! Mă rotesc de {nr} ori plin de energie! Privește-mă!"
            return reply, f"rotate:{nr}"

        # Pattern B: N rotatii (ex: "fa 10 rotatii", "fa 5 rotiri", "fa 3 piruete")
        mB = re.search(r'(\d+)\s*(?:ori\s+)?' + rot_roots, norm)
        if mB:
            nr = min(20, max(1, int(mB.group(1))))
            reply = "Ham! Fac o rotație completă pentru tine! Privește-mă!" if nr == 1 else f"Ham ham! Mă rotesc de {nr} ori plin de energie! Privește-mă!"
            return reply, f"rotate:{nr}"

        # Pattern C: rotatie de N (ex: "roteste de 5", "invarte de 10")
        mC = re.search(rot_roots + r'.*?de\s+(\d+)', norm)
        if mC:
            nr = min(20, max(1, int(mC.group(1))))
            reply = "Ham! Fac o rotație completă pentru tine! Privește-mă!" if nr == 1 else f"Ham ham! Mă rotesc de {nr} ori plin de energie! Privește-mă!"
            return reply, f"rotate:{nr}"

        # Pattern D: rotatie simpla (fara numar specificat)
        if re.search(r'\b' + rot_roots, norm):
            return "Ham! Fac o rotație completă pentru tine!", "rotate:1"

        # 4. MISCARE FATA-SPATE
        if 'fata spate' in norm or 'inainte si inapoi' in norm or 'fata si spate' in norm:
            return "Ham ham! Mă plimb puțin înainte și înapoi!", "forward_backward"

        # 5. INAINTE / IN FATA
        if re.search(r'\b(?:in\s+fata|inainte|avanseaz\w*|fugi\s+in\s+fata|mergi\s+drept|hai\s+in\s+fata)\b', norm):
            return "Ham! Merg înainte cu atenție!", "forward"

        # 6. INAPOI / IN SPATE
        if re.search(r'\b(?:in\s+spate|inapoi|cu\s+spatele|marsarier|da\s+te\s+in\s+spate|da\s+te\s+inapoi)\b', norm):
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
        if re.search(r'\b(?:ce\s+faci|cum\s+esti|cum\s+te\s+simti|ce\s+mai\s+faci|iti\s+este\s+foame|esti\s+flamand|esti\s+obosit|esti\s+fericit|esti\s+sanatos)\b', norm):
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

        # Verificam daca intentia este o comanda directa cunoscuta
        reply, action = self.classify_intent(user_text)

        # Daca robotul doarme, refuzam miscarile pana este trezit
        if stare_somn == 'doarme' and action not in ['wake', 'heal', 'feed', 'sleep', 'stop', None]:
            reply = "Zzz... Sforăi... Robotul doarme adânc! Spune-mi 'Trezește-te!' mai întâi dacă vrei să mă mișc!"
            action = 'NONE'

        # Daca nu este o comanda directa, intrebam modelul LLM
        if not action or action == 'status':
            hrana = self.stare_curenta.get('hrana', 80)
            energie = self.stare_curenta.get('energie', 90)
            fericire = self.stare_curenta.get('fericire', 75)
            sanatate = self.stare_curenta.get('sanatate', 100)

            if action == 'status':
                pass  # pastram raspunsul formulat precis
            else:
                system_prompt = (
                    "Ești un cățeluș robot simpatic (un Tamagotchi inteligent și afectuos).\n"
                    f"Starea ta fizică acum: Hrană={hrana}%, Energie={energie}%, Fericire={fericire}%, Sănătate={sanatate}%, Stare={stare_somn}.\n"
                    "Reguli stricte:\n"
                    "1. Răspunde MEREU scurt, vesel și dragălaș în limba română (maxim 2 propoziții), ca un animăluț devotat ('Ham ham!').\n"
                    "2. Nu spune NICIODATĂ că ești o simulare sau un model AI. Ești un cățeluș robot real!\n"
                    "3. Pe ultima linie scrie: ACTIUNE: <FEED/PLAY/SLEEP/WAKE/HEAL/ROTATE:N/ARENA_TOUR/NONE>.\n"
                )
                llm_reply, llm_action = self.ask_llm(system_prompt, user_text)
                if llm_reply:
                    reply = llm_reply
                    action = llm_action

        if not reply:
            reply = "Ham ham! Sunt aici, animăluțul tău robot! Mă bucur să vorbim!"
            action = 'NONE'

        # Afisam in terminal
        print(f"\n🐶 Tamagotchi: {reply}")
        if action and action != 'NONE' and action != 'status':
            print(f"⚡ Actiune declansata: [{action.upper()}]")
        print("Tu: ", end="", flush=True)

        # Publicam ce zice robotul
        speech_msg = String()
        speech_msg.data = reply
        self.speech_pub.publish(speech_msg)

        # Transmitem actiunea fizica catre motion_node si state_node
        if action and action != 'NONE' and action != 'status':
            action_msg = String()
            action_msg.data = action.lower()
            self.action_pub.publish(action_msg)

        # Sinteza vocala TTS
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

                # Daca LLM a generat un raspuns rigid sau gol
                text_ciudat = any(w in clean_reply.lower() for w in ['nu are niciun', 'simulatie', 'model ai', 'nu pot face'])
                if not clean_reply or text_ciudat:
                    clean_reply = "Ham ham! Sunt cățelușul tău robot, gata de distracție!"

                return clean_reply, action
        except Exception:
            return None, 'NONE'

    def listen_microphone(self, durata_secunde=4.0):
        """Inregistreaza si transcrie comanda vocala in limba romana cu timp generos (4s)."""
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

    def speak_audio(self, text: str):
        """Reda raspunsul robotului vocal prin difuzoare (TTS)."""
        try:
            clean_text = re.sub(r'[^\w\s.,!?-]', '', text).strip()
            if clean_text:
                subprocess.Popen(['spd-say', '-l', 'ro', '-r', '15', clean_text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def terminal_chat_loop(self):
        """Bucla interactiva din terminal: tastatura sau comenzi vocale."""
        time.sleep(1.0)
        print("\n" + "=" * 70)
        print("🤖 TAMAGOTCHI AI & VOICE SUITE (Standard Profesional)")
        print("   👉 Scrie orice mesaj text SAU tastează 'v' pentru comandă VOCALĂ!")
        print("   Comenzi cheie de test:")
        print("   - 'Învârte-te de 10 ori' sau 'Răsucește-te de 5 ori' (Control precis!)")
        print("   - 'Dă turul arenei' (Navigație autonomă LiDAR la viteză mărită!)")
        print("   - 'Mergi în față' / 'Mergi în spate' / 'Virează la stânga/dreapta'")
        print("   - 'Hai la joacă!' / 'Ia un măr!' / 'Du-te la culcare' / 'Trezește-te!'")
        print("   - 'Stop' (Oprire de urgență pe loc)")
        print("=" * 70)

        while rclpy.ok():
            try:
                user_msg = input("\nTu (sau 'v' pt microfon): ").strip()
                if not user_msg:
                    continue

                if user_msg.lower() in ['v', 'mic', 'voce', 'rec']:
                    print("🔴 ASCULTĂM... Vorbește clar la microfon acum (4 secunde)!")
                    text_vocal = self.listen_microphone(durata_secunde=4.0)
                    if text_vocal:
                        print(f"🎤 Am auzit comanda: \"{text_vocal}\"")
                        self.process_message(text_vocal)
                    else:
                        print("⚠️ Nu am deslușit comanda. Asigură-te că microfonul este deschis și vorbește mai tare.")
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
