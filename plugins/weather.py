from merlin_plugin_manager import MerlinPlugin
import requests

class WeatherPlugin(MerlinPlugin):
    def __init__(self):
        super().__init__("weather")
        
    def execute(self, city="New York"):
        # Using a free public API for demonstration
        try:
            url = f"https://wttr.in/{city}?format=j1"
            response = requests.get(url, timeout=10)
            data = response.json()
            current = data['current_condition'][0]
            temp = current['temp_C']
            desc = current['weatherDesc'][0]['value']
            return {"reply": f"The current weather in {city} is {desc} with a temperature of {temp}°C."}
        except Exception as e:
            return {"error": str(e)}

def get_plugin():
    return WeatherPlugin()
