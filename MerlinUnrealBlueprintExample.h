// MerlinUnrealBlueprintExample.h
// Example Unreal Actor for Blueprint integration with Merlin
#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "MerlinUnrealClient.h"
#include "MerlinUnrealBlueprintExample.generated.h"

UCLASS()
class AMerlinUnrealBlueprintExample : public AActor
{
    GENERATED_BODY()
public:
    AMerlinUnrealBlueprintExample();

    UPROPERTY(BlueprintReadWrite, EditAnywhere, Category="Merlin")
    UMerlinUnrealClient* MerlinClient;

    UFUNCTION(BlueprintCallable, Category="Merlin")
    void SendMerlinMessage(const FString& UserInput);

    UFUNCTION(BlueprintPure, Category="Merlin")
    FString GetMerlinReply() const;
};
