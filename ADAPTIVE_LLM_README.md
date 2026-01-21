# Adaptive LLM Backend - Self-Optimizing Multi-Model System

## Overview
Merlin's adaptive backend learns from every interaction to automatically select and optimize the best model for each task. It combines multi-model parallel execution with machine learning-style adaptation to continuously improve performance.

## Key Features

### 1. Self-Learning Metrics
Tracks per-model performance:
- **Success Rate**: How often the model responds successfully
- **Average Latency**: Speed of responses
- **User Ratings**: Explicit feedback scores (1-5)
- **Task-Specific Success**: Performance per task type (code, creative, analysis, etc.)

### 2. Intelligent Query Analysis
Automatically categorizes each query:
- **Task Type**: code, creative, analysis, search, fact, planning, translation, summarize
- **Complexity**: low, medium, high
- **Urgency**: low, normal, high
- **Requirements**: creativity, accuracy

### 3. Adaptive Strategy Selection
Automatically chooses optimal strategy:
- **High urgency** → Fastest model (adaptive routing)
- **High complexity** → Best quality (voting)
- **Requires accuracy** → Consensus verification
- **Normal** → Smart routing based on learned performance

### 4. Dynamic Model Scoring
Composite scoring based on:
- Historical success rate (30% weight)
- Average latency (20% weight, faster = better)
- User ratings (30% weight)
- Task-specific success (20% weight)

## Configuration

### Enable Adaptive Mode
```bash
# In .env
LLM_BACKEND=adaptive
PARALLEL_STRATEGY=auto  # Let system choose best strategy
LEARNING_MODE=enabled
MIN_LEARNING_SAMPLES=5  # Min requests before using learned data
```

### Configure Models
Same as parallel mode - add your models to OLLAMA_MODELS or configure external APIs.

## How It Works

### Query Flow
```
User Query
    ↓
QueryContext.analyze()
    ↓
Determine: task type, complexity, urgency, requirements
    ↓
Check learned metrics for each model
    ↓
Select optimal model based on scores
    ↓
Execute all models in parallel
    ↓
Apply chosen strategy (voting/routing/cascade/consensus)
    ↓
Return best response
    ↓
Update metrics (success, latency, task type)
    ↓
Save to artifacts/adaptive_metrics.json
```

### Learning Process
1. **Initial Phase** (first 5 requests): Uses heuristics and latency
2. **Learning Phase** (5+ requests): Incorporates user ratings and task success
3. **Optimized Phase**: Continuously refines model selection based on performance

## API Endpoints

### Provide Feedback
```bash
POST /merlin/llm/adaptive/feedback
X-Merlin-Key: merlin-secret-key
Content-Type: application/json

{
  "model_name": "mistral",
  "rating": 5,
  "task_type": "code"
}
```

### View Learning Status
```bash
GET /merlin/llm/adaptive/status
X-Merlin-Key: merlin-secret-key
```

Response:
```json
{
  "strategy": "auto",
  "learning_mode": true,
  "min_samples": 5,
  "models": [
    {"name": "mistral", "backend": "ollama"},
    {"name": "llama3.2", "backend": "ollama"}
  ],
  "metrics": {
    "mistral": {
      "total_requests": 150,
      "success_rate": 0.95,
      "avg_latency": 1.2,
      "avg_rating": 4.5
    },
    "llama3.2": {
      "total_requests": 200,
      "success_rate": 0.98,
      "avg_latency": 0.8,
      "avg_rating": 4.2
    }
  }
}
```

### Reset Metrics
```bash
POST /merlin/llm/adaptive/reset
X-Merlin-Key: merlin-secret-key
```

## Adaptation Examples

### Example 1: Code Query
```
User: "Write a Python function to sort a list"
    ↓
Analysis: task_type=code, complexity=medium, urgency=normal
    ↓
Learned: Nemotron3 has 95% success for code tasks
    ↓
Action: Route to Nemotron3 first, validate with others
```

### Example 2: Creative Query
```
User: "Write a short sci-fi story about time travel"
    ↓
Analysis: task_type=creative, complexity=high, urgency=low, requires_creativity=true
    ↓
Learned: Mistral has 4.8/5 rating for creative tasks
    ↓
Action: Use voting strategy with Mistral as primary scorer
```

### Example 3: Urgent Query
```
User: "What's 2+2? Quick!"
    ↓
Analysis: task_type=fact, complexity=low, urgency=high
    ↓
Learned: Llama3.2 has 0.3s average latency
    ↓
Action: Cascade - return Llama3.2 immediately, verify later
```

## Performance Optimization

### For Fast Responses
- Set `PARALLEL_STRATEGY=cascade`
- Use fast models in `OLLAMA_MODELS`
- System will prioritize low latency

### For High Quality
- Set `PARALLEL_STRATEGY=voting`
- Use diverse models (creative, analytical, coding)
- Provide feedback to improve scoring

### For Reliability
- Set `PARALLEL_STRATEGY=consensus`
- Use 3+ models
- High accuracy critical tasks

## Metrics Storage

Metrics are stored in `artifacts/adaptive_metrics.json`:

```json
{
  "mistral": {
    "total_requests": 100,
    "successful_requests": 95,
    "total_latency": 120.5,
    "user_ratings": [5, 4, 5, 4, 5],
    "task_successes": {
      "code": 30,
      "creative": 35,
      "analysis": 30
    }
  }
}
```

## Advanced Features

### Task-Based Routing
System learns which models excel at specific tasks:
- Code tasks → Nemotron3, GLM4
- Creative tasks → Mistral
- Analysis tasks → GLM4, Nemotron3
- Fast responses → Llama3.2
- Semantic tasks → Nomic

### Urgency Adaptation
- **High urgency**: Prioritizes speed, uses cascade
- **Low urgency**: Prioritizes quality, uses voting
- **Normal**: Balances based on learned metrics

### Complexity Adaptation
- **Low complexity**: Routes to fastest model
- **Medium complexity**: Uses adaptive routing
- **High complexity**: Uses voting for best quality

### Failover Adaptation
If a model fails consistently:
- Reduces its priority score
- Eventually stops selecting it
- Automatically retries if it recovers

## Troubleshooting

### Poor Model Selection
1. Check metrics: `GET /merlin/llm/adaptive/metrics`
2. Provide feedback on bad responses
3. Reset metrics if needed: `POST /merlin/llm/adaptive/reset`
4. Adjust `MIN_LEARNING_SAMPLES` (higher = more conservative)

### System Not Learning
- Ensure `LEARNING_MODE=enabled`
- Check write permissions for `artifacts/` directory
- Verify metrics file is updating

### Slow Adaptation
- Increase `MIN_LEARNING_SAMPLES` for faster reliance on learned data
- Or provide more feedback to accelerate learning

## Best Practices

1. **Start with diverse models** - Different strengths help learning
2. **Provide feedback regularly** - Ratings accelerate optimization
3. **Let it run** - System improves over time (100+ requests)
4. **Monitor metrics** - Check weekly for trends
5. **Reset periodically** - Clear old data if patterns change

## Comparison: Parallel vs Adaptive

| Feature | Parallel | Adaptive |
|----------|-----------|-----------|
| Model selection | Fixed/Manual | Learned/Automatic |
| Strategy | Manual | Automatic based on context |
| Performance tracking | Basic | Advanced (per-task) |
| User feedback | No | Yes (ratings) |
| Optimization | Static | Continuous |
| Best for | Fixed workflows | Evolving usage patterns |

## Future Enhancements

- [ ] A/B testing between strategies
- [ ] Predictive model selection
- [ ] Context window optimization
- [ ] Cost optimization for paid APIs
- [ ] Multi-user personalization
- [ ] Model performance dashboard
- [ ] Export/import learning data
- [ ] Federated learning across instances
