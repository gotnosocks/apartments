import json, sys

p = sys.argv[1]
if p.endswith(".json"):
    d = json.load(open(p))
    print(
        "COST",
        d.get("total_cost_usd"),
        "turns",
        d.get("num_turns"),
        "denials",
        d.get("permission_denials"),
    )
    print(d.get("result"))
    sys.exit()
cost, final, tools = 0.0, "", []
for line in open(p):
    try:
        e = json.loads(line)
    except Exception:
        continue
    if e.get("type") == "tool_execution_start":
        tools.append(f"{e.get('toolName')}: {json.dumps(e.get('args'))[:160]}")
    if e.get("type") == "message_end":
        m = e.get("message", {})
        if m.get("role") == "assistant":
            cost += (m.get("usage", {}).get("cost", {}) or {}).get("total", 0)
            txt = "".join(
                c.get("text", "")
                for c in m.get("content", [])
                if c.get("type") == "text"
            )
            if txt:
                final = txt
print("COST", round(cost, 4), "tool calls", len(tools))
print("\n".join(tools))
print("FINAL:\n" + final)
