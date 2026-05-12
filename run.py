#!/usr/bin/env python3
# Standard library imports
import sys
from pathlib import Path

# Add parent directory to path for package imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Third-party imports
# (none)

# Local imports
from dungeon.main import DungeonApp
from dungeon.multi_ui import run_multiplayer


def main():
    print("=" * 50)
    print("       TUI DUNGEON")
    print("=" * 50)
    print()
    print("Select game mode:")
    print("  1) Single Player")
    print("  2) LAN Multiplayer")
    print("  3) Exit")
    print()

    while True:
        choice = input("Enter choice (1-3): ").strip()

        if choice == "1":
            app = DungeonApp()
            app.run()
            break
        elif choice == "2":
            run_multiplayer()
            break
        elif choice == "3":
            print("Goodbye!")
            break
        else:
            print("Invalid choice. Please enter 1, 2, or 3.")


if __name__ == "__main__":
    main()