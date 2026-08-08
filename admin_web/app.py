from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os

app = Flask(__name__)
app.secret_key = os.getenv("WEB_ADMIN_SECRET", "funstat-secret-2024")
DB_PATH = os.getenv("DATABASE_PATH", "../database/funstat.db")
OWNER_ID = os.getenv("OWNER_ID", "")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    conn = get_db()
    cur = conn.cursor()
    try:
        users = cur.execute("SELECT COUNT(*) as c FROM users").fetchone()['c']
        credits = cur.execute("SELECT SUM(credits) as s FROM users").fetchone()['s'] or 0
        pending = cur.execute("SELECT COUNT(*) as c FROM transactions WHERE status='pending'").fetchone()['c']
        settings = {r['key']: r['value'] for r in cur.execute("SELECT * FROM settings").fetchall()}
    except:
        users, credits, pending, settings = 0,0,0,{}
    conn.close()
    return render_template('dashboard.html', users=users, credits=credits, pending=pending, settings=settings)

@app.route('/settings', methods=['POST'])
def update_settings():
    price = request.form.get('price_per_credit')
    upi = request.form.get('upi_id')
    trc = request.form.get('usdt_trc20')
    bep = request.form.get('usdt_bep20')
    conn = get_db()
    for k,v in [('price_per_credit',price), ('upi_id',upi), ('usdt_trc20',trc), ('usdt_bep20',bep)]:
        if v is not None:
            conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (k,v))
    # Handle UPI QR upload via web
    if 'upi_qr' in request.files:
        f = request.files['upi_qr']
        if f and f.filename:
            import pathlib
            save_path = pathlib.Path(__file__).parent.parent / "upi_qr_custom.jpg"
            f.save(str(save_path))
            # Also set flag so bot knows custom QR exists (store as local path marker)
            conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", ("upi_qr_file_id", "local:upi_qr_custom.jpg"))
            flash("✅ Custom UPI QR uploaded via Web! Bot will now show this QR.")
        else:
            flash("✅ Settings Updated! Bot me instantly reflect hoga (QR not changed)")
    else:
        flash("✅ Settings Updated! Bot me instantly reflect hoga")
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/users')
def users():
    conn = get_db()
    rows = conn.execute("SELECT * FROM users ORDER BY joined_at DESC LIMIT 100").fetchall()
    conn.close()
    return render_template('users.html', users=rows)

@app.route('/transactions')
def transactions():
    conn = get_db()
    rows = conn.execute("SELECT * FROM transactions ORDER BY id DESC LIMIT 100").fetchall()
    conn.close()
    return render_template('transactions.html', txs=rows)

@app.route('/approve/<int:tx_id>')
def approve(tx_id):
    conn = get_db()
    tx = conn.execute("SELECT * FROM transactions WHERE id=?", (tx_id,)).fetchone()
    if tx and tx['status']=='pending':
        conn.execute("UPDATE transactions SET status='approved' WHERE id=?", (tx_id,))
        conn.execute("UPDATE users SET credits=credits+? WHERE user_id=?", (tx['amount'], tx['user_id']))
        conn.commit()
        flash(f"✅ {tx['amount']} credits approved for {tx['user_id']}")
    conn.close()
    return redirect(url_for('transactions'))

if __name__ == '__main__':
    port = int(os.getenv("WEB_ADMIN_PORT", 5000))
    print(f"🌐 Owner Web Panel: http://0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=True)
