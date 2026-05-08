# Production Deployment Guide

When you're ready to launch Revelator, use this checklist.

---

## **Database Migration**

### Current (Development)
- SQLite: `./forgeguard.db`
- Single file, no concurrency
- ❌ Not suitable for multiple users

### Production
- **Switch to: PostgreSQL**
- Supports concurrent users
- Easy backups and scaling
- Cloud-friendly (Heroku, AWS RDS, Railway, Supabase)

**Steps:**
1. Create PostgreSQL database (local or cloud)
2. Update `.env`: `DATABASE_URL=postgresql://user:password@host:5432/revelator`
3. Run migrations: `python -c "from backend.app.database import init_db; init_db()"`
4. SQLite → PostgreSQL dump (if migrating existing data)

**Recommended Providers:**
- Railway.app ($5/month)
- Supabase (free tier)
- AWS RDS (pay-as-you-go)
- DigitalOcean Managed Databases

---

## **LLM Setup**

### Current (Development)
- Ollama local (CPU/GPU intensive)
- Groq API (some endpoints)
- ❌ Local Ollama slow for production

### Production
- **Switch to: Groq API only**
- Fast (~500ms response)
- Cheap (~$0.001 per call)
- No server resources needed

**Changes Required:**
```env
# .env
USE_CLOUD_LLM=true
GROQ_API_KEY=gsk_...  # Get from https://console.groq.com/keys
GROQ_MODEL=llama-3.1-8b-instant
GROQ_VISION_MODEL=llama-4-vision-preview
```

**Disable Ollama:**
- Remove OLLAMA_URL and OLLAMA_MODEL from config, or
- Keep them but never use with `USE_CLOUD_LLM=true`

---

## **Image Storage**

### Current (Development)
- Stored on server: `./backend/uploads/`
- ❌ Limited disk space, scales poorly

### Production
- **Switch to: Cloud Storage**
- AWS S3, Google Cloud Storage, Cloudinary, or DigitalOcean Spaces

**Recommended for simplicity:**
- **Cloudinary** (free tier: 25GB/month, easy upload API)
- **DigitalOcean Spaces** ($5/month, S3-compatible)
- **AWS S3** (industry standard, pay-per-use)

**Implementation:**
1. Create cloud storage bucket
2. Update `/backend/app/routes/analyze.py` to upload to cloud instead of `./uploads/`
3. Return signed URLs for image retrieval
4. Delete local upload directory from server

---

## **User Data & Security**

### Authentication
- ✓ JWT tokens with bcrypt hashing (already done)
- ✓ Google OAuth support (already done)
- ✓ Refresh token rotation (already done)

### HTTPS
- Required for all production deployments
- Free SSL: Let's Encrypt (auto-renewal)
- Most hosting platforms (Railway, Render, Heroku) provide this automatically

### Payment Data
- ✓ Stripe/PayMongo handle all card data (PCI DSS compliant)
- ✓ You never see/store card numbers
- Keep webhook signatures verified (already done)

### Data Protection
- [ ] Add data deletion endpoint (`DELETE /api/auth/me` → delete user + scans)
- [ ] Privacy policy & terms of service
- [ ] GDPR compliance (for EU users)
- [ ] Regular automated backups (PostgreSQL)
- [ ] Encrypted database backups

### Secrets Management
- Never commit `.env` to git ✓
- Use hosting platform's environment variable management
- Rotate API keys periodically (Stripe, PayMongo, Groq)

---

## **Hosting Options**

### Tier 1: Easiest (Recommended for MVP)
- **Railway.app** — 1-click deploy FastAPI + PostgreSQL
  - ~$5-20/month depending on usage
  - Built-in SSL, no config needed
  - PostgreSQL included
  
- **Render.com** — similar to Railway
  - Free tier available
  - Good for starting out
  
- **Vercel** (for frontend only)
  - Next.js/React frontend
  - Backend on separate platform (Railway, Render, etc.)

### Tier 2: More Control
- **DigitalOcean App Platform** — managed containers
  - ~$12/month minimum
  - More customizable

- **AWS** (Elastic Beanstalk, ECS, Lambda)
  - Scalable but more complex
  - Best for high-traffic apps

### Tier 3: DIY (Advanced)
- **Docker** + VPS (DigitalOcean, Linode, Hetzner)
  - Full control
  - More infrastructure management

---

## **Deployment Checklist**

### Phase 1: Database & Storage
- [ ] Create PostgreSQL database
- [ ] Update `DATABASE_URL` in `.env`
- [ ] Set up cloud storage (S3/Cloudinary)
- [ ] Update image upload code

### Phase 2: LLM & API
- [ ] Get Groq API key from https://console.groq.com
- [ ] Set `USE_CLOUD_LLM=true`
- [ ] Test Groq API calls
- [ ] Remove Ollama dependency

### Phase 3: Security & Compliance
- [ ] Enable HTTPS/SSL
- [ ] Add CORS for your domain
- [ ] Add `.env` secrets to hosting platform
- [ ] Implement data deletion endpoint
- [ ] Create privacy policy & terms of service

### Phase 4: Reliability
- [ ] Set up automated daily backups
- [ ] Add error logging (Sentry, or platform logs)
- [ ] Add rate limiting on API
- [ ] Monitor disk usage alerts
- [ ] Monitor database connection limits

### Phase 5: Monitoring (Optional but Recommended)
- [ ] Set up application monitoring (New Relic, Datadog)
- [ ] Log API errors (Sentry, LogRocket)
- [ ] Monitor Groq API usage/costs
- [ ] Track payment webhook failures

### Phase 6: User Onboarding
- [ ] Domain & DNS setup
- [ ] Email verification working
- [ ] Password reset working
- [ ] Payment flow tested end-to-end
- [ ] Promo codes tested

---

## **Environment Variables (Production)**

```env
# Database
DATABASE_URL=postgresql://user:pass@host:5432/revelator

# JWT
SECRET_KEY=<generate-random-64-char-string>
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=30

# LLM (Groq only)
USE_CLOUD_LLM=true
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.1-8b-instant
GROQ_VISION_MODEL=llama-4-vision-preview

# Payments
STRIPE_SECRET_KEY=sk_live_...  # NOT test keys!
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID_PRO=price_...
STRIPE_PRICE_ID_PREMIUM=price_...

PAYMONGO_SECRET_KEY=sk_live_...  # NOT test keys!
PAYMONGO_PUBLIC_KEY=pk_live_...

# OAuth
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...

# URLs
FRONTEND_URL=https://yourdomain.com
API_URL=https://api.yourdomain.com

# Cloud Storage (if using S3)
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_S3_BUCKET=revelator-uploads
AWS_REGION=us-east-1

# Optional: Error logging
SENTRY_DSN=https://...
```

---

## **Cost Estimate (Monthly)**

| Service | Cost | Notes |
|---------|------|-------|
| Hosting (Railway) | $10-20 | Scales with usage |
| PostgreSQL | included | Included in Railway |
| Groq API | ~$5 | ~100K requests/month |
| S3/Cloudinary | $5-10 | Or included if free tier |
| Domain | $10-15 | Annual |
| **Total** | **$30-60** | Very affordable |

---

## **Testing Before Launch**

1. **Database**: Test concurrent user access
2. **Auth**: Test login, signup, Google OAuth, promo codes
3. **Payments**: Test Stripe & PayMongo with test keys first
4. **Images**: Upload, retrieve, delete from cloud storage
5. **LLM**: Test Groq API responses
6. **Load**: Simulate 10+ concurrent users
7. **Errors**: Test error handling, webhook failures
8. **Security**: SQL injection, XSS, CSRF tests

---

## **Post-Launch Monitoring**

- Check error logs daily for first week
- Monitor Groq API costs
- Monitor database disk usage
- Verify daily backups are running
- Check payment webhook logs
- Review user feedback

---

## **Rollback Plan**

If something goes wrong in production:
1. Revert to previous PostgreSQL backup
2. Revert frontend to last working commit
3. Monitor Groq API rate limits
4. Check payment webhook logs for failures

Keep backups for at least 7 days.

---

## **Useful Links**

- Railway: https://railway.app
- Render: https://render.com
- PostgreSQL Setup: https://www.postgresql.org/docs/
- Groq Console: https://console.groq.com
- AWS S3: https://aws.amazon.com/s3/
- Cloudinary: https://cloudinary.com
- Let's Encrypt: https://letsencrypt.org
- Sentry: https://sentry.io

---

**When you're ready to launch, start with Phase 1. Don't skip security checks in Phase 3.**
