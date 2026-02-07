import argparse
import json
import sys
from merlin_tasks import task_manager
from merlin_plugin_manager import PluginManager
from merlin_system_info import get_system_info


def main():
    parser = argparse.ArgumentParser(description="Merlin Merlin CLI")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Tasks
    task_parser = subparsers.add_parser("task", help="Manage tasks")
    task_subparsers = task_parser.add_subparsers(
        dest="subcommand", help="Task subcommands"
    )

    task_subparsers.add_parser("list", help="List all tasks")

    add_task_parser = task_subparsers.add_parser("add", help="Add a new task")
    add_task_parser.add_argument("title", help="Task title")
    add_task_parser.add_argument("--description", default="", help="Task description")
    add_task_parser.add_argument("--priority", default="Medium", help="Task priority")

    # Plugins
    plugin_parser = subparsers.add_parser("plugin", help="Manage plugins")
    plugin_subparsers = plugin_parser.add_subparsers(
        dest="subcommand", help="Plugin subcommands"
    )
    plugin_subparsers.add_parser("list", help="List all plugins")

    # System
    subparsers.add_parser("info", help="Show system info")

    args = parser.parse_args()

    if args.command == "task":
        if args.subcommand == "list":
            print(json.dumps(task_manager.list_tasks(), indent=2))
        elif args.subcommand == "add":
            task = task_manager.add_task(args.title, args.description, args.priority)
            print(f"Added task: {task['id']}")

    elif args.command == "plugin":
        if args.subcommand == "list":
            pm = PluginManager()
            pm.load_plugins()
            print(json.dumps(pm.list_plugin_info(), indent=2))

    elif args.command == "info":
        print(json.dumps(get_system_info(), indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
