// MerlinUnrealBlueprintExample.cpp
// Example Unreal Actor for Blueprint integration with Merlin
#include "MerlinUnrealBlueprintExample.h"

AMerlinUnrealBlueprintExample::AMerlinUnrealBlueprintExample()
{
    MerlinClient = NewObject<UMerlinUnrealClient>(this, UMerlinUnrealClient::StaticClass());
}

void AMerlinUnrealBlueprintExample::SendMerlinMessage(const FString& UserInput)
{
    if (MerlinClient)
    {
        MerlinClient->SendChat(UserInput);
    }
}

FString AMerlinUnrealBlueprintExample::GetMerlinReply() const
{
    return MerlinClient ? MerlinClient->MerlinReply : TEXT("");
}
