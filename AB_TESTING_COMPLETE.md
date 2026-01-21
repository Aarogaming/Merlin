# A/B Testing - Implementation Complete

## Summary

Merlin now has a **complete A/B testing framework** for scientifically comparing and optimizing strategy performance.

---

## What Was Implemented

**1. ABTestingManager** (`merlin_ab_testing.py`):

**ABTest Class:**
- Test configuration (variants, weights, duration)
- Random variant selection based on weights
- Per-variant metrics tracking
- Winner determination with composite scoring
- Automatic test completion

**ABTestingManager Class:**
- Create new A/B tests with custom variants/weights
- Active test management
- Test history tracking (completed tests)
- Result recording per variant
- Test completion and winner declaration
- JSON persistence (`artifacts/ab_tests.json`)

**2. API Endpoints** (`merlin_api_server.py`):

**POST `/merlin/llm/ab/create`**
- Create new A/B test
- Variants: List of strategy names (e.g., ["auto", "voting", "routing"])
- Weights: Traffic split percentages (e.g., [0.4, 0.3, 0.3])
- Duration: Test duration in hours
- Returns: Test ID for tracking

**GET `/merlin/llm/ab/tests`**
- List all active A/B tests
- Returns: Test status, variants, current metrics per variant

**GET `/merlin/llm/ab/test/{test_id}`**
- Get detailed status of specific test
- Returns: Variant statistics, winner status, duration info

**POST `/merlin/llm/ab/result`**
- Record user feedback for a test variant
- Supports: User rating (1-5), latency measurement, success status
- Updates metrics for winner calculation

**POST `/merlin/llm/ab/complete/{test_id}`**
- Manually complete a test
- Automatically determines and returns winner
- Moves test to history

---

## Scoring System

**Composite Score Calculation:**
```
score = (
    success_rate * 50% +        # How often variant succeeds
    latency_score * 30% +        # Faster is better
    rating_score * 20%            # User satisfaction
)
```

**Latency Scoring:**
- < 1s: 10.0 points (excellent)
- 1-2s: 5.0 points (good)
- 2-5s: 2.5 points (acceptable)
- > 5s: 0.0 points (poor)

**Rating Scoring:**
- 5/5: 1.0 points (excellent)
- 4/5: 0.8 points (good)
- 3/5: 0.6 points (acceptable)
- 1-2/5: 0.2-0.4 points (poor)

---

## Usage Examples

### Example 1: Strategy Comparison Test

```bash
# Create test comparing auto vs voting vs routing
curl -X POST http://localhost:8000/merlin/llm/ab/create \
  -H "X-Merlin-Key: merlin-secret-key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Strategy Comparison",
    "variants": ["auto", "voting", "routing"],
    "weights": [0.33, 0.33, 0.34],
    "duration_hours": 48
  }'

# Response: {"test_id": "test_20260117_205431", "status": "created"}
```

### Example 2: Query Type Routing Test

```bash
# Create test comparing different query routing approaches
curl -X POST http://localhost:8000/merlin/llm/ab/create \
  -H "X-Merlin-Key: merlin-secret-key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Query Routing Comparison",
    "variants": ["code", "creative", "general"],
    "weights": [0.5, 0.3, 0.2],
    "duration_hours": 24
  }'
```

### Example 3: Record User Feedback

```bash
# User provides feedback on their experience
curl -X POST http://localhost:8000/merlin/llm/ab/result \
  -H "X-Merlin-Key: merlin-secret-key" \
  -H "Content-Type: application/json" \
  -d '{
    "test_id": "test_20260117_205431",
    "variant": "voting",
    "user_rating": 5,
    "latency": 1.2,
    "success": true
  }'
```

### Example 4: Complete Test & Get Winner

```bash
# Manually complete test before duration ends
curl -X POST http://localhost:8000/merlin/llm/ab/complete/test_20260117_205431 \
  -H "X-Merlin-Key: merlin-secret-key"

# Response: 
{
  "status": "completed",
  "winner": {
    "variant": "voting",
    "score": 0.87,
    "stats": {
      "requests": 152,
      "success_rate": 0.96,
      "avg_latency": 1.1,
      "avg_rating": 4.7
    }
  }
}
```

---

## Test Workflow

```
1. Create Test
   POST /merlin/llm/ab/create
   ↓
   Get test_id
   ↓
2. Run Test
   System assigns variants to requests
   ↓
   Users interact with system
   ↓
   Metrics collected per variant
   ↓
3. Record Results
   POST /merlin/llm/ab/result
   ↓
   User feedback collected
   ↓
   Latency measured
   ↓
4. Complete Test
   POST /merlin/llm/ab/complete
   ↓
   Winner determined
   ↓
   Test moved to history
   ↓
5. Analyze Results
   GET /merlin/llm/ab/tests
   ↓
   Compare performance
   ↓
   Select winner
   ↓
   Apply winner as default
```

---

## Data Persistence

**File:** `artifacts/ab_tests.json`

**Structure:**
```json
{
  "active_tests": {
    "test_id": {
      "test_id": "...",
      "name": "Test Name",
      "variants": ["variant1", "variant2"],
      "weights": [0.5, 0.5],
      "start_time": "2026-01-17T20:00:00",
      "end_time": "2026-01-18T20:00:00",
      "status": "active|completed",
      "metrics": {
        "variant1": {
          "requests": 100,
          "ratings": [5, 4, 5, 4],
          "latencies": [1.1, 1.2, 0.9, 1.3],
          "successes": [1, 1, 1, 1]
        }
      }
    }
  },
  "history": [...completed tests...]
}
```

---

## Features

**Traffic Splitting:**
- Random variant selection
- Weighted distribution support
- Consistent selection per test ID

**Metrics Collection:**
- Request count per variant
- Success rate tracking
- Latency averaging
- User rating collection (last 50)
- Automatic data pruning at 100 ratings

**Winner Determination:**
- Composite scoring (success + latency + rating)
- Only considers variants with 10+ requests
- Automatic winner declaration on test completion

**Test Management:**
- List all active tests
- Get detailed status
- Manual completion support
- Historical tracking

---

## Best Practices

**1. Test Design:**
- Test 2-3 variants at a time (A/B/C testing)
- Use statistically significant sample sizes (100+ requests)
- Run tests for minimum 24-48 hours

**2. Variant Configuration:**
- Start with equal weights: `[0.5, 0.5]`
- Adjust based on preliminary results
- Test different aspects: strategy, model combination, parameters

**3. Result Collection:**
- Record user feedback for every interaction
- Measure actual latency
- Track successful vs failed requests
- Use consistent rating scale (1-5)

**4. Analysis:**
- Compare success rates (statistical significance)
- Consider latency (user experience)
- Factor in user ratings (satisfaction)
- Don't declare winners with insufficient data

---

## Integration with Adaptive System

The A/B testing system can automatically update the adaptive learning system:

```python
# After A/B test completes, update model scores
winner = ab_testing_manager.complete_test(test_id)
if winner and winner["variant"] == "voting":
    # Boost voting strategy model scores
    adaptive_llm_backend.provide_feedback(
        model_name="mistral",  # example
        rating=5,
        task_type="ab_test_winner"
    )
```

---

## API Endpoint Reference

### Create Test
```bash
POST /merlin/llm/ab/create
X-Merlin-Key: merlin-secret-key
Content-Type: application/json

{
  "name": "Test Name",
  "variants": ["variant1", "variant2", "variant3"],
  "weights": [0.4, 0.3, 0.3],  # Optional, default is equal
  "duration_hours": 24
}
```

Response:
```json
{
  "test_id": "test_20260117_205431",
  "status": "created",
  "name": "Test Name"
}
```

### List Tests
```bash
GET /merlin/llm/ab/tests
X-Merlin-Key: merlin-secret-key
```

Response:
```json
{
  "tests": [
    {
      "test_id": "...",
      "name": "Test Name",
      "status": "active",
      "variants": ["variant1", "variant2"],
      "weights": [0.4, 0.3],
      "start_time": "...",
      "variant_stats": {
        "variant1": {
          "requests": 50,
          "success_rate": 0.94,
          "avg_latency": 1.2,
          "avg_rating": 4.5
        }
      },
      "winner": null
    }
  ]
}
```

### Get Test Status
```bash
GET /merlin/llm/ab/test/{test_id}
X-Merlin-Key: merlin-secret-key
```

Response:
```json
{
  "test_id": "test_20260117_205431",
  "name": "Test Name",
  "status": "active",
  "variants": ["variant1", "variant2"],
  "weights": [0.4, 0.3],
  "start_time": "...",
  "end_time": null,
  "duration_hours": 24,
  "variant_stats": {...},
  "winner": null
}
```

### Record Result
```bash
POST /merlin/llm/ab/result
X-Merlin-Key: merlin-secret-key
Content-Type: application/json

{
  "test_id": "test_20260117_205431",
  "variant": "variant1",
  "user_rating": 4,  # 1-5, optional
  "latency": 1.5,  # seconds, optional
  "success": true
}
```

Response:
```json
{
  "status": "recorded",
  "test_id": "test_20260117_205431",
  "variant": "variant1"
}
```

### Complete Test
```bash
POST /merlin/llm/ab/complete/{test_id}
X-Merlin-Key: merlin-secret-key
```

Response:
```json
{
  "status": "completed",
  "test_id": "test_20260117_205431",
  "winner": {
    "variant": "variant1",
    "score": 0.85,
    "stats": {
      "requests": 100,
      "success_rate": 0.95,
      "avg_latency": 1.1,
      "avg_rating": 4.7
    }
  }
}
```

---

## Troubleshooting

**No clear winner:**
- Increase test duration
- Ensure sufficient requests per variant (100+)
- Check variant weights are appropriate

**Unbalanced metrics:**
- Verify all requests have results recorded
- Check test configuration
- Manually record missing results

**Test not ending:**
- Use manual complete endpoint
- Check test duration settings
- Verify variant selection logic

---

## Files Created/Modified

**New:**
- `merlin_ab_testing.py` - A/B testing framework

**Modified:**
- `merlin_api_server.py` - Added A/B testing endpoints:
  - POST /merlin/llm/ab/create
  - GET /merlin/llm/ab/tests
  - GET /merlin/llm/ab/test/{test_id}
  - POST /merlin/llm/ab/result
  - POST /merlin/llm/ab/complete/{test_id}

---

## A/B Testing Features Complete and Ready for Scientific Strategy Optimization!
