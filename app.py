import os
import csv
import io
from datetime import date, datetime, timedelta
from decimal import Decimal
from flask import Flask, render_template, redirect, url_for, flash, request, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm, CSRFProtect
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash
from wtforms import StringField, PasswordField, SubmitField, DecimalField, SelectField, DateField, EmailField
from wtforms.validators import DataRequired, Email, Length, EqualTo, NumberRange, Optional

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'pocketpulse-change-this-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pocketpulse.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
csrf = CSRFProtect(app)

CATEGORIES = [('Food','Food'),('Travel','Travel'),('Shopping','Shopping'),('Education','Education'),('Bills','Bills'),('Health','Health'),('Salary','Salary'),('Other','Other')]

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(40), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    transactions = db.relationship('Transaction', backref='owner', lazy=True, cascade='all, delete-orphan')
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Numeric(12,2), nullable=False)
    kind = db.Column(db.String(10), nullable=False)
    category = db.Column(db.String(40), nullable=False)
    description = db.Column(db.String(200), nullable=False, default='')
    transaction_date = db.Column(db.Date, nullable=False, default=date.today)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)

class MonthlyBudget(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    month = db.Column(db.String(7), nullable=False)
    amount = db.Column(db.Numeric(12,2), nullable=False)
    __table_args__ = (db.UniqueConstraint('user_id','month', name='unique_user_month_budget'),)

class SavingsGoal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    title = db.Column(db.String(80), nullable=False)
    target_amount = db.Column(db.Numeric(12,2), nullable=False)
    saved_amount = db.Column(db.Numeric(12,2), nullable=False, default=0)
    target_date = db.Column(db.Date, nullable=True)

class RecurringTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    amount = db.Column(db.Numeric(12,2), nullable=False)
    kind = db.Column(db.String(10), nullable=False)
    category = db.Column(db.String(40), nullable=False)
    description = db.Column(db.String(200), nullable=False, default='')
    frequency = db.Column(db.String(20), nullable=False, default='monthly')
    next_date = db.Column(db.Date, nullable=False, default=date.today)
    active = db.Column(db.Boolean, nullable=False, default=True)

class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3,max=40)])
    email = EmailField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8,max=128)])
    confirm_password = PasswordField('Confirm password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Create account')

class LoginForm(FlaskForm):
    email = EmailField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class TransactionForm(FlaskForm):
    kind = SelectField('Type', choices=[('expense','Expense'),('income','Income')], validators=[DataRequired()])
    amount = DecimalField('Amount (₹)', places=2, validators=[DataRequired(), NumberRange(min=Decimal('0.01'))])
    category = SelectField('Category', choices=CATEGORIES, validators=[DataRequired()])
    description = StringField('Description', validators=[Optional(), Length(max=200)])
    transaction_date = DateField('Date', default=date.today, validators=[DataRequired()])
    submit = SubmitField('Save transaction')

class BudgetForm(FlaskForm):
    month = StringField('Month (YYYY-MM)', validators=[DataRequired(), Length(min=7,max=7)])
    amount = DecimalField('Monthly budget (₹)', places=2, validators=[DataRequired(), NumberRange(min=Decimal('0.01'))])
    submit = SubmitField('Save budget')

class GoalForm(FlaskForm):
    title = StringField('Goal name', validators=[DataRequired(), Length(min=2,max=80)])
    target_amount = DecimalField('Target amount (₹)', places=2, validators=[DataRequired(), NumberRange(min=Decimal('0.01'))])
    saved_amount = DecimalField('Already saved (₹)', places=2, default=Decimal('0'), validators=[DataRequired(), NumberRange(min=Decimal('0'))])
    target_date = DateField('Target date (optional)', validators=[Optional()])
    submit = SubmitField('Add goal')

class RecurringForm(FlaskForm):
    kind = SelectField('Type', choices=[('expense','Expense'),('income','Income')], validators=[DataRequired()])
    amount = DecimalField('Amount (₹)', places=2, validators=[DataRequired(), NumberRange(min=Decimal('0.01'))])
    category = SelectField('Category', choices=CATEGORIES, validators=[DataRequired()])
    description = StringField('Description', validators=[Optional(), Length(max=200)])
    frequency = SelectField('Repeat', choices=[('weekly','Weekly'),('monthly','Monthly')], validators=[DataRequired()])
    next_date = DateField('Next due date', default=date.today, validators=[DataRequired()])
    submit = SubmitField('Save recurring rule')

@login_manager.user_loader
def load_user(user_id): return db.session.get(User, int(user_id))

@app.route('/')
def home(): return redirect(url_for('dashboard' if current_user.is_authenticated else 'login'))

@app.route('/register', methods=['GET','POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    form = RegisterForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        if db.session.scalar(select(User).where(User.email == email)):
            flash('An account with this email already exists.', 'error')
        else:
            user = User(username=form.username.data.strip(), email=email)
            user.set_password(form.password.data)
            db.session.add(user)
            try:
                db.session.commit(); flash('Account created. Please log in.', 'success'); return redirect(url_for('login'))
            except IntegrityError:
                db.session.rollback(); flash('That email is already registered.', 'error')
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET','POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.scalar(select(User).where(User.email == form.email.data.strip().lower()))
        if user and user.check_password(form.password.data):
            login_user(user); return redirect(url_for('dashboard'))
        flash('Incorrect email or password.', 'error')
    return render_template('login.html', form=form)

@app.route('/dashboard', methods=['GET','POST'])
@login_required
def dashboard():
    form = TransactionForm()
    selected_month = request.args.get('month','')
    if form.validate_on_submit():
        item = Transaction(amount=form.amount.data, kind=form.kind.data, category=form.category.data,
            description=(form.description.data or '').strip(), transaction_date=form.transaction_date.data, user_id=current_user.id)
        db.session.add(item); db.session.commit(); flash('Transaction saved successfully.', 'success')
        return redirect(url_for('dashboard', month=selected_month) if selected_month else url_for('dashboard'))
    all_transactions = db.session.scalars(select(Transaction).where(Transaction.user_id == current_user.id).order_by(Transaction.transaction_date.desc(), Transaction.id.desc())).all()
    available_months = sorted({t.transaction_date.strftime('%Y-%m') for t in all_transactions}, reverse=True)
    transactions = all_transactions
    if selected_month:
        try: datetime.strptime(selected_month, '%Y-%m')
        except ValueError: selected_month = ''
        if selected_month: transactions = [t for t in all_transactions if t.transaction_date.strftime('%Y-%m') == selected_month]
    income = sum((t.amount for t in transactions if t.kind == 'income'), Decimal('0.00'))
    expenses = sum((t.amount for t in transactions if t.kind == 'expense'), Decimal('0.00'))
    balance = income - expenses
    expense_totals = {}
    monthly = {}
    for t in transactions:
        key = t.transaction_date.strftime('%Y-%m')
        monthly.setdefault(key, {'income': Decimal('0'), 'expense': Decimal('0')})
        monthly[key][t.kind] += t.amount
        if t.kind == 'expense': expense_totals[t.category] = expense_totals.get(t.category, Decimal('0')) + t.amount
    monthly_keys = sorted(monthly)
    budget_month = selected_month or date.today().strftime('%Y-%m')
    budget = db.session.scalar(select(MonthlyBudget).where(MonthlyBudget.user_id == current_user.id, MonthlyBudget.month == budget_month))
    budget_spent = sum((t.amount for t in all_transactions if t.kind == 'expense' and t.transaction_date.strftime('%Y-%m') == budget_month), Decimal('0'))
    goals = db.session.scalars(select(SavingsGoal).where(SavingsGoal.user_id == current_user.id).order_by(SavingsGoal.id.desc())).all()
    return render_template('dashboard.html', form=form, transactions=transactions[:100], income=income, expenses=expenses, balance=balance,
        expense_labels=list(expense_totals), expense_values=[float(v) for v in expense_totals.values()],
        monthly_labels=[datetime.strptime(k,'%Y-%m').strftime('%b %Y') for k in monthly_keys],
        monthly_income_values=[float(monthly[k]['income']) for k in monthly_keys], monthly_expense_values=[float(monthly[k]['expense']) for k in monthly_keys],
        selected_month=selected_month, available_months=available_months, budget=budget, budget_month=budget_month,
        budget_spent=budget_spent, goals=goals)

@app.route('/transaction/delete/<int:transaction_id>', methods=['POST'])
@login_required
def delete_transaction(transaction_id):
    item = db.session.scalar(select(Transaction).where(Transaction.id == transaction_id, Transaction.user_id == current_user.id))
    if not item: flash('Transaction not found.', 'error')
    else: db.session.delete(item); db.session.commit(); flash('Transaction deleted.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/transaction/edit/<int:transaction_id>', methods=['GET','POST'])
@login_required
def edit_transaction(transaction_id):
    item = db.session.scalar(select(Transaction).where(Transaction.id == transaction_id, Transaction.user_id == current_user.id))
    if not item: flash('Transaction not found.', 'error'); return redirect(url_for('dashboard'))
    form = TransactionForm(obj=item)
    if form.validate_on_submit():
        item.amount=form.amount.data; item.kind=form.kind.data; item.category=form.category.data
        item.description=(form.description.data or '').strip(); item.transaction_date=form.transaction_date.data
        db.session.commit(); flash('Transaction updated.', 'success'); return redirect(url_for('dashboard'))
    return render_template('edit_transaction.html', form=form, transaction=item)

@app.route('/export/csv')
@login_required
def export_csv():
    rows = db.session.scalars(select(Transaction).where(Transaction.user_id == current_user.id).order_by(Transaction.transaction_date.desc())).all()
    output = io.StringIO(); writer = csv.writer(output)
    writer.writerow(['Date','Type','Category','Description','Amount'])
    for t in rows:
        # Prefix potentially executable spreadsheet values to reduce CSV formula injection risk.
        desc = t.description or ''
        if desc.startswith(('=','+','-','@','\t','\r')): desc = "'" + desc
        writer.writerow([t.transaction_date.isoformat(), t.kind, t.category, desc, str(t.amount)])
    return Response('\ufeff' + output.getvalue(), mimetype='text/csv', headers={'Content-Disposition':'attachment; filename=pocketpulse_transactions.csv'})

@app.route('/budget', methods=['GET','POST'])
@login_required
def budget_page():
    form = BudgetForm(); month = request.args.get('month', date.today().strftime('%Y-%m'))
    if request.method == 'GET': form.month.data = month
    if form.validate_on_submit():
        month_value = form.month.data.strip()
        try: datetime.strptime(month_value, '%Y-%m')
        except ValueError: flash('Enter month in YYYY-MM format, for example 2026-10.', 'error')
        else:
            obj = db.session.scalar(select(MonthlyBudget).where(MonthlyBudget.user_id == current_user.id, MonthlyBudget.month == month_value))
            if obj: obj.amount = form.amount.data
            else: db.session.add(MonthlyBudget(user_id=current_user.id, month=month_value, amount=form.amount.data))
            db.session.commit(); flash('Monthly budget saved.', 'success'); return redirect(url_for('budget_page', month=month_value))
    obj = db.session.scalar(select(MonthlyBudget).where(MonthlyBudget.user_id == current_user.id, MonthlyBudget.month == month))
    spent = sum((t.amount for t in db.session.scalars(select(Transaction).where(Transaction.user_id == current_user.id, Transaction.kind == 'expense')).all() if t.transaction_date.strftime('%Y-%m') == month), Decimal('0'))
    return render_template('budget.html', form=form, budget=obj, month=month, spent=spent)

@app.route('/goals', methods=['GET','POST'])
@login_required
def goals_page():
    form = GoalForm()
    if form.validate_on_submit():
        goal = SavingsGoal(user_id=current_user.id, title=form.title.data.strip(), target_amount=form.target_amount.data,
            saved_amount=form.saved_amount.data, target_date=form.target_date.data)
        db.session.add(goal); db.session.commit(); flash('Savings goal added.', 'success'); return redirect(url_for('goals_page'))
    goals = db.session.scalars(select(SavingsGoal).where(SavingsGoal.user_id == current_user.id).order_by(SavingsGoal.id.desc())).all()
    return render_template('goals.html', form=form, goals=goals)

@app.route('/goals/<int:goal_id>/update', methods=['POST'])
@login_required
def update_goal(goal_id):
    goal = db.session.scalar(select(SavingsGoal).where(SavingsGoal.id == goal_id, SavingsGoal.user_id == current_user.id))
    if not goal: flash('Goal not found.', 'error'); return redirect(url_for('goals_page'))
    try: amount = Decimal(request.form.get('saved_amount',''))
    except Exception: amount = Decimal('-1')
    if amount < 0: flash('Enter a valid saved amount.', 'error')
    else: goal.saved_amount = min(amount, goal.target_amount); db.session.commit(); flash('Savings progress updated.', 'success')
    return redirect(url_for('goals_page'))

@app.route('/goals/<int:goal_id>/delete', methods=['POST'])
@login_required
def delete_goal(goal_id):
    goal = db.session.scalar(select(SavingsGoal).where(SavingsGoal.id == goal_id, SavingsGoal.user_id == current_user.id))
    if goal: db.session.delete(goal); db.session.commit(); flash('Goal deleted.', 'success')
    else: flash('Goal not found.', 'error')
    return redirect(url_for('goals_page'))

@app.route('/recurring', methods=['GET','POST'])
@login_required
def recurring_page():
    form = RecurringForm()
    if form.validate_on_submit():
        rule = RecurringTransaction(user_id=current_user.id, amount=form.amount.data, kind=form.kind.data, category=form.category.data,
            description=(form.description.data or '').strip(), frequency=form.frequency.data, next_date=form.next_date.data, active=True)
        db.session.add(rule); db.session.commit(); flash('Recurring rule saved. It will not charge a bank account automatically.', 'success'); return redirect(url_for('recurring_page'))
    rules = db.session.scalars(select(RecurringTransaction).where(RecurringTransaction.user_id == current_user.id).order_by(RecurringTransaction.next_date)).all()
    return render_template('recurring.html', form=form, rules=rules)

@app.route('/recurring/<int:rule_id>/create', methods=['POST'])
@login_required
def create_recurring_transaction(rule_id):
    rule = db.session.scalar(select(RecurringTransaction).where(RecurringTransaction.id == rule_id, RecurringTransaction.user_id == current_user.id))
    if not rule: flash('Recurring rule not found.', 'error'); return redirect(url_for('recurring_page'))
    if not rule.active: flash('This recurring rule is paused. Activate it first.', 'error'); return redirect(url_for('recurring_page'))
    item = Transaction(user_id=current_user.id, amount=rule.amount, kind=rule.kind, category=rule.category,
        description=rule.description or 'Recurring transaction', transaction_date=rule.next_date)
    db.session.add(item)
    rule.next_date = rule.next_date + (timedelta(days=7) if rule.frequency == 'weekly' else timedelta(days=30))
    db.session.commit(); flash('Transaction created from recurring rule.', 'success'); return redirect(url_for('recurring_page'))

@app.route('/recurring/<int:rule_id>/toggle', methods=['POST'])
@login_required
def toggle_recurring(rule_id):
    rule = db.session.scalar(select(RecurringTransaction).where(RecurringTransaction.id == rule_id, RecurringTransaction.user_id == current_user.id))
    if rule: rule.active = not rule.active; db.session.commit(); flash('Recurring rule status updated.', 'success')
    else: flash('Recurring rule not found.', 'error')
    return redirect(url_for('recurring_page'))

@app.route('/profile', methods=['GET','POST'])
@login_required
def profile_page():
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        email = request.form.get('email','').strip().lower()
        password = request.form.get('new_password','')
        confirm = request.form.get('confirm_password','')
        if len(username) < 3 or len(username) > 40 or '@' not in email:
            flash('Enter a valid username and email.', 'error')
        elif db.session.scalar(select(User).where(User.email == email, User.id != current_user.id)):
            flash('That email is already in use.', 'error')
        elif password and (len(password) < 8 or password != confirm):
            flash('New password must be at least 8 characters and match confirmation.', 'error')
        else:
            current_user.username = username; current_user.email = email
            if password: current_user.set_password(password)
            db.session.commit(); flash('Profile updated successfully.', 'success'); return redirect(url_for('profile_page'))
    return render_template('profile.html')

@app.route('/logout', methods=['POST'])
@login_required
def logout(): logout_user(); flash('You have been logged out.', 'success'); return redirect(url_for('login'))

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)
