#!/usr/bin/env python3
"""
Nodul de Comenzi Vocale (Tamagotchi Voice Node)
Proiect Sincretic: Robot Tamagotchi
Asculta la microfon comenzi vocale in limba romana si le publica pe /tamagotchi/user_input
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

        # Publisher pentru comenzile vocale recunoscute
        self.input_pub = self.create_publisher(String, '/tamagotchi/user_input', 10)

        # Fisiere temporare audio
        self.audio_wav_path = '/tmp/tamagotchi_voice_input.wav'

        if not SPEECH_REC_AVAILABLE:
            self.get_logger().error('Pachetul SpeechRecognition nu este instalat!')
        else:
            self.get_logger().info('Modulul de Recunoastere Vocala este gata!')
            self.get_logger().info('Publica comenzile recunoscute pe: /tamagotchi/user_input')

        # Pornim firul de executie pentru ascultare Push-to-Talk
        self.voice_thread = threading.Thread(target=self.voice_loop, daemon=True)
        self.voice_thread.start()

    def record_audio(self, durata_secunde=4):
        """Inregistreaza audio de la microfon folosind arecord (ALSA nativ Linux)."""
        cmd = [
            'arecord',
            '-d', str(durata_secunde),
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
        """Transcreeaza fisierul audio in limba romana."""
        if not os.path.exists(self.audio_wav_path):
            return None

        r = sr.Recognizer()
        try:
            with sr.AudioFile(self.audio_wav_path) as source:
                audio = r.record(source)
            text = r.recognize_google(audio, language='ro-RO')
            return text.strip()
        except sr.UnknownValueError:
            return None
        except sr.RequestError as e:
            self.get_logger().warn(f'Eroare serviciu recunoastere vocala: {e}')
            return None
        except Exception as e:
            self.get_logger().warn(f'Eroare transcriere: {e}')
            return None

    def voice_loop(self):
        """Bucla interactiva: apasa Enter pentru a vorbi."""
        time.sleep(1.0)
        print("\n" + "=" * 60)
        print("🎙️  TAMAGOTCHI CONTROL VOCAL (Limba Romana)")
        print("   Apasă [ENTER] -> Vorbește la microfon timp de 3-4 secunde!")
        print("   Exemple vocale:")
        print("   - 'Rotește-te de trei ori'")
        print("   - 'Mergi în față'")
        print("   - 'Hai la joacă'")
        print("   - 'Ești flămând?'")
        print("=" * 60)

        while rclpy.ok():
            try:
                input("\n👉 Apasă [ENTER] și vorbește: ")
                print("🔴 ASCULT... Vorbește acum! (3 secunde)")
                
                success = self.record_audio(durata_secunde=3)
                if not success:
                    print("❌ Nu am putut accesa microfonul.")
                    continue

                print("⏳ Recunosc comanda...")
                text = self.transcribe_audio()

                if text:
                    print(f"✅ Ai spus: \"{text}\"")
                    # Publicam mesajul vocal pe topicul de intrare pentru robot
                    msg = String()
                    msg.data = text
                    self.input_pub.publish(msg)
                else:
                    print("⚠️ Nu am deslusit ce ai spus. Incearca sa vorbesti mai clar si mai aproape de microfon.")

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
