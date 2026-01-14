// MerlinUnityChatUI.cs
// Unity C# MonoBehaviour for Merlin chat UI integration
using UnityEngine;
using UnityEngine.UI;
using System.Collections;
using TMPro;

public class MerlinUnityChatUI : MonoBehaviour
{
    public TMP_InputField userInputField;
    public Button sendButton;
    public TextMeshProUGUI chatHistoryText;
    public MerlinUnityClient merlinClient;

    void Start()
    {
        sendButton.onClick.AddListener(OnSendClicked);
    }

    void OnSendClicked()
    {
        string userInput = userInputField.text;
        if (!string.IsNullOrEmpty(userInput))
        {
            StartCoroutine(SendChatAndDisplay(userInput));
            userInputField.text = "";
        }
    }

    IEnumerator SendChatAndDisplay(string userInput)
    {
        yield return StartCoroutine(merlinClient.SendChatCoroutine(userInput));
        string reply = merlinClient.MerlinReply;
        chatHistoryText.text += $"\n<color=yellow>You:</color> {userInput}";
        chatHistoryText.text += $"\n<color=cyan>Merlin:</color> {reply}";
    }
}
