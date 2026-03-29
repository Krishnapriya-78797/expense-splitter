from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
import os

app = Flask(__name__)
app.secret_key = 'expense-splitter-secret'

DATABASE = '/app/instance/expenses.db'

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs('/app/instance', exist_ok=True)
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL
        );
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY,
            description TEXT,
            amount REAL NOT NULL,
            paid_by INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS expense_shares (
            id INTEGER PRIMARY KEY,
            expense_id INTEGER,
            user_id INTEGER,
            share_amount REAL NOT NULL
        );
        INSERT OR IGNORE INTO users (name) VALUES ('Alice'), ('Bob'), ('Charlie');
    ''')
    conn.commit()
    conn.close()

@app.before_first_request
def initialize():
    init_db()

@app.route('/')
def index():
    conn = get_db()
    expenses = conn.execute('''
        SELECT e.id, e.description, e.amount, u.name as paid_by_name, e.created_at
        FROM expenses e JOIN users u ON e.paid_by = u.id
        ORDER BY e.created_at DESC
    ''').fetchall()
    conn.close()
    return render_template('index.html', expenses=expenses)

@app.route('/add_expense', methods=['GET', 'POST'])
def add_expense():
    conn = get_db()
    users = conn.execute('SELECT * FROM users').fetchall()
    if request.method == 'POST':
        description = request.form['description']
        amount = float(request.form['amount'])
        paid_by_name = request.form['paid_by']
        participants = request.form.getlist('participants')

        paid_by = conn.execute('SELECT id FROM users WHERE name = ?', (paid_by_name,)).fetchone()['id']

        cursor = conn.execute('INSERT INTO expenses (description, amount, paid_by) VALUES (?, ?, ?)', 
                            (description, amount, paid_by))
        expense_id = cursor.lastrowid

        share = amount / len(participants)
        for p_name in participants:
            user_id = conn.execute('SELECT id FROM users WHERE name = ?', (p_name,)).fetchone()['id']
            conn.execute('INSERT INTO expense_shares (expense_id, user_id, share_amount) VALUES (?, ?, ?)', 
                        (expense_id, user_id, share))

        conn.commit()
        conn.close()
        flash('Expense added successfully!')
        return redirect(url_for('index'))
    
    conn.close()
    return render_template('add_expense.html', users=users)

@app.route('/balances')
def balances():
    conn = get_db()
    users = conn.execute('SELECT * FROM users').fetchall()
    balance_dict = {u['id']: {'name': u['name'], 'balance': 0.0} for u in users}

    paid = conn.execute('SELECT paid_by, SUM(amount) as total FROM expenses GROUP BY paid_by').fetchall()
    for row in paid:
        if row['paid_by'] in balance_dict:
            balance_dict[row['paid_by']]['balance'] += row['total']

    owed = conn.execute('SELECT user_id, SUM(share_amount) as total FROM expense_shares GROUP BY user_id').fetchall()
    for row in owed:
        if row['user_id'] in balance_dict:
            balance_dict[row['user_id']]['balance'] -= row['total']

    conn.close()

    debtors = [v for v in balance_dict.values() if v['balance'] < 0]
    creditors = [v for v in balance_dict.values() if v['balance'] > 0]
    debts = []
    for debtor in debtors:
        for creditor in creditors:
            if debtor['balance'] >= 0 or creditor['balance'] <= 0:
                break
            settle = min(-debtor['balance'], creditor['balance'])
            if settle > 0:
                debts.append(f"{debtor['name']} owes {creditor['name']} ₹{settle:.2f}")
                debtor['balance'] += settle
                creditor['balance'] -= settle

    return render_template('balances.html', balances=balance_dict.values(), debts=debts)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
