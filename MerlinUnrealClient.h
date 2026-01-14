// MerlinUnrealClient.h
// Unreal Engine C++ header for Merlin REST API chat
#pragma once
#include "CoreMinimal.h"
#include "Http.h"
#include "MerlinUnrealClient.generated.h"

UCLASS(Blueprintable)
class UMerlinUnrealClient : public UObject
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable, Category="Merlin")
    void SendChat(const FString& UserInput, const FString& UserId = TEXT("default"));

    UFUNCTION(BlueprintCallable, Category="Merlin")
    void GetChatHistory(const FString& UserId = TEXT("default"));

    UPROPERTY(BlueprintReadWrite, Category="Merlin")
    TArray<FString> MerlinHistory;

    UPROPERTY(BlueprintReadWrite, Category="Merlin")
    FString MerlinReply;

    UPROPERTY(BlueprintReadWrite, Category="Merlin")
    FString ApiKey = TEXT("merlin-secret-key");

private:
    void OnChatResponse(FHttpRequestPtr Request, FHttpResponsePtr Response, bool bWasSuccessful);
};
