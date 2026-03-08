# Task 81: Dashboard delivery bridge for static React or fallback HTML UI.
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import os
from merlin_metrics_dashboard import metrics_dashboard


def setup_dashboard(app: FastAPI):
    # Serve static files when a frontend build is present.
    if os.path.exists("frontend/dist"):
        app.mount(
            "/dashboard",
            StaticFiles(directory="frontend/dist", html=True),
            name="dashboard",
        )
    else:

        @app.get("/dashboard", response_class=HTMLResponse)
        async def dashboard_fallback():
            return """
            <html>
                <head>
                    <title>Merlin Dashboard</title>
                    <style>
                        :root { --bg: #f0f2f5; --card: white; --text: black; --primary: #1a73e8; }
                        body.dark { --bg: #121212; --card: #1e1e1e; --text: #e0e0e0; --primary: #8ab4f8; }
                        body { font-family: sans-serif; margin: 20px; background: var(--bg); color: var(--text); transition: background 0.3s, color 0.3s; }
                        .card { background: var(--card); padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }
                        h1 { color: var(--primary); }
                        h2 { border-bottom: 1px solid #eee; padding-bottom: 10px; }
                        .status-ok { color: green; font-weight: bold; }
                        .status-fail { color: red; font-weight: bold; }
                        pre { background: rgba(0,0,0,0.05); padding: 10px; border-radius: 4px; overflow-x: auto; color: var(--text); }
                        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
                        button { cursor: pointer; }
                    </style>
                </head>
                <body>
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <h1>Merlin Merlin Dashboard</h1>
                        <button onclick="toggleDarkMode()" style="padding: 10px;">Toggle Dark Mode</button>
                    </div>
                    
                    <div class="grid">
                        <div class="card">
                            <h2>System Health</h2>
                            <div id="health">Loading...</div>
                        </div>
                        <div class="card">
                            <h2>System Info</h2>
                            <div id="sysinfo">Loading...</div>
                        </div>
                    </div>

                    <div class="card">
                        <h2>Active Plugins</h2>
                        <div id="plugins">Loading...</div>
                    </div>

                    <div class="card">
                        <h2>Recent Tasks</h2>
                        <div id="tasks">Loading...</div>
                    </div>

                    <div class="card">
                        <h2>Merlin Chat (Real-time)</h2>
                        <div id="chat-box" style="height: 200px; border: 1px solid #ccc; padding: 10px; overflow-y: scroll; margin-bottom: 10px;"></div>
                        <input type="text" id="chat-input" style="width: 80%; padding: 10px;" placeholder="Type a message...">
                        <button onclick="sendMessage()" style="padding: 10px;">Send</button>
                    </div>

                    <script>
                        let ws;
                        const apiKey = localStorage.getItem('MERLIN_API_KEY') || 'merlin-secret-key';
                        function toggleDarkMode() {
                            document.body.classList.toggle('dark');
                            localStorage.setItem('darkMode', document.body.classList.contains('dark'));
                        }
                        if (localStorage.getItem('darkMode') === 'true') document.body.classList.add('dark');

                        function connectWS() {
                            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                            ws = new WebSocket(`${protocol}//${window.location.host}/ws/chat?api_key=${encodeURIComponent(apiKey)}`);
                            ws.onmessage = (event) => {
                                const chatBox = document.getElementById('chat-box');
                                if (event.data === '[DONE]') {
                                    chatBox.innerHTML += '<br>';
                                } else {
                                    chatBox.innerHTML += event.data;
                                }
                                chatBox.scrollTop = chatBox.scrollHeight;
                            };
                            ws.onclose = () => setTimeout(connectWS, 3000);
                        }
                        connectWS();

                        function sendMessage() {
                            const input = document.getElementById('chat-input');
                            const chatBox = document.getElementById('chat-box');
                            const message = input.value;
                            if (message) {
                                chatBox.innerHTML += '<strong>You:</strong> ' + message + '<br><strong>Merlin:</strong> ';
                                ws.send(JSON.stringify({ user_input: message, user_id: 'dashboard-user', api_key: apiKey }));
                                input.value = '';
                            }
                        }
                        async function fetchData(url, elementId) {
                            try {
                                const response = await fetch(url, {
                                    headers: { 'X-Merlin-Key': apiKey } // Default key for dev
                                });
                                const data = await response.json();
                                document.getElementById(elementId).innerHTML = '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
                            } catch (error) {
                                document.getElementById(elementId).innerHTML = '<span class="status-fail">Error loading data</span>';
                            }
                        }

                        fetchData('/health', 'health');
                        fetchData('/merlin/system_info', 'sysinfo');
                        fetchData('/merlin/plugins', 'plugins');
                        fetchData('/merlin/llm/adaptive/metrics', 'llmMetrics');
                        fetchData('/merlin/tasks', 'tasks'); 
                    </script>
                </body>
            </html>
            """
