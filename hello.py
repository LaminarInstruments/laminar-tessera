from tessera.store import Store

s = Store()          # a safe little box to put stuff in
s.put("widgets", 120)
print(s.get("widgets"))
