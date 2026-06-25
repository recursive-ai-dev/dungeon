import sys

with open('entities/__init__.py', 'r') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if "from .components import (" in line:
        new_lines.append("from .components import (\n")
    elif "from .consumables import (" in line:
        new_lines.append("from .consumables import (\n")
    elif "from .ai import (" in line:
        new_lines.append("from .ai import (\n")
    elif "from .spells import (" in line:
        new_lines.append("from .spells import (\n")
    elif "from .status_effects import (" in line:
        new_lines.append("from .status_effects import (\n")
    else:
        new_lines.append(line)

with open('entities/__init__.py', 'w') as f:
    f.writelines(new_lines)
