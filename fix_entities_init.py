import sys

with open('entities/__init__.py') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    # Convert relative imports to absolute imports for specific modules
    if any(m in line for m in [".components", ".consumables", ".ai", ".spells", ".status_effects"]) and "from ." in line:
        new_lines.append(line.replace("from .", "from entities.", 1))
    else:
        new_lines.append(line)

with open('entities/__init__.py', 'w') as f:
    f.writelines(new_lines)
