import re
import sys
from statistics import mean

line_re = re.compile(
    r"METRICS query=(?P<query>.*?) tools_used=\[(?P<tools>.*?)\] tool_calls=(?P<tool_calls>\d+)"
    r" iterations=(?P<iterations>\d+) latency_ms=(?P<latency>\d+)"
    r" tokens_input=(?P<in>\d+) tokens_output=(?P<out>\d+) cost=(?P<cost>[\d\.]+)"
    r" success=(?P<success>True|False) error_type=(?P<error>None|[\w_]+)"
    r" grounded=(?P<grounded>True|False) invalid_id_blocked=(?P<invalid>True|False)"
)

rows = []
for line in sys.stdin:
    m = line_re.search(line)
    if not m:
        continue
    d = m.groupdict()
    d["tool_calls"] = int(d["tool_calls"])
    d["iterations"] = int(d["iterations"])
    d["latency"] = int(d["latency"])
    d["in"] = int(d["in"])
    d["out"] = int(d["out"])
    d["cost"] = float(d["cost"])
    d["success"] = d["success"] == "True"
    d["grounded"] = d["grounded"] == "True"
    d["invalid"] = d["invalid"] == "True"
    rows.append(d)

if not rows:
    print("No metrics found")
    sys.exit(0)

total = len(rows)
success_rate = sum(1 for r in rows if r["success"]) / total
grounded_rate = sum(1 for r in rows if r["grounded"]) / total
invalid_block_rate = sum(1 for r in rows if r["invalid"]) / total

print("Total:", total)
print("Success rate:", round(success_rate * 100, 2), "%")
print("Grounded rate (no inventar):", round(grounded_rate * 100, 2), "%")
print("Invalid ID blocked rate:", round(invalid_block_rate * 100, 2), "%")
print("Avg tool calls:", round(mean(r["tool_calls"] for r in rows), 2))
print("Avg iterations:", round(mean(r["iterations"] for r in rows), 2))
print("Avg latency ms:", round(mean(r["latency"] for r in rows), 2))
print("Avg cost:", round(mean(r["cost"] for r in rows), 6))