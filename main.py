import os
import json
import configparser
from flask import Flask, render_template, request, redirect, url_for, flash, session, make_response
import gspread
from datetime import datetime
import qrcode
import io
import base64
import pandas as pd
from fpdf import FPDF
from cachetools import cached, TTLCache
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from dateutil.parser import parse

# --- إعداد التطبيق ---
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'a_very_secret_key_that_you_should_change')

# --- إعداد قاعدة البيانات ---
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- تعريف نموذج المستخدم (User Model) ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    def __repr__(self):
        return f'<User {self.username}>'

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# --- قواميس المساعدة ---
PAYMENT_METHOD_MAP = {
    "udf4": "VODAFONE", "udf19": "B-M", "udf2": "CIB-H", "udf30": "INSTAPAY",
    "udf10": "VALU", "udf27": "FORSA", "udf29": "CONTACT", "udf20": "CIB POINTS",
    "udf26": "SOUHOOLA", "udf5": "CARCIB", "cash": "نقداً",
}
ARABIC_MONTH_NAMES = {
    'Jan': 'يناير', 'Feb': 'فبراير', 'Mar': 'مارس', 'Apr': 'أبريل',
    'May': 'مايو', 'Jun': 'يونيو', 'Jul': 'يوليو', 'Aug': 'أغسطس',
    'Sep': 'سبتمبر', 'Oct': 'أكتوبر', 'Nov': 'نوفمبر', 'Dec': 'ديسمبر'
}

# --- دالة مساعدة لحماية المسارات ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            flash('الرجاء تسجيل الدخول للوصول إلى هذه الصفحة.', 'error')
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

# --- إعداد Google Sheet والبيانات المؤقتة ---
try:
    config = configparser.ConfigParser()
    config.read('config.ini')
    sheet_url = config.get('GSPREAD', 'sheet_url')
    creds_json_string = os.environ['GSPREAD_CREDENTIALS_JSON']
    creds_dict = json.loads(creds_json_string)
    gc = gspread.service_account_from_dict(creds_dict)
    sheet_cache = TTLCache(maxsize=1, ttl=300)

    @cached(sheet_cache)
    def get_sheet_data():
        """Fetches data from Google Sheet as raw, unformatted values."""
        try:
            worksheet = gc.open_by_url(sheet_url).sheet1
            # -- التعديل الجذري هنا: جلب القيم الخام للأرقام --
            data = worksheet.get_all_values(value_render_option='UNFORMATTED_VALUE')
            return data[1:] if data else []
        except gspread.exceptions.SpreadsheetNotFound:
            flash("خطأ: لم يتم العثور على جدول البيانات. يرجى التحقق من الرابط.", "error")
            return []
        except Exception as e:
            flash(f"خطأ في جلب البيانات من Google Sheet: {e}", "error")
            return []
except Exception as e:
    app.logger.error(f"Error during initial setup: {e}")

# --- الدوال الوظيفية ---
def search_data_for_web(query, search_type, data):
    current_data = get_sheet_data()
    if not current_data:
        return []

    INDEX_DATE, INDEX_INVOICE_NUMBER, INDEX_TOTAL_AMOUNT, INDEX_PAYMENT_METHOD, \
    INDEX_CASHIER_NAME, INDEX_CUSTOMER_NAME, INDEX_PHONE_NUMBER = 0, 1, 2, 3, 4, 5, 6
    INDEX_ITEMS_STR, INDEX_DISCOUNT, INDEX_VAT, INDEX_TAX_ID = 7, 8, 9, 10
    
    invoices_to_aggregate = {}
    query_stripped = str(query).strip()
    search_col_index = INDEX_INVOICE_NUMBER if search_type == 'invoice' else INDEX_PHONE_NUMBER

    for row in current_data:
        if len(row) <= search_col_index:
            continue
        
        cell_value = str(row[search_col_index]).strip()
        
        if cell_value == query_stripped:
            invoice_number = row[INDEX_INVOICE_NUMBER]
            
            if invoice_number not in invoices_to_aggregate:
                raw_date_str = str(row[INDEX_DATE]).strip() if len(row) > INDEX_DATE else 'غير متوفر'
                formatted_date = raw_date_str
                try:
                    dt_object = parse(raw_date_str)
                    month_abbrev = dt_object.strftime('%b')
                    arabic_month = ARABIC_MONTH_NAMES.get(month_abbrev, month_abbrev)
                    am_pm = "صباحًا" if dt_object.hour < 12 else "مساءً"
                    display_hour_12 = dt_object.hour % 12 or 12
                    formatted_date = f"{dt_object.day:02d} {arabic_month} {dt_object.year} | {display_hour_12:02d}:{dt_object.minute:02d}:{dt_object.second:02d} {am_pm}"
                except Exception:
                    pass
                
                raw_payment_method = str(row[INDEX_PAYMENT_METHOD]).strip().lower() if len(row) > INDEX_PAYMENT_METHOD else 'غير متوفر'
                display_payment_method = PAYMENT_METHOD_MAP.get(raw_payment_method, raw_payment_method.capitalize())
                
                invoices_to_aggregate[invoice_number] = {
                    'number': invoice_number,
                    'date': formatted_date,
                    'payment_method': display_payment_method,
                    'cashier': row[INDEX_CASHIER_NAME] if len(row) > INDEX_CASHIER_NAME else 'غير متوفر',
                    'customer_name': row[INDEX_CUSTOMER_NAME] or 'غير مسجل',
                    'customer_phone': row[INDEX_PHONE_NUMBER] or 'غير مسجل',
                    'items_str': str(row[INDEX_ITEMS_STR]) if len(row) > INDEX_ITEMS_STR else '',
                    'discount': str(row[INDEX_DISCOUNT]) if len(row) > INDEX_DISCOUNT else '0',
                    'vat': str(row[INDEX_VAT]) if len(row) > INDEX_VAT else '0',
                    'tax_id': str(row[INDEX_TAX_ID]) if len(row) > INDEX_TAX_ID else 'غير متوفر',
                    'total_amount': 0.0
                }
            
            try:
                # بما أننا الآن نحصل على أرقام خام، يمكننا تحويلها مباشرة
                current_row_amount = float(row[INDEX_TOTAL_AMOUNT])
                invoices_to_aggregate[invoice_number]['total_amount'] += current_row_amount
            except (ValueError, IndexError):
                continue # تجاهل المبلغ إذا كان غير صالح

    results = list(invoices_to_aggregate.values())
    for res in results:
        res['total_amount'] = f"{res['total_amount']:.2f}"

    return results

def generate_qr_code(text):
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode('utf-8')

# --- مسارات تطبيق الويب ---
@app.route('/')
@login_required
def home():
    # Check for theme from URL parameter or cookie as fallback
    initial_theme = request.args.get('theme') or request.cookies.get('theme')
    return render_template('index.html', initial_theme=initial_theme)

@app.route('/search', methods=['POST'])
@login_required
def search():
    query = request.form.get('query')
    search_type = request.form.get('search_type')
    search_results = search_data_for_web(query, search_type, None)
    initial_theme = request.args.get('theme') or request.cookies.get('theme')
    return render_template('index.html', results=search_results, query=query, search_type=search_type, initial_theme=initial_theme)

@app.route('/export_csv')
@login_required
def export_csv_results():
    query = request.args.get('query')
    search_type = request.args.get('search_type')
    if not query or not search_type:
        flash("الرجاء تحديد معلمات البحث للتصدير.", "error")
        return redirect(url_for('home'))
    
    search_results = search_data_for_web(query, search_type, None)
    if not search_results:
        flash("لا توجد نتائج لتصديرها.", "info")
        return redirect(url_for('home'))
    
    output = io.StringIO()
    df = pd.DataFrame(search_results)
    df.to_csv(output, index=False, encoding='utf-8')
    output.seek(0)
    
    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename=results_{query}.csv"
    response.headers["Content-type"] = "text/csv; charset=utf-8"
    return response

@app.route('/export_pdf/<invoice_number>')
@login_required
def export_pdf(invoice_number):
    results = search_data_for_web(invoice_number, 'invoice', None)
    if not results:
        flash("لم يتم العثور على الفاتورة المطلوبة.", "error")
        return redirect(url_for('home'))
    
    invoice = results[0]
    
    class PDF(FPDF):
        def header(self):
            # تأكد من وجود الخط Amiri-Regular.ttf في نفس المجلد
            try: self.add_font('Amiri', '', 'Amiri-Regular.ttf', uni=True)
            except RuntimeError: self.add_font('Arial', '', 'arial.ttf', uni=True)
            self.set_font('Amiri', '', 15)
            self.cell(0, 10, 'تفاصيل الفاتورة', 0, 1, 'C')
            self.ln(10)
        def footer(self):
            self.set_y(-15)
            self.set_font('Amiri' if 'Amiri' in self.fonts else 'Arial', '', 8)
            self.cell(0, 10, f'صفحة {self.page_no()}', 0, 0, 'C')

    pdf = PDF()
    pdf.add_page()
    pdf.set_font('Amiri' if 'Amiri' in pdf.fonts else 'Arial', '', 12)
    
    pdf.cell(0, 10, f"رقم الفاتورة: {invoice.get('number', 'N/A')}", 0, 1, 'R')
    pdf.cell(0, 10, f"التاريخ: {invoice.get('date', 'N/A')}", 0, 1, 'R')
    pdf.cell(0, 10, f"المبلغ الإجمالي: {invoice.get('total_amount', 'N/A')}", 0, 1, 'R')
    
    pdf_output = pdf.output(dest='S').encode('latin-1')
    response = make_response(pdf_output)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'inline; filename=invoice_{invoice_number}.pdf'
    return response

# --- مسارات تسجيل الدخول / التسجيل / الخروج ---
@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if 'logged_in' in session:
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            session['logged_in'] = True
            session['username'] = user.username
            flash('تم تسجيل الدخول بنجاح!', 'info')
            return redirect(url_for('home'))
        else:
            flash('اسم المستخدم أو كلمة المرور غير صحيحة.', 'error')
    
    initial_theme = request.args.get('theme')
    return render_template('login.html', initial_theme=initial_theme)

@app.route('/register', methods=['GET', 'POST'])
def register_page():
    if 'logged_in' in session:
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if not all([username, password, confirm_password]):
            flash('الرجاء تعبئة جميع الحقول.', 'error')
        elif User.query.filter_by(username=username).first():
            flash('اسم المستخدم هذا موجود بالفعل.', 'error')
        elif password != confirm_password:
            flash('كلمتا المرور غير متطابقتين.', 'error')
        elif len(password) < 6:
            flash('كلمة المرور يجب أن تكون 6 أحرف على الأقل.', 'error')
        else:
            new_user = User(username=username)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            flash('تم تسجيل حسابك بنجاح! الرجاء تسجيل الدخول.', 'info')
            return redirect(url_for('login_page'))
    
    initial_theme = request.args.get('theme')
    return render_template('register.html', initial_theme=initial_theme)

@app.route('/logout')
def logout():
    session.clear()
    flash('تم تسجيل الخروج بنجاح.', 'info')
    return redirect(url_for('login_page'))

# --- تشغيل التطبيق وإعداد قاعدة البيانات ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            admin_user = User(username='admin')
            admin_user.set_password('adminpass')
            db.session.add(admin_user)
            print("Default admin user 'admin' created.")
        
        if not User.query.filter_by(username='viewer').first():
            viewer_user = User(username='viewer')
            viewer_user.set_password('viewerpass')
            db.session.add(viewer_user)
            print("Default viewer user 'viewer' created.")
        
        db.session.commit()

    app.run(host='0.0.0.0', port=5000, debug=True)