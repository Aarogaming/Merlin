import os
import importlib.util
import logging
import os


class MerlinPlugin:
    def __init__(
        self,
        name,
        description="",
        version="1.0.0",
        author="Unknown",
        category="general",
    ):
        self.name = name
        self.description = description
        self.version = version
        self.author = author
        self.category = category

    def execute(self, *args, **kwargs):
        raise NotImplementedError("Plugins must implement execute method")

    def get_info(self):
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "category": self.category,
        }


class PluginManager:
    def __init__(self, plugin_dir="plugins"):
        self.plugin_dir = plugin_dir
        self.plugins = {}
        if not os.path.exists(self.plugin_dir):
            os.makedirs(self.plugin_dir)

    def load_plugins(self):
        for filename in os.listdir(self.plugin_dir):
            if filename.endswith(".py") and not filename.startswith("__"):
                plugin_name = filename[:-3]
                file_path = os.path.join(self.plugin_dir, filename)

                spec = importlib.util.spec_from_file_location(plugin_name, file_path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    try:
                        spec.loader.exec_module(module)
                    except Exception as e:
                        logging.warning(
                            f"Skipping plugin {plugin_name} due to import error: {e}"
                        )
                        continue

                if hasattr(module, "get_plugin"):
                    self.plugins[plugin_name] = module.get_plugin()
                    logging.info(f"Loaded plugin: {plugin_name}")

    def execute_plugin(self, name, *args, **kwargs):
        if name in self.plugins:
            return self.plugins[name].execute(*args, **kwargs)
        return {"error": f"Plugin {name} not found"}

    def list_plugin_info(self):
        return {name: plugin.get_info() for name, plugin in self.plugins.items()}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    pm = PluginManager()
    pm.load_plugins()
    print(f"Loaded plugins: {list(pm.plugins.keys())}")
