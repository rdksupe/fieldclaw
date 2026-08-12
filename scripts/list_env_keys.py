import os

files = [
    "/home/rdksupe/building_shit/buildsync/apps/api/.env",
    "/home/rdksupe/building_shit/buildsync/kb/projects/1a58398d-514c-4472-9583-baf7c934b567/.env",
    "/home/rdksupe/building_shit/buildsync/kb/projects/67e47a35-522a-485c-8342-6523952a530e/.env",
    "/home/rdksupe/building_shit/buildsync/sim/.env.sim",
]
for f in files:
    if not os.path.exists(f):
        print(f"\n### {f} -- MISSING"); continue
    print(f"\n### {f}")
    keys = []
    for raw in open(f):
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        keys.append(line.split("=", 1)[0].strip())
    for k in sorted(keys):
        print("  -", k)
