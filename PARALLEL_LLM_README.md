# Parallel LLM Backend - Multi-Model Orchestration

## Overview
Merlin now supports running multiple LLM models in parallel with intelligent response selection. This allows you to leverage the strengths of different models (Mistral, Nemotron 3, GLM, Nomic, Llama) simultaneously.

## Configuration

### 1. Set Backend to Parallel
```bash
# In .env file
LLM_BACKEND=parallel
PARALLEL_STRATEGY=voting  # Options: voting, routing, cascade, consensus
```

### 2. Configure Models

#### Ollama Models (Local)
```bash
# Install and start Ollama
ollama pull llama3.2
ollama pull mistral
ollama pull nomic
ollama run llama3.2 &

# Configure in .env
OLLAMA_URL=http://localhost:11434/api/chat
OLLAMA_MODELS=["llama3.2", "mistral", "nomic", "glm4"]
```

#### External APIs

**Nemotron 3:**
```bash
NEMOTRON_API_KEY=your-key-here
NEMOTRON_URL=http://localhost:8001/v1/chat/completions
NEMOTRON_MODEL=nemotron-3
```

**GLM (BigModel.cn):**
```bash
GLM_API_KEY=your-key-here
GLM_URL=https://open.bigmodel.cn/api/paas/v4/chat/completions
GLM_MODEL=glm-4
```

## Strategies

### 1. Voting (Default)
All models respond simultaneously, scores each response, returns best one.
- **Pros:** Best quality response, diversity
- **Cons:** Slower latency
- **Best for:** Complex tasks, creative writing, critical decisions

### 2. Routing
Analyzes query type and routes to optimal model:
- **Code tasks** → Nemotron 3
- **Creative tasks** → Mistral  
- **Fast responses** → Llama 3.2
- **Semantic search** → Nomic
- **Analysis** → GLM 4
- **Pros:** Optimized per task, faster
- **Cons:** May not handle mixed queries well
- **Best for:** Specialized workflows, production

### 3. Cascade
Uses fastest model for initial response, refined by best model.
- **Pros:** Fast + quality, good UX
- **Cons:** Two-stage latency
- **Best for:** Chat interfaces, real-time

### 4. Consensus
Combines responses from all models for majority agreement.
- **Pros:** Reduces errors, high reliability
- **Cons:** Complex integration, may lose nuance
- **Best for:** Critical systems, fact-checking

## API Endpoints

### Check Parallel Status
```bash
GET /merlin/llm/parallel/status
X-Merlin-Key: merlin-secret-key
```

Response:
```json
{
  "strategy": "voting",
  "models": [
    {"name": "mistral", "backend": "ollama"},
    {"name": "nomic", "backend": "ollama"},
    {"name": "llama3.2", "backend": "ollama"}
  ],
  "health": {
    "mistral": true,
    "nomic": true,
    "llama3.2": false
  }
}
```

### Change Strategy
```bash
POST /merlin/llm/parallel/strategy
X-Merlin-Key: merlin-secret-key
Content-Type: application/json

{
  "strategy": "cascade"
}
```

## Model Comparison

| Model | Strengths | Weaknesses | Best For |
|--------|------------|--------------|-----------|
| **Mistral** | Creative, nuanced | Slower | Writing, storytelling |
| **Nemotron 3** | Coding, logic | Requires API | Debug, programming |
| **GLM 4** | Analysis, reasoning | Latency | Evaluation, comparison |
| **Nomic** | Embeddings, semantic | Not conversational | Search, RAG |
| **Llama 3.2** | Fast, efficient | Less nuanced | Quick responses |

## Performance Tips

1. **For speed:** Use `routing` strategy with Llama 3.2
2. **For quality:** Use `voting` strategy with all models
3. **For reliability:** Use `consensus` strategy
4. **For UX:** Use `cascade` strategy

## Example Usage

```python
# Start Merlin with parallel backend
LLM_BACKEND=parallel PARALLEL_STRATEGY=voting python merlin_api_server.py

# Query Merlin - it will use all configured models
curl -X POST http://localhost:8000/merlin/chat \
  -H "X-Merlin-Key: merlin-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"user_input": "Write a Python function to sort a list"}'

# Response will be the best among all models
```

## Troubleshooting

**Models not responding:**
- Check health status: `GET /merlin/llm/parallel/status`
- Ensure Ollama is running: `ollama list`
- Verify API keys for external models

**Slow responses:**
- Switch to `routing` strategy
- Reduce model count in `OLLAMA_MODELS`
- Use `cascade` for faster initial response

**Quality issues:**
- Increase model count
- Use `voting` strategy
- Ensure models are trained for your use case

## Future Enhancements

- [ ] Streaming support for parallel responses
- [ ] Custom scoring functions per strategy
- [ ] Model performance analytics
- [ ] Dynamic model selection based on success metrics
- [ ] Hybrid strategies combining multiple approaches
