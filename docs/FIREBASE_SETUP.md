# Firebase Setup

Both the FastAPI backend and the React web app talk to the same Firebase project. The backend uses the **Admin SDK** (server-side, full privileges); the web app uses the **Web SDK** (client-side, gated by Security Rules).

## 1. Create a Firebase project

1. Go to https://console.firebase.google.com → **Add project**.
2. Name it (e.g. `revelator`). Disable Analytics if you want.
3. Once created, you land on the project overview.

## 2. Enable Authentication

1. Left nav → **Build → Authentication → Get started**.
2. **Sign-in method** tab → enable:
   - **Email/Password**
   - **Google** (set support email = your email)

## 3. Create Firestore database

1. Left nav → **Build → Firestore Database → Create database**.
2. Start in **production mode** (we'll write the rules in step 6).
3. Pick the closest region. **You cannot change this later.**

## 4. Enable Storage

1. Left nav → **Build → Storage → Get started**.
2. Same region as Firestore.

## 5. Get the Web SDK config (for the web app)

1. Project overview → **Web** icon (`</>`) under "Add an app".
2. Register the app (nickname: `revelator-web`). Skip hosting.
3. Copy the `firebaseConfig` object. You need 6 values:
   - `apiKey`, `authDomain`, `projectId`, `storageBucket`, `messagingSenderId`, `appId`
4. Paste these into `web/.env` (created from `web/.env.example`).

## 6. Get the Admin SDK service account (for the backend)

1. Project settings (gear icon) → **Service accounts** → **Generate new private key**.
2. Save the downloaded JSON outside source control. A common path: `backend/firebase-service-account.json` (already in `.gitignore`).
3. In `backend/.env`, set:
   ```
   FIREBASE_CREDENTIALS_FILE=./firebase-service-account.json
   FIREBASE_STORAGE_BUCKET=<projectId>.appspot.com
   ```

## 7. Security Rules

### Firestore — paste this in **Firestore → Rules**:

```js
rules_version = '2';
service cloud.firestore { 
  match /databases/{database}/documents {

    // Users can read/update their own profile. Backend (Admin SDK) bypasses these.
    match /users/{uid} {
      allow read, update: if request.auth != null && request.auth.uid == uid;
      allow create: if request.auth != null && request.auth.uid == uid;
      allow delete: if false;
    }

    // Users can read scans they own. Only the backend writes scans.
    match /scans/{scanId} {
      allow read: if request.auth != null && resource.data.user_id == request.auth.uid;
      allow write: if false;  // Admin SDK only
    }
  }
}
```

### Storage — paste this in **Storage → Rules**:

```js
rules_version = '2';
service firebase.storage {
  match /b/{bucket}/o {
    // Each user can read images under their own folder. Admin SDK writes them.
    match /users/{uid}/scans/{scanId} {
      allow read: if request.auth != null && request.auth.uid == uid;
      allow write: if false;  // Admin SDK only
    }
  }
}
```

Click **Publish** on both.

## 8. Create Firestore indexes

The History page queries `scans` filtered by `user_id` and ordered by `created_at desc`. Firestore needs a composite index for that.

The first time you load History, Firestore will throw an error in the console with a one-click link to create the index. Click it.

(Alternatively: **Firestore → Indexes → Add index** with collection `scans`, fields `user_id Ascending, created_at Descending`.)

## 9. Authorized domains for Auth

If you deploy the web app to a domain other than localhost:

**Authentication → Settings → Authorized domains → Add domain** for each domain that will serve the app (Vercel domain, your custom domain, etc.). Without this, Google sign-in popups fail with `auth/unauthorized-domain`.

---

You're ready to run.

```bash
# backend
cd v2/backend
pip install -r requirements.txt
python run.py

# web (separate shell)
cd v2/web
npm install
npm run dev
```
