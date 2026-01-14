# Merlin Unreal Integration Guide

This guide explains how to use the provided `MerlinUnrealClient` C++ class to connect Unreal Engine to your Merlin REST API backend for conversational AI.

## 1. Add the Files

- Copy `MerlinUnrealClient.h` and `MerlinUnrealClient.cpp` into your Unreal project's `Source/<YourProject>/` directory.

## 2. Register the Class

- Add `#include "MerlinUnrealClient.h"` to your desired Actor or UI class.
- Add a `UPROPERTY()` of type `UMerlinUnrealClient*` to your class, and instantiate it (e.g., in `BeginPlay`).

## 3. Usage Example (Blueprint or C++)

- Call `SendChat(UserInput)` to send a message to Merlin.
- After the HTTP request completes, read the `MerlinReply` property for the response.
- You can expose this to Blueprints for easy UI integration.

## 4. REST API Endpoint

- By default, the client sends requests to `http://localhost:8000/merlin/chat`.
- Make sure your `merlin_api_server.py` is running and accessible from your Unreal project.
- Set `ApiKey` on `UMerlinUnrealClient` to match your `MERLIN_API_KEY`.

## 5. Example Blueprint Flow

1. Create a Blueprint based on your Actor/UI.
2. Add a variable of type `MerlinUnrealClient`.
3. On user input (e.g., button press), call `SendChat`.
4. Bind to a timer or event to check `MerlinReply` and update your UI.

## 6. Notes

- The HTTP request is asynchronous. You may want to trigger a UI update when `MerlinReply` changes.
- For production, update the API URL as needed.
- You can extend the class to support streaming or more advanced features.

---

For questions or advanced integration, see the comments in the C++ files or ask for further Unreal/Blueprint examples.
