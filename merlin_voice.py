import pyttsx3
import speech_recognition as sr
import logging

class MerlinVoice:
    def __init__(self):
        self.engine = pyttsx3.init()
        self.recognizer = sr.Recognizer()
        
    def speak(self, text):
        try:
            logging.info(f"Speaking: {text}")
            self.engine.say(text)
            self.engine.runAndWait()
            return True
        except Exception as e:
            logging.error(f"TTS Error: {e}")
            return False
            
    def listen(self):
        try:
            with sr.Microphone() as source:
                logging.info("Listening...")
                audio = self.recognizer.listen(source, timeout=5)
                text = self.recognizer.recognize_google(audio)
                logging.info(f"Recognized: {text}")
                return text
        except sr.WaitTimeoutError:
            logging.warning("Listening timed out")
            return None
        except Exception as e:
            logging.error(f"STT Error: {e}")
            return None

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    voice = MerlinVoice()
    voice.speak("Hello, I am Merlin. How can I help you today?")
