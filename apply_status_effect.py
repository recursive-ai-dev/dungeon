import sys

with open('storylets.py') as f:
    lines = f.readlines()

new_lines = []
skip = 0
for i, line in enumerate(lines):
    if skip > 0:
        skip -= 1
        continue
    if "elif effect.effect_type == StoryletEffectType.STATUS_EFFECT:" in line:
        new_lines.append(line)
        new_lines.append("            from entities.status_effects import StatusEffect\n")
        new_lines.append("            new_effect = StatusEffect(name=str(effect.value), duration=effect.duration, power=1)\n")
        new_lines.append("            msg = engine.player.fighter.status_effects.add_effect(new_effect, engine.player.fighter, engine)\n")
        new_lines.append("            engine.messages.append(f\"You feel {effect.value}. {msg}\")\n")
        skip = 3 # skip the old lines 171-173
    else:
        new_lines.append(line)

with open('storylets.py', 'w') as f:
    f.writelines(new_lines)
