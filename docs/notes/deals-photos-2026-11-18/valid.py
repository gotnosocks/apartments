import json, sys

for line in sys.stdin:
    try:
        d = json.loads(line)
        if (
            isinstance(d, dict)
            and "label" in d
            and isinstance(d.get("categories"), list)
        ):
            sys.stdout.write(line)
    except ValueError:
        pass
