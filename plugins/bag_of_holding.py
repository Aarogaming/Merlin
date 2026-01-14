# Merlin Plugin: The Bag of Holding (Dimensional Storage)
import os
import json
import shutil
from merlin_logger import merlin_logger

class BagOfHolding:
    def __init__(self, storage_root="merlin_vault"):
        self.name = "bag_of_holding"
        self.description = "A dimensional storage space for the Architect's snippets, files, and secrets."
        self.category = "Utility"
        self.storage_path = storage_root
        os.makedirs(self.storage_path, exist_ok=True)

    def execute(self, spell_type: str, item_name: str = "", content: str = ""):
        merlin_logger.info(f"Merlin reaching into the Bag of Holding: {spell_type} for {item_name}")

        try:
            if spell_type == "store":
                # Store a snippet or reference
                with open(os.path.join(self.storage_path, f"{item_name}.txt"), "w") as f:
                    f.write(content)
                return {"output": f"Placed {item_name} into the Bag of Holding. It is safe within the void."}

            elif spell_type == "retrieve":
                # Retrieve an item
                path = os.path.join(self.storage_path, f"{item_name}.txt")
                if os.path.exists(path):
                    with open(path, "r") as f:
                        data = f.read()
                    return {"output": f"Pulled {item_name} from the Bag of Holding:\n{data}"}
                return {"error": f"I cannot find {item_name} in the dimensional void."}

            elif spell_type == "inventory":
                # List all items in the bag
                items = os.listdir(self.storage_path)
                return {"output": f"The Bag of Holding contains: {', '.join([i.replace('.txt', '') for i in items])}"}

            else:
                return {"error": f"Unknown dimensional command: {spell_type}"}

        except Exception as e:
            return {"error": f"The void is unstable: {str(e)}"}

def get_plugin():
    return BagOfHolding()
