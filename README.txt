POCKETPULSE - Integrated project

Features:
- Register/login with password hashing
- User-specific income and expense transactions
- Edit/delete transactions
- Dashboard summaries, month filter and charts
- Export your transactions to CSV
- Monthly budgets with 80% and limit alerts
- Savings goals and saved-amount progress
- Recurring transaction rules (manual creation, not automatic bank payments)
- Profile settings and optional password change
- CSRF protection on POST forms

Run on Windows:
1. Copy/backup your existing PocketPulse folder first.
2. Copy app.py, requirements.txt, templates folder and static folder into your project folder.
3. Open terminal in that folder.
4. Run: python -m pip install -r requirements.txt
5. Run: python app.py
6. Open http://127.0.0.1:5000

Database note:
This app uses SQLite at Flask's instance/pocketpulse.db. db.create_all() creates the new tables for budget, savings goals and recurring rules without deleting existing tables. Back up your database before changing code.

Security note:
For a real deployment, set a strong SECRET_KEY environment variable and disable debug mode.
