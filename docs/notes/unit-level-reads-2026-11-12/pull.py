import sys, json

sys.path.insert(0, "/data1/apartments/serve/master/frontier/src")
from rentfrontier import api_records

ids = set(json.load(open(sys.argv[1])))
out = open(sys.argv[2], "w")
r = api_records.records_file()
n = 0
for x in api_records.captures(
    r, ["listing_id", "collected_at", "snapshot_id", "raw_listing_json"]
):
    if x["listing_id"] in ids:
        x["collected_at"] = str(x["collected_at"])
        out.write(json.dumps(x) + "\n")
        n += 1
print(n)
