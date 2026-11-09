#!/usr/bin/env python3
"""
Nodul de Viziune Artificiala si Recunoastere Emotionala Faciala (Controlabil la Cerere)
Proiect Sincretic: Robot Tamagotchi
Functionalitate:
1. Porneste implicit in modul STANDBY (camera oprita) pana cand utilizatorul o activeaza.
2. Asculta comenzi de control pe /tamagotchi/vision_control:
   - 'start' / 'on'   : Deschide camera (/dev/video0) si fereastra vizuala live.
   - 'stop'  / 'off'  : Inchide fereastra vizuala si elibereaza camera web.
   - 'toggle'         : Comuta intre pornit si oprit.
3. Clasifica expresia faciala (Fericit / Trist / Neutru) folosind Emotion-FERPlus (ONNX) + Haar Cascade.
4. Publica emotia detectata in timp real pe topicul /tamagotchi/emotion pentru reactia automata a robotului.
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

        # Topic pentru controlul camerei (start / stop / toggle)
        self.control_sub = self.create_subscription(
            String,
            '/tamagotchi/vision_control',
            self.control_callback,
            10
        )

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

        # Clase de emotie FERPlus: 0:neutral, 1:happiness, 2:surprise, 3:sadness, 4:anger, 5:disgust, 6:fear, 7:contempt
        self.emotion_labels = ['neutral', 'happiness', 'surprise', 'sadness', 'anger', 'disgust', 'fear', 'contempt']

        # Starea camerei (implicit OPRITA pana la comanda utilizatorului)
        self.cap = None
        self.camera_active = False
        self.window_name = "Tamagotchi Face Emotion Vision"

        # Memorie pentru stabilitatea emotiei
        self.history = []
        self.last_published_emotion = None
        self.last_published_time = 0.0

        self.get_logger().info('=' * 60)
        self.get_logger().info('👁️  Nodul Tamagotchi Vision este pregatit (Mod STANDBY - Camera Oprita).')
        self.get_logger().info('   - Controleaza camera pe: /tamagotchi/vision_control (start/stop/toggle)')
        self.get_logger().info('   - Publica emotiile pe: /tamagotchi/emotion')
        self.get_logger().info('=' * 60)

        # Timer procesare cadre la 10 FPS (ruleaza doar cand camera este activata)
        self.timer = self.create_timer(0.10, self.process_frame)

    def start_camera(self):
        """Deschide camera web si fereastra OpenCV."""
        if self.camera_active and self.cap and self.cap.isOpened():
            return True

        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            self.cap = cv2.VideoCapture(1)

        if not self.cap.isOpened():
            self.get_logger().error('Nu s-a putut deschide camera web (/dev/video0 sau /dev/video1)!')
            self.cap = None
            self.camera_active = False
            return False

        self.camera_active = True
        self.history.clear()
        self.last_published_emotion = None
        self.last_published_time = 0.0
        self.get_logger().info('🟢 Camera web a fost PORNITA!')
        return True

    def stop_camera(self):
        """Inchide fereastra OpenCV si elibereaza camera web."""
        was_active = self.camera_active
        if self.cap and self.cap.isOpened():
            self.cap.release()
        self.cap = None
        self.camera_active = False
        self.history.clear()
        self.last_published_emotion = None
        try:
            cv2.destroyWindow(self.window_name)
            cv2.destroyAllWindows()
            for _ in range(4):
                cv2.waitKey(1)
        except Exception:
            pass

        if was_active:
            msg = String()
            msg.data = json.dumps({'emotion': 'camera_closed', 'camera_active': False, 'timestamp': time.time()})
            self.emotion_pub.publish(msg)
            self.get_logger().info('🔴 Camera web a fost OPRITA.')

    def control_callback(self, msg: String):
        """Proceseaza comenzile de pornire/oprire a camerei."""
        cmd = msg.data.strip().lower()
        if cmd in ['start', 'on', 'open', 'porneste', 'deschide', 'snapshot']:
            self.start_camera()
        elif cmd in ['stop', 'off', 'close', 'opreste', 'inchide']:
            self.stop_camera()
        elif cmd == 'toggle':
            if self.camera_active:
                self.stop_camera()
            else:
                self.start_camera()

    def classify_face_emotion(self, face_gray):
        """Clasifica emotia fetei folosind reteaua neuronala ONNX si Haar smile booster."""
        h, w = face_gray.shape
        mouth_roi = face_gray[int(h * 0.55):h, :]
        smiles = self.smile_cascade.detectMultiScale(mouth_roi, scaleFactor=1.7, minNeighbors=20)
        has_smile = len(smiles) > 0

        if not self.net_available:
            if has_smile:
                return 'happy', 0.85
            return 'neutral', 0.5

        resized = cv2.resize(face_gray, (64, 64))
        blob = resized.astype(np.float32).reshape(1, 1, 64, 64)

        self.net.setInput(blob)
        preds = self.net.forward()[0]

        exp_preds = np.exp(preds - np.max(preds))
        probs = exp_preds / np.sum(exp_preds)
        idx_max = int(np.argmax(probs))
        label_raw = self.emotion_labels[idx_max]
        confidence = float(probs[idx_max])

        # Probabilitati agregate pentru sensibilitate ridicata la zambet si tristete
        pos_prob = float(probs[1] + probs[2])               # happiness + surprise
        neg_prob = float(np.sum(probs[3:]))                 # sadness + anger + disgust + fear + contempt

        if label_raw in ['happiness', 'surprise'] or has_smile or pos_prob >= 0.35:
            conf_out = max(confidence, pos_prob, 0.85 if has_smile else 0.75)
            return 'happy', min(0.99, conf_out)
        elif label_raw in ['sadness', 'anger', 'fear', 'disgust', 'contempt'] or neg_prob >= 0.22:
            conf_out = max(confidence, neg_prob, 0.75)
            return 'sad', min(0.99, conf_out)
        else:
            return 'neutral', confidence

    def process_frame(self):
        """Capteaza un cadru doar daca camera este activa, detecteaza fata si publica emotia."""
        if not self.camera_active:
            return

        if not self.cap or not self.cap.isOpened():
            self.stop_camera()
            return

        ret, frame = self.cap.read()
        if not ret:
            return

        frame = cv2.flip(frame, 1)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        small_gray = cv2.resize(gray, (0, 0), fx=0.5, fy=0.5)
        faces_small = self.face_cascade.detectMultiScale(
            small_gray,
            scaleFactor=1.2,
            minNeighbors=4,
            minSize=(40, 40)
        )

        if len(faces_small) > 0:
            faces = [(x*2, y*2, w*2, h*2) for (x, y, w, h) in faces_small]
            faces_sorted = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
            x, y, w, h = faces_sorted[0]
            face_roi_gray = gray[y:y+h, x:x+w]

            detected_emotion, confidence = self.classify_face_emotion(face_roi_gray)

            self.history.append(detected_emotion)
            if len(self.history) > 5:
                self.history.pop(0)

            dominant_emotion = max(set(self.history), key=self.history.count)

            if dominant_emotion == 'happy':
                color = (0, 230, 0)
                text_label = f"FERICIT / ZAMBITOR ({int(confidence*100)}%)"
            elif dominant_emotion == 'sad':
                color = (0, 100, 255)
                text_label = f"TRIST / SUPARAT ({int(confidence*100)}%)"
            else:
                color = (220, 220, 220)
                text_label = f"NEUTRU / CALM ({int(confidence*100)}%)"

            cv2.rectangle(frame, (x, y), (x+w, y+h), color, 3)
            cv2.rectangle(frame, (x, max(0, y - 35)), (x + w, y), color, -1)
            cv2.putText(frame, text_label, (x + 8, max(20, y - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.62, (0, 0, 0), 2, cv2.LINE_AA)

            # Publicam pe /tamagotchi/emotion imediat la schimbarea emotiei sau la fiecare 1.5s
            now = time.time()
            if (dominant_emotion != self.last_published_emotion or (now - self.last_published_time > 1.5)):
                msg = String()
                payload = {
                    'emotion': dominant_emotion,
                    'confidence': round(confidence, 2),
                    'face_detected': True,
                    'camera_active': True,
                    'timestamp': now
                }
                msg.data = json.dumps(payload)
                self.emotion_pub.publish(msg)
                self.last_published_emotion = dominant_emotion
                self.last_published_time = now
        else:
            self.history.clear()
            cv2.putText(frame, "Priveste spre camera pentru a-ti citi expresia...", (25, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.68, (0, 165, 255), 2, cv2.LINE_AA)

        h_frame, w_frame = frame.shape[:2]
        cv2.rectangle(frame, (0, h_frame - 40), (w_frame, h_frame), (25, 25, 25), -1)
        cv2.putText(frame, "Tamagotchi Emotion AI  |  Apasa 'q' sau scrie 'c' / 'opreste camera' pt inchidere",
                    (15, h_frame - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (200, 200, 200), 1, cv2.LINE_AA)

        try:
            cv2.imshow(self.window_name, frame)
            key = cv2.waitKey(1) & 0xFF
            if key in [ord('q'), 27]:
                self.stop_camera()
        except Exception:
            pass

    def destroy_node(self):
        self.stop_camera()
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
