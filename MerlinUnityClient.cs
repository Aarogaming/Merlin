// MerlinUnityClient.cs
// Unity C# script to call Merlin REST API
using System.Collections;
using UnityEngine;
using UnityEngine.Networking;
using TMPro; // For TextMeshPro UI

public class MerlinUnityClient : MonoBehaviour
{
    public string apiUrl = "http://localhost:8000/merlin/chat";
    public string apiKey = "merlin-secret-key";
    public TMP_InputField userInputField;
    public TMP_Text merlinReplyText;
    public string userId = "default";
    public string MerlinReply = "";

    public void OnSendButton()
    {
        string userInput = userInputField.text;
        StartCoroutine(SendChatCoroutine(userInput));
    }

    public IEnumerator SendChatCoroutine(string userInput)
    {
        var reqObj = new ChatRequest { user_input = userInput, user_id = userId };
        var json = JsonUtility.ToJson(reqObj);
        var request = new UnityWebRequest(apiUrl, "POST");
        byte[] bodyRaw = System.Text.Encoding.UTF8.GetBytes(json);
        request.uploadHandler = new UploadHandlerRaw(bodyRaw);
        request.downloadHandler = new DownloadHandlerBuffer();
        request.SetRequestHeader("Content-Type", "application/json");
        request.SetRequestHeader("X-Merlin-Key", apiKey);
        yield return request.SendWebRequest();
        if (request.result == UnityWebRequest.Result.Success)
        {
            ChatResponse resp = JsonUtility.FromJson<ChatResponse>(request.downloadHandler.text);
            MerlinReply = resp.reply;
            if (merlinReplyText != null)
            {
                merlinReplyText.text = MerlinReply;
            }
        }
        else
        {
            MerlinReply = "[Merlin API Error]";
        }
    }

    [System.Serializable]
    public class ChatRequest { public string user_input; public string user_id; }
    [System.Serializable]
    public class ChatResponse { public string reply; }
}
