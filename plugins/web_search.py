# Merlin Plugin: Web Search (The Omniscient Librarian)
import requests
from bs4 import BeautifulSoup
import os

class WebSearchPlugin:
    def __init__(self):
        self.name = "web_search"
        self.description = "Searches the internet for real-time information."
        self.category = "Intelligence"

    def execute(self, query: str):
        """Searches DuckDuckGo and scrapes results."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        url = f"https://html.duckduckgo.com/html/?q={query}"

        try:
            response = requests.get(url, headers=headers)
            if response.status_code != 200:
                return {"error": f"Search failed with status {response.status_code}"}

            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            for result in soup.find_all('div', class_='result__body', limit=5):
                title = result.find('a', class_='result__a').text
                snippet = result.find('a', class_='result__snippet').text
                link = result.find('a', class_='result__a')['href']
                results.append(f"Title: {title}\nSnippet: {snippet}\nLink: {link}")

            if not results:
                return {"output": "No results found for your query."}

            return {"output": "\n\n".join(results)}

        except Exception as e:
            return {"error": str(e)}

def get_plugin():
    return WebSearchPlugin()
