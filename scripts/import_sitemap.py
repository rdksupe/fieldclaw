import json, os, urllib.request, urllib.error

base = os.environ["FIELDCLAW_BASE_URL"]
pid  = "81989611-f0f4-496c-a197-17a2220bea8b"
key  = os.environ["FIELDCLAW_API_KEY"]

gj = json.load(open("/home/rdksupe/building_shit/buildsync/kb/projects/81989611-f0f4-496c-a197-17a2220bea8b/wiki/sources/human-dc1-site-logistics.geojson"))

def req(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    rq = urllib.request.Request(url, data=data, method=method,
        headers={"X-API-Key": key, "Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(rq)
        return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

url = f"{base}/api/projects/{pid}/sitemap"
code, resp = req("POST", url, {"geojson": gj, "replace": True})
print("SITEMAP", code, resp[:800])
code, resp = req("GET", f"{base}/api/projects/{pid}/zones")
print("ZONES", code, resp)
