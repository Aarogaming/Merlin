// MerlinKotlinAndroidChat.kt
// Android Kotlin sample: Chat with Merlin REST API
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.android.synthetic.main.activity_main.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

class MainActivity : AppCompatActivity() {
    private val client = OkHttpClient()
    private val apiUrl = "http://10.0.2.2:8000/merlin/chat" // Use 10.0.2.2 for localhost in emulator
    private val historyUrl = "http://10.0.2.2:8000/merlin/history/"
    private val apiKey = System.getenv("MERLIN_API_KEY") ?: "merlin-secret-key"
    private val userId = "default" // Set per device/user

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        sendButton.setOnClickListener {
            val userInput = userInputEdit.text.toString()
            if (userInput.isNotBlank()) {
                chatHistory.append("\nYou: $userInput")
                sendChat(userInput)
                userInputEdit.text.clear()
            }
        }
    }

    private fun sendChat(userInput: String) {
        lifecycleScope.launch {
            val reply = withContext(Dispatchers.IO) {
                val json = JSONObject().put("user_input", userInput).put("user_id", userId).toString()
                val body = json.toRequestBody("application/json".toMediaTypeOrNull())
                val request = Request.Builder()
                    .url(apiUrl)
                    .post(body)
                    .header("X-Merlin-Key", apiKey)
                    .build()
                try {
                    val response = client.newCall(request).execute()
                    if (response.isSuccessful) {
                        val respJson = JSONObject(response.body?.string() ?: "")
                        respJson.optString("reply", "[No reply]")
                    } else {
                        "[Merlin API Error]"
                    }
                } catch (e: Exception) {
                    "[Network Error]"
                }
            }
            chatHistory.append("\nMerlin: $reply")
        }
    }

    // Optional: Load chat history for this user
    private fun loadChatHistory() {
        lifecycleScope.launch {
            val history = withContext(Dispatchers.IO) {
                val request = Request.Builder()
                    .url(historyUrl + userId)
                    .get()
                    .header("X-Merlin-Key", apiKey)
                    .build()
                try {
                    val response = client.newCall(request).execute()
                    if (response.isSuccessful) {
                        val respJson = JSONObject(response.body?.string() ?: "")
                        val arr = respJson.optJSONArray("history")
                        (0 until (arr?.length() ?: 0)).joinToString("\n") { i ->
                            val obj = arr!!.getJSONObject(i)
                            val userLine = "You: ${obj.getString("user")}"
                            val merlinLine = "Merlin: ${obj.getString("merlin")}"
                            "$userLine\n$merlinLine"
                        }
                    } else {
                        "[History API Error]"
                    }
                } catch (e: Exception) {
                    "[History Network Error]"
                }
            }
            chatHistory.text = history
        }
    }
}
