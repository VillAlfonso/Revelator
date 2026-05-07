# Admin Features — Later Phase

You asked to skip admin/promo-codes/ban for now until we know how Firebase handles it. Here are the facts and a recommended path when you're ready.

## TL;DR

| Feature       | Firebase mechanism                                      | Effort |
|---------------|---------------------------------------------------------|--------|
| Admin role    | **Custom claims** on the auth token                     | Low    |
| Super-admin   | Same — `role: "superadmin"` claim                       | Low    |
| Ban user      | `auth.update_user(uid, disabled=True)` (built-in)       | Low    |
| Promo codes   | `promo_codes` Firestore collection + 1 backend endpoint | Medium |
| Audit log     | `admin_logs` Firestore collection (append-only)         | Low    |

Firebase covers all of this. Nothing forces you to drop features — they're just done with Firebase primitives instead of SQL tables.

---

## 1. Admin / super-admin role

Firebase Auth supports **custom claims** — small key/value pairs attached to a user's ID token. Read by both backend (firebase-admin) and frontend (decoded ID token).

**Set from a backend-only endpoint:**
```python
from firebase_admin import auth as fb_auth

@router.post("/admin/promote")
def promote(uid: str, current_user: dict = Depends(get_super_admin)):
    fb_auth.set_custom_user_claims(uid, {"admin": True})
```

**Read on the frontend:**
```js
const token = await user.getIdTokenResult(true);  // forceRefresh after promotion
const isAdmin = token.claims.admin === true;
```

**Gate Firestore writes via Security Rules:**
```js
match /admin_logs/{doc} {
  allow read, write: if request.auth.token.admin == true;
}
```

This is **better** than the SQLite version — claims are signed and cached on every request, so the frontend can render admin UI without a round-trip.

**Bootstrapping the first super-admin:** there's no UI for it — you set it once with a script:
```python
# scripts/make_super_admin.py
fb_auth.set_custom_user_claims("YOUR_UID", {"admin": True, "superadmin": True})
```

---

## 2. Ban / unban

Firebase has this built-in:

```python
fb_auth.update_user(uid, disabled=True)   # ban — user can no longer sign in
fb_auth.update_user(uid, disabled=False)  # unban
```

When `disabled=True`:
- Existing sessions get rejected on next ID-token verify (within ~1 hour, or instantly if you check `auth.token.firebase.sign_in_provider` claim freshness).
- New sign-in attempts return `auth/user-disabled`.

That's the whole feature. No DB column needed.

---

## 3. Promo codes

This is where the SQLite version had real complexity (uniqueness, max_uses counter, expiry). On Firestore it's the same logic, just different storage:

**Schema** — `promo_codes/{code}`:
```js
{
  plan: "pro" | "premium",
  max_uses: 100,
  uses: 0,
  expires_at: <timestamp>,
  active: true,
  created_by: "<admin_uid>",
  created_at: <timestamp>,
}
```

**Redemption** runs as a Firestore **transaction** so the counter can't double-redeem under concurrency:

```python
@router.post("/redeem-code")
def redeem_code(body: RedeemRequest, current_user: dict = Depends(get_current_user)):
    code_ref = db().collection("promo_codes").document(body.code)
    user_ref = db().collection("users").document(current_user["uid"])

    @firestore.transactional
    def txn(t):
        code_snap = code_ref.get(transaction=t)
        if not code_snap.exists: raise HTTPException(404, "Invalid code")
        code = code_snap.to_dict()
        if not code.get("active"): raise HTTPException(400, "Code is deactivated")
        if code["uses"] >= code["max_uses"]: raise HTTPException(400, "Code fully redeemed")
        if code["expires_at"] and _now() > code["expires_at"]: raise HTTPException(400, "Code expired")

        t.update(code_ref, {"uses": firestore.Increment(1)})
        t.update(user_ref, {"plan": code["plan"], "updated_at": _now()})

    txn(db().transaction())
    return {"ok": True, "plan": code["plan"]}
```

**Recommendation for capstone:** *defer this*. For a 30-person demo you don't need codes — just upgrade demo users manually from the Firebase console. Build it post-defense if it has product value.

---

## 4. Audit log

Append-only Firestore collection `admin_logs`:

```js
{
  admin_uid: "...",
  action: "ban" | "promote" | "redeem_code" | "set_plan",
  target_uid: "...",
  details: { ... },
  created_at: <timestamp>,
}
```

Add it as a `db().collection("admin_logs").add({...})` at the end of every admin endpoint. Security rule: `read, create` if `request.auth.token.admin == true`, no update or delete (immutable).

---

## When to add the admin panel

**Build it when** any of these is true:
- You have >50 users and managing them in the Firebase console is awkward.
- You actually use promo codes for marketing (capstone presentations don't count).
- A teammate needs to ban abusers and you don't want to give them Firebase project access.

**Until then** the Firebase console is a fine admin UI:
- Auth tab → search/disable users
- Firestore → manually edit `users/{uid}.plan`
- That's all the SQL-version admin panel did anyway.

---

## Cost of postponing

Zero. All four features are additive — nothing in the v2 schema or rules will need migration when you bring them back. The `users` doc already has the right shape, and adding custom claims doesn't touch Firestore at all.

---

## Recommended order when you do build them

1. **Custom claims + super-admin promotion script** (1 hour) — needed before anything else admin.
2. **Ban / unban endpoint + frontend toggle** (1 hour) — easiest user-facing win.
3. **Audit log writes** (30 min) — add to every admin endpoint as you build them.
4. **Stats dashboard** (2 hours) — Firestore aggregate queries for total users, scans, plan distribution.
5. **Promo codes** (4 hours) — only if you actually need them.
