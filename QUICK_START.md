# Quick Start - New Features

## Email Rating System

### 1. Run Database Migration
```bash
flask db upgrade
```

### 2. Validate Emails
When you validate emails, ratings are automatically calculated and assigned:
- A = 80-100 (Excellent)
- B = 60-79 (Good)
- C = 40-59 (Fair)
- D = 0-39 (Poor)

### 3. View Ratings on Dashboard
Go to Dashboard → See "Email Quality Ratings" section with breakdown by A/B/C/D

### 4. Export by Rating
Go to Export → Check desired ratings (A, B, C, or D) → Export

---

## Random Limit Export

### Quick Usage
1. Go to Export page
2. Check "Limit to Random Sample"
3. Enter number of emails (e.g., 5000)
4. Select export type and click "Start Export"

---

## Real-time Job Monitoring

### Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Start Redis (required for WebSocket)
redis-server

# Start Flask with SocketIO support
python run.py

# Start Celery worker
celery -A celery_worker.celery_app worker --loglevel=info
```

### Usage
1. Start any job (import, validate, export)
2. Navigate to job status page
3. Watch progress update in real-time without page refresh
4. See "Connected" badge when WebSocket is active

---

## Quick Test

### Test Rating System
```bash
# After migration, check ratings
flask shell
>>> from app.models.email import Email
>>> Email.query.filter_by(rating='A').count()
>>> Email.query.filter_by(rating='B').count()
```

### Test Random Export
1. Upload 1000 emails
2. Export with random limit = 100
3. Verify export has exactly 100 emails

### Test Real-time Monitoring
1. Upload large file (10,000+ emails)
2. Watch job status page
3. Verify progress bar updates without page refresh

---

## Troubleshooting

### SocketIO not working?
```bash
# Check Redis
redis-cli ping
# Should return: PONG

# Check Flask-SocketIO
pip list | grep Flask-SocketIO
# Should show: Flask-SocketIO 5.3.5
```

### Ratings not showing?
```bash
# Re-run migration
flask db upgrade

# Or manually update
flask shell
>>> from app.models.email import Email
>>> emails = Email.query.filter(Email.quality_score.isnot(None)).all()
>>> for e in emails:
...     e.update_rating()
>>> from app import db
>>> db.session.commit()
```

---

## Next Steps

1. ✅ Run database migration
2. ✅ Test rating system on validation
3. ✅ Verify dashboard shows ratings
4. ✅ Test export with rating filter
5. ✅ Test random limit export
6. ✅ Test WebSocket real-time monitoring

See **NEW_FEATURES_GUIDE.md** for complete documentation.
