import json

with open('poster_cache.json', 'r', encoding='utf-8') as f:
    cache = json.load(f)

total = len(cache)
valid = [(k, v) for k, v in cache.items() if v and v.get('poster') and v['poster'] != 'N/A']
no_poster = [(k, v) for k, v in cache.items() if not v or not v.get('poster') or v['poster'] == 'N/A']

print(f"Total cache entries : {total}")
print(f"With valid poster   : {len(valid)}")
print(f"Without poster      : {len(no_poster)}")
print()
print("--- Sample valid posters ---")
for title, data in valid[:5]:
    print(f"  {title}: {data['poster'][:70]}")
print()
print("--- Titles with no poster ---")
for title, data in no_poster[:10]:
    print(f"  {title}")
