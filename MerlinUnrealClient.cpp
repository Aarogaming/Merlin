// MerlinUnrealClient.cpp
// Unreal Engine C++ implementation for Merlin REST API chat
#include "MerlinUnrealClient.h"
#include "HttpModule.h"
#include "Interfaces/IHttpResponse.h"
#include "Json.h"
#include "JsonUtilities.h"

void UMerlinUnrealClient::SendChat(const FString& UserInput, const FString& UserId)
{
    FString Url = TEXT("http://localhost:8000/merlin/chat");
    TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Request = FHttpModule::Get().CreateRequest();
    Request->SetURL(Url);
    Request->SetVerb(TEXT("POST"));
    Request->SetHeader(TEXT("Content-Type"), TEXT("application/json"));
    Request->SetHeader(TEXT("X-Merlin-Key"), ApiKey);

    TSharedPtr<FJsonObject> JsonObject = MakeShareable(new FJsonObject);
    JsonObject->SetStringField(TEXT("user_input"), UserInput);
    JsonObject->SetStringField(TEXT("user_id"), UserId);
    FString RequestBody;
    TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&RequestBody);
    FJsonSerializer::Serialize(JsonObject.ToSharedRef(), Writer);
    Request->SetContentAsString(RequestBody);

    Request->OnProcessRequestComplete().BindUObject(this, &UMerlinUnrealClient::OnChatResponse);
    Request->ProcessRequest();
}

void UMerlinUnrealClient::GetChatHistory(const FString& UserId)
{
    FString Url = FString::Printf(TEXT("http://localhost:8000/merlin/history/%s"), *UserId);
    TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Request = FHttpModule::Get().CreateRequest();
    Request->SetURL(Url);
    Request->SetVerb(TEXT("GET"));
    Request->SetHeader(TEXT("Content-Type"), TEXT("application/json"));
    Request->SetHeader(TEXT("X-Merlin-Key"), ApiKey);
    Request->OnProcessRequestComplete().BindLambda([this](FHttpRequestPtr Req, FHttpResponsePtr Resp, bool bSuccess) {
        MerlinHistory.Empty();
        if (bSuccess && Resp.IsValid()) {
            TSharedPtr<FJsonObject> JsonObj;
            TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Resp->GetContentAsString());
            if (FJsonSerializer::Deserialize(Reader, JsonObj) && JsonObj.IsValid()) {
                const TArray<TSharedPtr<FJsonValue>>* HistoryArr;
                if (JsonObj->TryGetArrayField(TEXT("history"), HistoryArr)) {
                    for (const auto& Entry : *HistoryArr) {
                        if (Entry->Type == EJson::Object) {
                            TSharedPtr<FJsonObject> EntryObj = Entry->AsObject();
                            FString UserMsg = EntryObj->GetStringField(TEXT("user"));
                            FString MerlinMsg = EntryObj->GetStringField(TEXT("merlin"));
                            MerlinHistory.Add(FString::Printf(TEXT("You: %s\nMerlin: %s"), *UserMsg, *MerlinMsg));
                        }
                    }
                }
            }
        }
    });
    Request->ProcessRequest();
}

void UMerlinUnrealClient::OnChatResponse(FHttpRequestPtr Request, FHttpResponsePtr Response, bool bWasSuccessful)
{
    if (!bWasSuccessful || !Response.IsValid())
    {
        MerlinReply = TEXT("[Merlin API Error]");
        return;
    }
    FString ResponseStr = Response->GetContentAsString();
    TSharedPtr<FJsonObject> JsonObject;
    TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(ResponseStr);
    if (FJsonSerializer::Deserialize(Reader, JsonObject) && JsonObject.IsValid())
    {
        MerlinReply = JsonObject->GetStringField(TEXT("reply"));
    }
    else
    {
        MerlinReply = TEXT("[Invalid Merlin API Response]");
    }
}
