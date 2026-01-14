// MerlinKotlinDesktopChat.kt
// Desktop Kotlin (Compose) sample: Chat with Merlin REST API
import androidx.compose.desktop.ui.tooling.preview.Preview
import androidx.compose.foundation.layout.*
import androidx.compose.material.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.*
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

@Composable
@Preview
fun MerlinChatApp() {
    var userInput by remember { mutableStateOf("") }
    var chatHistory by remember { mutableStateOf("") }
    val client = remember { OkHttpClient() }
    val apiUrl = "http://localhost:8000/merlin/chat"
    val historyUrl = "http://localhost:8000/merlin/history/"
    val apiKey = System.getenv("MERLIN_API_KEY") ?: "merlin-secret-key"
    val userId = "default" // Set per device/user
    val scope = rememberCoroutineScope()

    Column(modifier = Modifier.padding(16.dp)) {
        Text(chatHistory, modifier = Modifier.weight(1f).fillMaxWidth())
        Row {
            TextField(
                value = userInput,
                onValueChange = { userInput = it },
                modifier = Modifier.weight(1f)
            )
            Button(onClick = {
                if (userInput.isNotBlank()) {
                    chatHistory += "\nYou: $userInput"
                    scope.launch {
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
                        chatHistory += "\nMerlin: $reply"
                    }
                    userInput = ""
                }
            }) {
                Text("Send")
            }
        }
        // Optional: Load chat history button
        Button(onClick = {
            scope.launch {
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
                chatHistory = history
            }
        }) { Text("Load History") }
    }
    }
}

// In your main() function:
// import androidx.compose.ui.window.Window
// import androidx.compose.ui.window.application
// fun main() = application { Window(onCloseRequest = ::exitApplication) { MerlinChatApp() } }
