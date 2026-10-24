#!/usr/bin/env python3
"""
Nodul de Viziune Artificiala si Recunoastere Emotionala Faciala
Proiect Sincretic: Robot Tamagotchi
Functionalitate:
1. Acceseaza camera laptopului (/dev/video0).
2. Detecteaza fata utilizatorului in timp real (Haar Cascade).
3. Clasifica expresia faciala (Fericit / Trist / Neutru / Surprins) folosind reteaua neuronala profunda Emotion-FERPlus (ONNX).
4. Publica emotia detectata pe topicul /tamagotchi/emotion.
5. Afiseaza o interfata vizuala interactiva cu dreptunghi colorat si emoji corespunzator starii.
"""

import os
import time
import json
import numpy as np
import cv2
import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class TamagotchiVisionNode(Node):
    def __init__(self):
        super().__init__('tamagotchi_vision_node')

        # Topic pentru publicarea emotiei detectate
        self.emotion_pub = self.create_publisher(String, '/tamagotchi/emotion', 10)

        # Cai fisiere modele
        models_dir = os.path.expanduser('~/ros2_ws/src/tamagotchi_robot/models')
        self.onnx_model_path = os.path.join(models_dir, 'emotion-ferplus-8.onnx')
        self.face_cascade_path = '/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml'
        self.smile_cascade_path = '/usr/share/opencv4/haarcascades/haarcascade_smile.xml'

        # Initializare detectori
        self.face_cascade = cv2.CascadeClassifier(self.face_cascade_path)
        self.smile_cascade = cv2.CascadeClassifier(self.smile_cascade_path)

        # Incarcare retea neuronala ONNX (Emotion-FERPlus)
        if os.path.exists(self.onnx_model_path):
            self.net = cv2.dnn.readNetFromONNX(self.onnx_model_path)
            self.net_available = True
            self.get_logger().info('Modelul neuronal profund Emotion-FERPlus (ONNX) a fost incarcat cu succes!')
        else:
            self.net_available = False
            self.get_logger().warn('Fisierul ONNX nu a fost gasit, folosesc detectorul geometric Haar!')

        # Clase de emotie FERPlus: 0: neutral, 1: happiness, 2: surprise, 3: sadness, 4: anger, 5: disgust, 6: fear, 7: contempt
        self.emotion_labels = ['neutral', 'happiness', 'surprise', 'sadness', 'anger', 'disgust', 'fear', 'contempt']

        # Initializare camera web
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            self.cap = cv2.VideoCapture(1)

        if not self.cap.isOpened():
            self.get_logger().error('Nu s-a putut deschide nicio camera web (/dev/video0 sau /dev/video1)!')
        else:
            self.get_logger().info('=' * 60)
            self.get_logger().info('👁️  Nodul Tamagotchi Vision a pornit camera laptopului!')
            self.get_logger().info('   Publica emotiile detectate pe: /tamagotchi/emotion')
            self.get_logger().info('=' * 60)

        # Memorie pentru stabilitatea emotiei (evita fluctuatiile bruste)
        self.history = []
        self.last_published_emotion = None
        self.last_published_time = 0.0

        # Timer procesare cadre la 10 FPS (echilibru optim intre fluiditate si consum redus CPU)
        self.timer = self.create_timer(0.10, self.process_frame)

    def classify_face_emotion(self, face_gray):
        """Clasifica emotia fetei folosind reteaua neuronala ONNX si Haar smile booster."""
        if not self.net_available:
            return 'neutral', 0.5

        # Redimensionare la 64x64 conform specificatiilor Emotion-FERPlus
        resized = cv2.resize(face_gray, (64, 64))
        blob = resized.astype(np.float32).reshape(1, 1, 64, 64)

        self.net.setInput(blob)
        preds = self.net.forward()[0]

        # Calcul probabilitati prin Softmax
        exp_preds = np.exp(preds - np.max(preds))
        probs = exp_preds / np.sum(exp_preds)
        idx_max = int(np.argmax(probs))
        label_raw = self.emotion_labels[idx_max]
        confidence = float(probs[idx_max])

        # Verificare suplimentara pentru zambet (Haar Smile)
        # In jumatatea inferioara a fetei (regiunea gurii)
        h, w = face_gray.shape
        mouth_roi = face_gray[int(h * 0.55):h, :]
        smiles = self.smile_cascade.detectMultiScale(mouth_roi, scaleFactor=1.7, minNeighbors=20)
        has_smile = len(smiles) > 0

        # Mapeaza in categoriile cheie: 'happy', 'sad', 'neutral'
        if label_raw in ['happiness', 'surprise'] or has_smile:
            return 'happy', max(confidence, 0.85 if has_smile else confidence)
        elif label_raw in ['sadness', 'anger', 'fear', 'disgust', 'contempt']:
            return 'sad', confidence
        else:
            return 'neutral', confidence

    def process_frame(self):
        """Capteaza un cadru, detecteaza fata, clasifica emotia si afiseaza interfata."""
        if not self.cap or not self.cap.isOpened():
            return

        ret, frame = self.cap.read()
        if not ret:
            return

        # Oglindim cadrul pe orizontala (efect natural de oglinda)
        frame = cv2.flip(frame, 1)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Optimizare CPU: detectie faciala pe rezolutie scalata la 50%
        small_gray = cv2.resize(gray, (0, 0), fx=0.5, fy=0.5)
        faces_small = self.face_cascade.detectMultiScale(
            small_gray,
            scaleFactor=1.2,
            minNeighbors=4,
            minSize=(40, 40)
        )

        detected_emotion = 'none'
        confidence = 0.0

        if len(faces_small) > 0:
            # Rescalam coordonatele la dimensiunea originala
            faces = [(x*2, y*2, w*2, h*2) for (x, y, w, h) in faces_small]
            faces_sorted = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
            x, y, w, h = faces_sorted[0]
            face_roi_gray = gray[y:y+h, x:x+w]

            detected_emotion, confidence = self.classify_face_emotion(face_roi_gray)

            # Istoric pentru filtrare zgomot
            self.history.append(detected_emotion)
            if len(self.history) > 6:
                self.history.pop(0)

            # Emotia dominanta din istoric
            dominant_emotion = max(set(self.history), key=self.history.count)

            # Configurare culori si etichete
            if dominant_emotion == 'happy':
                color = (0, 230, 0)      # Verde vibrant
                text_label = f"FERICIT / ZAMBITOR ({int(confidence*100)}%)"
                emoji_icon = "😊"
            elif dominant_emotion == 'sad':
                color = (0, 100, 255)    # Portocaliu / Albastru
                text_label = f"TRIST / SUPARAT ({int(confidence*100)}%)"
                emoji_icon = "😢"
            else:
                color = (220, 220, 220)  # Gri deschis
                text_label = f"NEUTRU / CALM ({int(confidence*100)}%)"
                emoji_icon = "😐"

            # Desenare chenar fata si eticheta
            cv2.rectangle(frame, (x, y), (x+w, y+h), color, 3)

            # Bara de eticheta eleganta deasupra fetei
            cv2.rectangle(frame, (x, y - 35), (x + w, y), color, -1)
            cv2.putText(frame, text_label, (x + 8, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 2, cv2.LINE_AA)

            # Publicam pe topic daca s-a schimbat starea sau la interval de 2 secunde
            now = time.time()
            if (dominant_emotion != self.last_published_emotion or (now - self.last_published_time > 2.0)):
                msg = String()
                payload = {
                    'emotion': dominant_emotion,
                    'confidence': round(confidence, 2),
                    'face_detected': True,
                    'timestamp': now
                }
                msg.data = json.dumps(payload)
                self.emotion_pub.publish(msg)
                self.last_published_emotion = dominant_emotion
                self.last_published_time = now
        else:
            self.history.clear()
            cv2.putText(frame, "Priveste spre camera pentru a-ti citi expresia...", (30, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2, cv2.LINE_AA)

        # Banner informativ in partea de jos
        cv2.rectangle(frame, (0, frame.shape[0] - 40), (frame.shape[0] + 200, frame.shape[0]), (25, 25, 25), -1)
        cv2.putText(frame, "Tamagotchi Facial Emotion AI  |  Apasa 'q' pentru a inchide fereastra",
                    (15, frame.shape[0] - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (200, 200, 200), 1, cv2.LINE_AA)

        # Afisare fereastra video
        try:
            cv2.imshow("Tamagotchi Face Emotion Vision", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                self.destroy_node()
                rclpy.shutdown()
        except Exception:
            pass

    def destroy_node(self):
        if self.cap and self.cap.isOpened():
            self.cap.release()
        cv2.destroyAllWindows()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = TamagotchiVisionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
