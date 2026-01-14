// MerlinElectronDesktopChat.js
// Electron renderer process: Merlin chat UI
const { ipcRenderer } = require('electron');

const chatHistory = document.getElementById('chatHistory');
const userInput = document.getElementById('userInput');
const userIdInput = document.getElementById('userIdInput');
const sendButton = document.getElementById('sendButton');
const historyButton = document.getElementById('historyButton');
const apiKey = localStorage.getItem('MERLIN_API_KEY') || 'merlin-secret-key';

sendButton.onclick = async () => {
  const text = userInput.value;
  const userId = userIdInput.value || 'default';
  if (!text.trim()) return;
  chatHistory.value += `\nYou: ${text}`;
  userInput.value = '';
  try {
    const resp = await fetch('http://localhost:8000/merlin/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Merlin-Key': apiKey },
      body: JSON.stringify({ user_input: text, user_id: userId })
    });
    const data = await resp.json();
    chatHistory.value += `\nMerlin: ${data.reply}`;
  } catch {
    chatHistory.value += '\nMerlin: [API Error]';
  }
};

historyButton.onclick = async () => {
  const userId = userIdInput.value || 'default';
  try {
    const resp = await fetch(`http://localhost:8000/merlin/history/${userId}`, {
      headers: { 'X-Merlin-Key': apiKey }
    });
    const data = await resp.json();
    chatHistory.value = (data.history || []).map(entry => `You: ${entry.user}\nMerlin: ${entry.merlin}`).join('\n');
  } catch {
    chatHistory.value = '[History API Error]';
  }
};
