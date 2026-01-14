# Merlin Unity Integration Guide

This guide explains how to connect your Unity project to the Merlin REST API for conversational AI, using the provided C# scripts.

## 1. Add the Files

- Copy `MerlinUnityClient.cs` and `MerlinUnityChatUI.cs` into your Unity project's `Assets/Scripts/` directory.
- Make sure you have TextMeshPro imported (Window > Package Manager > TextMeshPro).

## 2. Set Up the Scene

1. Create a Canvas in your scene.
2. Add a TMP_InputField for user input, a Button for sending, and a TextMeshProUGUI for chat history.
3. Add an empty GameObject and attach both `MerlinUnityClient` and `MerlinUnityChatUI` scripts.
4. Assign the UI elements to the `MerlinUnityChatUI` fields in the Inspector.
5. Assign the `MerlinUnityClient` component to the `merlinClient` field in `MerlinUnityChatUI`.

## 3. Usage

- Enter text in the input field and click Send.
- The chat history will update with both your message and Merlin's reply.
- The scripts use coroutines for async API calls and UI updates.

## 4. REST API Endpoint

- By default, the client sends requests to `http://localhost:8000/merlin/chat`.
- Make sure your `merlin_api_server.py` is running and accessible from your Unity project.
- Set `apiKey` on `MerlinUnityClient` to match your `MERLIN_API_KEY`.

## 5. Notes

- For production, update the API URL as needed.
- You can extend the scripts for avatars, voice, or advanced UI.

---

For questions or advanced integration, see the comments in the C# files or ask for further Unity/VR examples.
