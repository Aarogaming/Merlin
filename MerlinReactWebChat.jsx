// MerlinReactWebChat.jsx
// React functional component for Merlin REST API chat
import React, { useState } from 'react';

function MerlinReactWebChat() {
  const [userInput, setUserInput] = useState('');
  const [chatHistory, setChatHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [userId, setUserId] = useState('default');
  const [showTaskCreator, setShowTaskCreator] = useState(false);
  const [taskTitle, setTaskTitle] = useState('');
  const [taskDesc, setTaskDesc] = useState('');

  const sendChat = async () => {
    if (!userInput.trim()) return;
    setChatHistory([...chatHistory, { sender: 'You', text: userInput }]);
    setLoading(true);
    try {
      const apiKey = localStorage.getItem('MERLIN_API_KEY') || 'merlin-secret-key';
      const resp = await fetch('http://localhost:8000/merlin/chat', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'X-Merlin-Key': apiKey
        },
        body: JSON.stringify({ user_input: userInput, user_id: userId })
      });
      const data = await resp.json();
      setChatHistory(h => [...h, { sender: 'Merlin', text: data.reply }]);
    } catch {
      setChatHistory(h => [...h, { sender: 'Merlin', text: '[API Error]' }]);
    }
    setUserInput('');
    setLoading(false);
  };

  // Optional: Load chat history for this user
  const loadHistory = async () => {
    setLoading(true);
    try {
      const apiKey = localStorage.getItem('MERLIN_API_KEY') || 'merlin-secret-key';
      const resp = await fetch(`http://localhost:8000/merlin/history/${userId}`, {
        headers: { 'X-Merlin-Key': apiKey }
      });
      const data = await resp.json();
      setChatHistory(
        (data.history || []).flatMap(entry => [
          { sender: 'You', text: entry.user },
          { sender: 'Merlin', text: entry.merlin }
        ])
      );
    } catch {
      setChatHistory([{ sender: 'System', text: '[History API Error]' }]);
    }
    setLoading(false);
  };
  const createTask = async () => {
    setLoading(true);
    try {
      const apiKey = localStorage.getItem('MERLIN_API_KEY') || 'merlin-secret-key';
      const resp = await fetch('http://localhost:8000/merlin/aas/create_task', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'X-Merlin-Key': apiKey
        },
        body: JSON.stringify({ title: taskTitle, description: taskDesc })
      });
      const data = await resp.json();
      setChatHistory(h => [...h, { sender: 'System', text: `Task Created: ${data.task_id}` }]);
      setShowTaskCreator(false);
      setTaskTitle('');
      setTaskDesc('');
    } catch {
      setChatHistory(h => [...h, { sender: 'System', text: '[Task API Error]' }]);
    }
    setLoading(false);
  };

  return (
    <div style={{ maxWidth: 400, margin: 'auto', fontFamily: 'sans-serif' }}>
      <div style={{ minHeight: 200, maxHeight: 400, overflowY: 'auto', border: '1px solid #ccc', padding: 8, marginBottom: 8, borderRadius: 8 }}>
        {chatHistory.map((msg, i) => (
          <div key={i}><b>{msg.sender}:</b> {msg.text}</div>
        ))}
      </div>
      <input
        value={userInput}
        onChange={e => setUserInput(e.target.value)}
        onKeyDown={e => e.key === 'Enter' && sendChat()}
        disabled={loading}
        style={{ width: '60%' }}
      />
      <input
        value={userId}
        onChange={e => setUserId(e.target.value)}
        disabled={loading}
        style={{ width: '20%' }}
        placeholder="User ID"
      />
      <button onClick={sendChat} disabled={loading} style={{ width: '18%' }}>Send</button>
      
      <div style={{ marginTop: 10 }}>
        <button onClick={() => setShowTaskCreator(!showTaskCreator)} style={{ width: '100%', padding: 8 }}>
          {showTaskCreator ? 'Cancel' : 'Create AAS Task'}
        </button>
        
        {showTaskCreator && (
          <div style={{ border: '1px solid #ddd', padding: 10, marginTop: 5, borderRadius: 8 }}>
            <input 
              placeholder="Task Title" 
              value={taskTitle} 
              onChange={e => setTaskTitle(e.target.value)} 
              style={{ width: '100%', marginBottom: 5 }}
            />
            <textarea 
              placeholder="Description" 
              value={taskDesc} 
              onChange={e => setTaskDesc(e.target.value)} 
              style={{ width: '100%', marginBottom: 5, height: 60 }}
            />
            <button onClick={createTask} disabled={loading || !taskTitle} style={{ width: '100%', background: '#4CAF50', color: 'white', border: 'none', padding: 8, borderRadius: 4 }}>
              Submit to AAS Hub
            </button>
          </div>
        )}
      </div>

      <button onClick={loadHistory} disabled={loading} style={{ width: '100%', marginTop: 10, padding: 8 }}>Load History</button>
    </div>
  );
}

export default MerlinReactWebChat;
