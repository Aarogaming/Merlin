# Cost Optimization - Minimizing LLM API Expenses - Implementation Complete

## Summary

Merlin now has a **complete cost optimization system** that tracks token usage across all models, enforces budget limits, and provides intelligent recommendations for minimizing LLM expenses.

---

## What Was Implemented

**1. Cost Tracking System** (`CostOptimizationManager`):
- Per-model pricing configuration (input/output token costs)
- Daily usage tracking (requests, tokens, costs)
- Budget management with configurable limits
- Cost efficiency scoring
- 90-day data retention with automatic cleanup
- Alerting for budget thresholds

**2. Token Tracking Integration**:
- Streaming backend tracks tokens per model
- Automatic cost calculation on every request
- Input tokens estimated from request length
- Output tokens tracked from model responses
- Task type recording for smarter optimization

**3. Features:**
- **Budget Management**:
  - Monthly budget limits
  - Warning/critical thresholds at 70%/90%
  - Per-model budget caps
  - Automatic budget reset
  
- **Usage Monitoring**:
  - Daily breakdown by model
  - Request count and token counts
  - Average cost per request
  - Cost efficiency scores
  
- **Recommendation Engine**:
  - Switch to free model recommendations
  - Usage reduction suggestions
  - Threshold adjustment warnings
  - Budget review scheduling

- **Data Persistence**:
  - `artifacts/model_pricing.json`: Model pricing configuration
  - `artifacts/model_usage.json`: Daily usage history
  - `artifacts/cost_optimization_log.json`: Optimization events

---

## Cost Tracking Examples

### Example 1: Daily Usage Tracking

```python
# After a day of queries, cost is automatically tracked
{
  "daily_usage": {
    "mistral": [
      {
        "date": "2026-01-17",
        "requests": 50,
        "input_tokens": 15000,
        "output_tokens": 45000,
        "total_cost": 1.80,
        "avg_cost_per_request": 0.036,
        "cost_efficiency_score": 0.8
      }
    ]
  }
}
```

### Example 2: Budget Alerting

**Budget:** $100/month
**Current spend:** $68.70 (68.7%)

Alerts:
```json
{
  "event_type": "budget_warning",
  "total_spend": 68.70,
  "budget_limit": 100.0,
  "percentage": 68.7
}
```

### Example 3: Cost Optimization Recommendations

**Scenario:** High Nemotron3 usage exceeding budget

```json
{
  "recommendations": {
    "switch_to_free_model": true,
    "reduce_usage": true,
    "adjust_thresholds": false,
    "schedule_review": false
  },
  "highest_cost_model": "nemotron3",
  "model_costs": {
    "mistral": 45.20,
    "llama3.2": 32.10,
    "nemotron3": 68.50,
    "glm4": 22.80
  }
}
```

---

## API Endpoints

### Get Cost Report
```bash
POST /merlin/llm/cost/report
X-Merlin-Key: merlin-secret-key
Content-Type: application/json

{
  "days": 30  # Report period in days
}
```

**Response:**
```json
{
  "period_days": 30,
  "start_date": "2026-01-17T00:00:00",
  "end_date": "2026-01-17T00:00:00",
  "budget_limit": 100.0,
  "total_spend": 45.60,
  "model_breakdown": {
    "mistral": {
      "total_cost": 18.30,
      "avg_cost": 0.18,
      "requests": 45,
      "avg_cost_per_request": 0.41,
      "cost_efficiency_score": 0.75
    },
    "llama3.2": {
      "total_cost": 12.00,
      "avg_cost": 0.12,
      "requests": 32,
      "avg_cost_per_request": 0.38,
      "cost_efficiency_score": 0.85
    },
    "nemotron3": {
      "total_cost": 15.30,
      "avg_cost": 0.25,
      "requests": 18,
      "avg_cost_per_request": 0.85,
      "cost_efficiency_score": 0.60
    }
  },
    "daily_average": {
      "model_breakdown": {...},
      "requests": 95,
      "avg_cost_per_request": 0.23,
      "total_spend": 45.60
    }
  },
  "recommendations": {
    "switch_to_free_model": false,
    "reduce_usage": true,
    "adjust_thresholds": false,
    "schedule_review": true
  }
}
```

### Set Monthly Budget
```bash
POST /merlin/llm/cost/budget
X-Merlin-Key: merlin-secret-key
Content-Type: application/json

{
  "budget_limit": 100.0
}
```

**Response:**
```json
{
  "status": "updated",
  "new_budget_limit": 100.0,
  "previous_limit": 80.0
}
```

### Set Cost Thresholds
```bash
POST /merlin/llm/cost/thresholds
X-Merlin-Key: merlin-secret-key
Content-Type: application/json

{
  "warning_threshold": 70.0,
  "critical_threshold": 90.0
}
```

**Response:**
```json
{
  "status": "updated",
  "warning_threshold": 70.0,
  "critical_threshold": 90.0
}
```

### Get Cost Optimization Recommendations
```bash
GET /merlin/llm/cost/optimization
X-Merlin-Key: merlin-secret-key
```

**Response:**
```json
{
  "model_breakdown": {...},
  "total_spend": 45.60,
  "highest_cost_model": "nemotron3",
  "recommendations": {
    "switch_to_free_model": false,
    "reduce_usage": true,
    "adjust_thresholds": false,
    "schedule_review": true
  }
}
```

### Set Model Pricing
```bash
POST /merlin/llm/cost/pricing
X-Merlin-Key: merlin-secret-key
Content-Type: application/json

{
  "model_name": "nemotron3",
  "input_cost_per_1k": 0.01,  # $0.01 per 1K tokens
  "output_cost_per_1k": 0.015,  # $0.015 per 1K tokens
  "currency": "USD",
  "free_tier_limit": 50000,     # 50K free tokens/month
  "tier_name": "Free Tier"
}
```

### Get Current Budget
```bash
GET /merlin/llm/cost/budget
X-Merlin-Key: merlin-secret-key
```

**Response:**
```json
{
  "budget_limit": 100.0,
  "current_month_spend": 45.60,
  "percentage_used": 45.6,
  "model_breakdown": {...}
}
```

---

## Configuration

**Environment Variables:**
```bash
# Monthly budget limit in USD
MONTHLY_BUDGET_LIMIT=100

# Warning threshold (70% of budget)
COST_WARNING_THRESHOLD=70

# Critical threshold (90% of budget)
COST_CRITICAL_THRESHOLD=90
```

**Default Model Pricing:**
- Ollama models: Free (tracked for token count)
- Nemotron3: $0.01/1K input, $0.015/1K output
- GLM4: Cloud API pricing
- Mistral: Cloud API pricing

---

## Token Tracking

**How It Works:**

1. **Estimate Input Tokens:**
   - Request length in characters
   - Approximate tokenization (chars/4)

2. **Track Output Tokens:**
   - Model response length in characters
   - Approximate tokens (chars/4)

3. **Calculate Cost:**
   - `(input_tokens * input_cost) + (output_tokens * output_cost)`
   - Store in daily usage data

4. **Budget Monitoring:**
   - Sum daily costs across all models
   - Compare against budget limit
   - Trigger alerts at 70% and 90%

5. **Generate Recommendations:**
   - Highest cost model vs lowest cost model
   - If 2x more expensive, suggest switching
   - If near budget, suggest usage reduction
   - High costs suggest budget review

---

## Best Practices

**1. Budget Setting:**
- Set realistic limits based on actual usage
- Monitor spending trends for 3 months before optimizing
- Use 20% buffer below your target

**2. Cost Reduction:**
- Prefer faster models for simple queries
- Use local models when possible
- Cache frequent responses locally
- Reduce token usage with shorter prompts

**3. Monitoring:**
- Check cost reports weekly
- Watch model cost per request trends
- Identify sudden cost increases

**4. Alerts:**
- Act on warning alerts immediately
- Switch to backup models at critical level
- Review usage patterns at budget exhaustion

---

## Files Created/Modified

**New:**
- `merlin_cost_optimization.py` - Complete cost optimization manager
- `COST_OPTIMIZATION_COMPLETE.md` - This documentation

**Modified:**
- `merlin_streaming_llm.py` - Added token tracking
- `merlin_emotion_chat.py` - Added cost optimization import
- `merlin_api_server.py` - Added 8 new cost endpoints

---

## Cost Optimization System Features Complete!

**Key Capabilities:**
- ✅ Per-model pricing configuration
- ✅ Real-time token usage tracking
- ✅ Daily and monthly cost reporting
- ✅ Budget limit management with alerts
- ✅ Cost efficiency scoring
- ✅ Intelligent recommendations
- ✅ Multiple pricing tiers (free, paid)
- ✅ 90-day data retention
- ✅ Automatic cleanup of old data

**Next Steps:**
1. Continue with model-aware plugin execution (#5)
2. Add multi-user personalization with learning profiles (#6)

The system now tracks every token and provides actionable cost optimization recommendations!
