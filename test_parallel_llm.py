# Test Parallel LLM Backend
import os

os.environ["LLM_BACKEND"] = "parallel"
os.environ["PARALLEL_STRATEGY"] = "voting"

from merlin_parallel_llm import parallel_llm_backend

print("=== Parallel LLM Backend Test ===\n")

print("1. Loading models...")
status = parallel_llm_backend.get_status()
print(f"   Strategy: {status['strategy']}")
print(f"   Models: {[m['name'] for m in status['models']]}")
print(f"   Health: {status['health']}\n")

print("2. Testing chat completion...")
messages = [
    {"role": "system", "content": "You are a helpful AI assistant."},
    {"role": "user", "content": "What is 2+2?"},
]

try:
    response = parallel_llm_backend.chat_completion(
        messages, temperature=0.7, timeout=30
    )
    reply = response["choices"][0]["message"]["content"]
    print(f"   Response: {reply}\n")
except Exception as e:
    print(f"   Error: {e}\n")

print("3. Testing strategies...")
for strategy in ["voting", "routing", "cascade", "consensus"]:
    os.environ["PARALLEL_STRATEGY"] = strategy
    parallel_llm_backend.strategy = strategy
    try:
        response = parallel_llm_backend.chat_completion(
            messages, temperature=0.7, timeout=10
        )
        print(
            f"   {strategy}: {len(response['choices'][0]['message']['content'])} chars"
        )
    except Exception as e:
        print(f"   {strategy}: Failed - {e}")

print("\n=== Test Complete ===")
print("\nTo use in production:")
print("1. Set LLM_BACKEND=parallel in .env")
print("2. Set PARALLEL_STRATEGY=voting/routing/cascade/consensus in .env")
print("3. Configure OLLAMA_MODELS and external API keys")
print("4. Restart Merlin API server")
