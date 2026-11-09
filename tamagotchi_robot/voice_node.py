#!/usr/bin/env python3
"""
Nodul Dedicat de Comenzi Vocale (Tamagotchi Voice Node)
Proiect Sincretic: Robot Tamagotchi
Permite controlul vocal independent al robotului prin microfon:
- Inregistrare audio la calitate 16kHz prin ALSA (arecord).
- Transcriere automata a limbii romane prin Google Speech Recognition API.
- Publicare pe /tamagotchi/user_input pentru prelucrare inteligenta in llm_node.
"""

import os
import subprocess
import threading
import time
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

try:
    import speech_recognition as sr
    SPEECH_REC_AVAILABLE = True
except ImportError:
    SPEECH_REC_AVAILABLE = False


class TamagotchiVoiceNode(Node):
    def __init__(self):
        super().__init__('tamagotchi_voice_node')

        self.input_pub = self.create_publisher(String, '/tamagotchi/user_input', 10)
        self.audio_wav_path = '/tmp/tamagotchi_voice_input.wav'

        if not SPEECH_REC_AVAILABLE:
            self.get_logger().error('Pachetul SpeechRecognition nu este instalat!')
        else:
            self.get_logger().info('=' * 60)
            self.get_logger().info('🎙️ Modulul Dedicat de Recunoastere Vocala este activ!')
            self.get_logger().info('   Publica textul recunoscut pe: /tamagotchi/user_input')
            self.get_logger().info('=' * 60)

        self.voice_thread = threading.Thread(target=self.voice_loop, daemon=True)
        self.voice_thread.start()

    def record_audio(self, durata_secunde=4.0):
        """Inregistreaza audio de la microfon folosind arecord la 16kHz mono."""
        try:
            subprocess.run(['spd-say', '-S'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.15)
        except Exception:
            pass
        cmd = [
            'arecord',
            '-d', str(int(durata_secunde)),
            '-f', 'S16_LE',
            '-r', '16000',
            '-c', '1',
            self.audio_wav_path
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            return True
        except Exception as e:
            self.get_logger().warn(f'Eroare inregistrare microfon: {e}')
            return False

    def transcribe_audio(self):
        """Transcrie fisierul audio in limba romana cu adaptare la zgomot ambiental."""
        if not os.path.exists(self.audio_wav_path):
            return None

        r = sr.Recognizer()
        r.energy_threshold = 300
        r.dynamic_energy_threshold = True

        try:
            with sr.AudioFile(self.audio_wav_path) as source:
                audio = r.record(source)
            text = r.recognize_google(audio, language='ro-RO')
            return text.strip()
        except sr.UnknownValueError:
            return None
        except sr.RequestError as e:
            self.get_logger().warn(f'Eroare serviciu recunoastere vocala (lipsa internet?): {e}')
            return None
        except Exception as e:
            self.get_logger().warn(f'Eroare transcriere: {e}')
            return None

    def voice_loop(self):
        """Bucla interactiva: apasa Enter pentru a vorbi."""
        time.sleep(1.0)
        print("\n" + "=" * 65)
        print("🎙️  TAMAGOTCHI VOCAL CONSOLE (Limba Română)")
        print("   👉 Apasă [ENTER] și vorbește clar la microfon timp de 4 secunde!")
        print("   Exemple de comenzi vocale:")
        print("   - 'Învârte-te de 10 ori' / 'Răsucește-te de 5 ori'")
        print("   - 'Dă turul arenei' / 'Fă o tură de arenă'")
        print("   - 'Mergi în față' / 'Mergi în spate' / 'Virează la stânga'")
        print("   - 'Hai la joacă' / 'Ia un măr' / 'Du-te la culcare'")
        print("   - 'Stop' (Oprire imediată)")
        print("=" * 65)

        while rclpy.ok():
            try:
                input("\n👉 Apasă [ENTER] pentru a vorbi: ")
                print("🔴 ASCULTĂM... Vorbește acum la microfon (4 secunde)!")

                success = self.record_audio(durata_secunde=4.0)
                if not success:
                    print("❌ Nu am putut accesa microfonul dispozitivului.")
                    continue

                print("⏳ Procesez comanda...")
                text = self.transcribe_audio()

                if text:
                    print(f"✅ Comandă recunoscută: \"{text}\"")
                    msg = String()
                    msg.data = text
                    self.input_pub.publish(msg)
                else:
                    print("⚠️ Nu am deslușit comanda. Încearcă să vorbești mai tare sau mai aproape de microfon.")

            except (EOFError, KeyboardInterrupt):
                break


def main(args=None):
    rclpy.init(args=args)
    node = TamagotchiVoiceNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
