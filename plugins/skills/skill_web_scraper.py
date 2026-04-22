import time
import urllib.request
import re
from plugins.intelligence import Intelligence

class WebScraperSkill(Intelligence):
    """
    Skill: WebScraper
    Domain: Intelligence
    
    A native python function using urllib to fetch a URL, strip HTML tags using regex, and return clean text content.
    """
    
    @property
    def capabilities(self) -> list[str]:
        return ["aaroneousautomationsuite_intelligence_web_scraper"]

    async def handle_message(self, capability_id: str, payload: dict) -> dict:
        start_time = time.time()
        
        if capability_id != "aaroneousautomationsuite_intelligence_web_scraper":
            return self._format_error(capability_id, "Unhandled capability.")
            
        url = payload.get("url")
        if not url:
            return self._format_error(capability_id, "Missing 'url' parameter.")
            
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'AAS-Distilled-Agent/1.0'})
            with urllib.request.urlopen(req) as response:
                html_content = response.read().decode('utf-8')
                
            # Strip HTML using regex (Zero-Bloat, no BeautifulSoup)
            clean_text = re.sub('<[^<]+?>', '', html_content)
            # Clean up whitespace
            clean_text = re.sub('\s+', ' ', clean_text).strip()
            
            result = {
                "url": url,
                "content_length": len(clean_text),
                "text": clean_text[:1000] # Return first 1000 chars safely
            }
            
            return self._format_success(capability_id, result, start_time)
            
        except Exception as e:
            return self._format_error(capability_id, str(e))
