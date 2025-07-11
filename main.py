import os
import json
import configparser
import pickle
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
import gspread
from datetime import datetime, timedelta
from dateutil.parser import parse, ParserError
from cachetools import cached, TTLCache
from functools import wraps

# --- إعداد التطبيق وقاعدة البيانات ---
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'a_default_secret_key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- نماذج قاعدة البيانات ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

# --- قواميس المساعدة ---
PAYMENT_METHOD_MAP = { "udf4": "VODAFONE", "udf19": "B-M", "udf2": "CIB-H", "udf30": "INSTAPAY", "udf10": "VALU", "udf27": "FORSA", "udf29": "CONTACT", "udf20": "CIB POINTS", "udf26": "SOUHOOLA", "udf5": "CARCIB", "cash": "نقداً" }
ARABIC_MONTH_NAMES = { 'Jan': 'يناير', 'Feb': 'فبراير', 'Mar': 'مارس', 'Apr': 'أبريل', 'May': 'مايو', 'Jun': 'يونيو', 'Jul': 'يوليو', 'Aug': 'أغسطس', 'Sep': 'سبتمبر', 'Oct': 'أكتوبر', 'Nov': 'نوفمبر', 'Dec': 'ديسمبر' }

# --- decorator لحماية المسارات ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            flash('الرجاء تسجيل الدخول للوصول إلى هذه الصفحة.', 'error')
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

# --- دوال التعامل مع Google Sheets ---
sheet_cache = TTLCache(maxsize=2, ttl=300)

def get_gspread_client():
    creds_json_string = os.environ.get('GSPREAD_CREDENTIALS_JSON')
    if not creds_json_string: raise ValueError("Secret GSPREAD_CREDENTIALS_JSON is not set.")
    return gspread.service_account_from_dict(json.loads(creds_json_string))

def save_data_locally(data, sheet_type='main'):
    """حفظ البيانات محلياً"""
    filename = f'local_data_{sheet_type}.pkl'
    try:
        with open(filename, 'wb') as f:
            pickle.dump({
                'data': data,
                'timestamp': datetime.now(),
                'sheet_type': sheet_type
            }, f)
        app.logger.info(f"تم حفظ بيانات {sheet_type} محلياً في {filename}")
    except Exception as e:
        app.logger.error(f"فشل في حفظ البيانات محلياً: {str(e)}")

def load_data_locally(sheet_type='main'):
    """تحميل البيانات المحفوظة محلياً"""
    filename = f'local_data_{sheet_type}.pkl'
    try:
        if os.path.exists(filename):
            with open(filename, 'rb') as f:
                saved_data = pickle.load(f)
                app.logger.info(f"تم تحميل بيانات {sheet_type} من الملف المحلي (آخر تحديث: {saved_data['timestamp']})")
                return saved_data['data']
    except Exception as e:
        app.logger.error(f"فشل في تحميل البيانات المحلية: {str(e)}")
    return None

@cached(sheet_cache)
def get_sheet_data(sheet_type='main', offline_mode=False):
    # إذا كان الوضع المطلوب هو العمل بدون إنترنت، حمّل البيانات المحلية مباشرة
    if offline_mode:
        app.logger.info(f"الوضع بدون إنترنت مفعل - تحميل البيانات المحلية لـ {sheet_type}")
        local_data = load_data_locally(sheet_type)
        if local_data:
            return local_data
        else:
            app.logger.warning(f"لا توجد بيانات محلية متاحة لـ {sheet_type}")
            return [] if sheet_type == 'main' else None
    
    # محاولة تحميل البيانات من Google Sheets أولاً
    try:
        # التحقق من وجود ملف الإعدادات
        if not os.path.exists('config.ini'):
            app.logger.error("config.ini file not found")
            # محاولة تحميل البيانات المحلية كبديل
            local_data = load_data_locally(sheet_type)
            if local_data:
                app.logger.info("استخدام البيانات المحلية بدلاً من Google Sheets")
                return local_data
            return [] if sheet_type == 'main' else None
            
        config = configparser.ConfigParser()
        config.read('config.ini')
        url_key = 'sheet_url' if sheet_type == 'main' else 'sales_sheet_url'
        
        # التحقق من وجود URL في الإعدادات
        if not config.has_section('GSPREAD') or not config.has_option('GSPREAD', url_key):
            app.logger.error(f"Missing {url_key} in config.ini")
            # محاولة تحميل البيانات المحلية كبديل
            local_data = load_data_locally(sheet_type)
            if local_data:
                app.logger.info("استخدام البيانات المحلية بدلاً من Google Sheets")
                return local_data
            return [] if sheet_type == 'main' else None
            
        sheet_url = config.get('GSPREAD', url_key)
        app.logger.info(f"Attempting to access {sheet_type} sheet: {sheet_url}")
        
        gc = get_gspread_client()
        spreadsheet = gc.open_by_url(sheet_url)
        worksheet_name = "الورقة1" if sheet_type == 'main' else "Data Sheet 1"
        
        try:
            worksheet = spreadsheet.worksheet(worksheet_name)
        except gspread.WorksheetNotFound:
            # محاولة استخدام أول ورقة عمل إذا لم يتم العثور على الاسم المحدد
            app.logger.warning(f"Worksheet '{worksheet_name}' not found, using first worksheet")
            worksheet = spreadsheet.get_worksheet(0)
            
        data = worksheet.get_all_values(value_render_option='UNFORMATTED_VALUE')
        app.logger.info(f"Successfully retrieved {len(data)} rows from {sheet_type} sheet")
        
        # البيانات بدون العنوان (الصف الأول)
        processed_data = data[1:] if len(data) > 1 else []
        
        # حفظ البيانات محلياً للاستخدام المستقبلي
        save_data_locally(processed_data, sheet_type)
        
        return processed_data
        
    except gspread.SpreadsheetNotFound:
        app.logger.error(f"Spreadsheet not found for {sheet_type}")
        # محاولة تحميل البيانات المحلية كبديل
        local_data = load_data_locally(sheet_type)
        if local_data:
            app.logger.info("استخدام البيانات المحلية بدلاً من Google Sheets")
            return local_data
        return [] if sheet_type == 'main' else None
    except json.JSONDecodeError:
        app.logger.error("Invalid JSON in GSPREAD_CREDENTIALS_JSON")
        # محاولة تحميل البيانات المحلية كبديل
        local_data = load_data_locally(sheet_type)
        if local_data:
            app.logger.info("استخدام البيانات المحلية بدلاً من Google Sheets")
            return local_data
        return [] if sheet_type == 'main' else None
    except Exception as e:
        app.logger.error(f"Failed to get {sheet_type} sheet data: {str(e)}")
        # محاولة تحميل البيانات المحلية كبديل
        local_data = load_data_locally(sheet_type)
        if local_data:
            app.logger.info("استخدام البيانات المحلية بدلاً من Google Sheets")
            return local_data
        return [] if sheet_type == 'main' else None

# --- دالة مخصصة وآمنة لمعالجة التاريخ ---
def parse_date_safely(date_str):
    if not date_str: return None
    
    # تحويل إلى نص أولاً
    date_str = str(date_str).strip()
    if not date_str: return None
    
    try:
        # إزالة المنطقة الزمنية إذا وجدت
        if '+' in date_str:
            date_str = date_str.split('+')[0].strip()
        
        # محاولة معالجة تنسيق Google Sheets المحدد: "15-JUN-25 05.10.52 PM"
        import re
        google_sheets_pattern = r'(\d{1,2}-[A-Z]{3}-\d{2})\s+(\d{1,2})\.(\d{2})\.(\d{2})\s+(AM|PM)'
        match = re.match(google_sheets_pattern, date_str)
        
        if match:
            date_part = match.group(1)  # "15-JUN-25"
            hour = int(match.group(2))  # "05"
            minute = int(match.group(3))  # "10"
            second = int(match.group(4))  # "52"
            ampm = match.group(5)  # "PM"
            
            # تحويل إلى تنسيق 24 ساعة
            if ampm == 'PM' and hour != 12:
                hour += 12
            elif ampm == 'AM' and hour == 12:
                hour = 0
                
            # إنشاء تنسيق ISO للتاريخ والوقت
            iso_format = f"{date_part} {hour:02d}:{minute:02d}:{second:02d}"
            
            # استخدام dateutil لمعالجة التاريخ
            from dateutil.parser import parse
            return parse(iso_format, fuzzy=True)
        
        # إذا لم يطابق النمط، محاولة المعالجة العادية
        from dateutil.parser import parse
        return parse(date_str, fuzzy=True)
        
    except (ParserError, ValueError, TypeError, ImportError) as e:
        # إذا فشلت كل المحاولات، لا نسجل تحذير لكل سجل لتجنب الإزعاج
        return None

# --- دوال تحليل ومعالجة البيانات ---

def search_data_for_web(query, search_type, data):
    if not data: return []
    INDEX_DATE, INDEX_INVOICE, INDEX_AMOUNT, INDEX_PAYMENT, INDEX_CASHIER, INDEX_CUST_NAME, INDEX_CUST_PHONE = 0, 1, 2, 3, 4, 5, 6
    invoices, query_stripped = {}, str(query).strip()
    search_col = INDEX_INVOICE if search_type == 'invoice' else INDEX_CUST_PHONE

    app.logger.info(f"البحث عن: '{query_stripped}' في العمود {search_col}")
    app.logger.info(f"عدد الصفوف المتاحة: {len(data)}")
    
    matches_found = 0
    for i, row in enumerate(data):
        if len(row) <= max(INDEX_CUST_PHONE, search_col): 
            continue
            
        if i < 3:  # عرض أول 3 صفوف للتشخيص
            app.logger.info(f"الصف {i}: {row}")
        
        cell_value = row[search_col]
        if not cell_value: continue
        
        # تنظيف وتحويل القيمة
        cell_str = str(cell_value).strip()
        
        # مقارنة مباشرة
        match_found = False
        if cell_str == query_stripped:
            match_found = True
        elif cell_str.replace('.0', '') == query_stripped:  # إزالة .0 من الأرقام
            match_found = True
        else:
            # محاولة تحويل إلى رقم للمقارنة
            try:
                if float(cell_str) == float(query_stripped):
                    match_found = True
            except (ValueError, TypeError):
                # البحث الجزئي للنصوص (للأسماء والهواتف)
                if search_type == 'phone' and query_stripped in cell_str:
                    match_found = True
                
        if match_found:
            matches_found += 1
            app.logger.info(f"تطابق موجود في الصف {i}: {row}")
            try:
                # تأكد من وجود جميع البيانات المطلوبة
                if len(row) <= INDEX_CUST_PHONE:
                    app.logger.warning(f"الصف {i} لا يحتوي على بيانات كافية")
                    continue
                    
                invoice_num_raw = row[INDEX_INVOICE]
                if not invoice_num_raw:
                    app.logger.warning(f"رقم الفاتورة فارغ في الصف {i}")
                    continue
                    
                invoice_num = str(int(float(invoice_num_raw)))
                app.logger.info(f"معالجة الفاتورة رقم: {invoice_num}")
                
                if invoice_num not in invoices:
                    dt_object = parse_date_safely(row[INDEX_DATE])
                    if not dt_object: 
                        # استخدام تاريخ افتراضي إذا فشلت المعالجة
                        app.logger.warning(f"استخدام تاريخ افتراضي للصف {i}: {row[INDEX_DATE]}")
                        date_display = "تاريخ غير محدد"
                    else:
                        date_display = f"{dt_object.day:02d} {ARABIC_MONTH_NAMES.get(dt_object.strftime('%b'), dt_object.strftime('%b'))} {dt_object.year}"

                    invoices[invoice_num] = {
                        'number': invoice_num,
                        'date': date_display,
                        'payment_method': PAYMENT_METHOD_MAP.get(str(row[INDEX_PAYMENT]).strip().lower(), str(row[INDEX_PAYMENT]).strip()),
                        'cashier': row[INDEX_CASHIER] or 'غير محدد', 
                        'customer_name': row[INDEX_CUST_NAME] or 'غير مسجل',
                        'customer_phone': row[INDEX_CUST_PHONE] or 'غير مسجل', 
                        'total_amount': 0.0
                    }
                
                # إضافة المبلغ
                amount_value = row[INDEX_AMOUNT]
                if amount_value:
                    try:
                        invoices[invoice_num]['total_amount'] += float(amount_value)
                    except (ValueError, TypeError):
                        app.logger.warning(f"مبلغ غير صالح في الصف {i}: {amount_value}")
                        
            except (ValueError, IndexError) as e:
                app.logger.error(f"خطأ في معالجة الصف {i}: {e}")
                continue
    
    app.logger.info(f"تم العثور على {matches_found} تطابق, {len(invoices)} فاتورة فريدة")
    results = list(invoices.values())
    for res in results: 
        res['total_amount'] = f"{res['total_amount']:.2f}"
    return results

def advanced_search_data(search_params, data):
    if not data: 
        app.logger.warning("لا توجد بيانات للبحث المتقدم")
        return []
    
    results = []
    processed_count = 0
    matched_count = 0
    INDEX_DATE, INDEX_INVOICE, INDEX_AMOUNT, INDEX_PAYMENT, INDEX_CASHIER, INDEX_CUST_NAME, INDEX_CUST_PHONE = 0, 1, 2, 3, 4, 5, 6

    app.logger.info(f"بدء البحث المتقدم مع المعايير: {search_params}")
    app.logger.info(f"عدد الصفوف المتاحة: {len(data)}")

    for i, row in enumerate(data):
        if len(row) <= max(INDEX_CUST_PHONE, INDEX_CASHIER): 
            continue
            
        processed_count += 1
        
        try:
            # محاولة معالجة التاريخ
            dt_object = parse_date_safely(row[INDEX_DATE])
            
            # إذا فشلت معالجة التاريخ، استخدم تاريخ افتراضي أو تخطي الفحص بناءً على وجود معايير تاريخ
            if not dt_object:
                if search_params.get('date_from') or search_params.get('date_to'):
                    continue  # تخطي هذا الصف إذا كان البحث يحتوي على معايير تاريخ
                # استخدام تاريخ افتراضي
                dt_object = datetime.now()
                date_display = "تاريخ غير محدد"
            else:
                date_display = f"{dt_object.day:02d} {ARABIC_MONTH_NAMES.get(dt_object.strftime('%b'), dt_object.strftime('%b'))} {dt_object.year}"

            # معالجة المبلغ
            try:
                amount = float(row[INDEX_AMOUNT])
            except (ValueError, TypeError):
                continue

            # معالجة البيانات النصية
            payment_method = str(row[INDEX_PAYMENT]).strip().lower()
            customer_name = str(row[INDEX_CUST_NAME] or '').strip().lower()
            cashier_name = str(row[INDEX_CASHIER] or '').strip().lower()

            # فحص المعايير
            # فحص التاريخ (فقط إذا كان التاريخ صحيح)
            if dt_object and dt_object != datetime.now():  # التأكد من أن التاريخ ليس افتراضي
                if search_params.get('date_from'):
                    try:
                        date_from = datetime.strptime(search_params['date_from'], '%Y-%m-%d').date()
                        if dt_object.date() < date_from:
                            continue
                    except ValueError:
                        app.logger.warning(f"تنسيق تاريخ 'من' غير صحيح: {search_params['date_from']}")
                        
                if search_params.get('date_to'):
                    try:
                        date_to = datetime.strptime(search_params['date_to'], '%Y-%m-%d').date()
                        if dt_object.date() > date_to:
                            continue
                    except ValueError:
                        app.logger.warning(f"تنسيق تاريخ 'إلى' غير صحيح: {search_params['date_to']}")

            # فحص طريقة الدفع
            if search_params.get('payment_method') and search_params['payment_method'] != 'all':
                if payment_method != search_params['payment_method']:
                    continue

            # فحص المبلغ الأدنى
            if search_params.get('amount_min'):
                try:
                    if amount < float(search_params['amount_min']):
                        continue
                except ValueError:
                    pass

            # فحص المبلغ الأعلى
            if search_params.get('amount_max'):
                try:
                    if amount > float(search_params['amount_max']):
                        continue
                except ValueError:
                    pass

            # فحص اسم العميل
            if search_params.get('customer_name'):
                if search_params['customer_name'].lower() not in customer_name:
                    continue

            # فحص اسم الكاشير
            if search_params.get('cashier_name'):
                if search_params['cashier_name'].lower() not in cashier_name:
                    continue

            # إذا وصلنا هنا، فالصف يطابق جميع المعايير
            matched_count += 1
            
            results.append({
                'number': str(int(float(row[INDEX_INVOICE]))),
                'date': date_display,
                'original_date': dt_object,
                'total_amount': f"{amount:.2f}",
                'payment_method': PAYMENT_METHOD_MAP.get(payment_method, payment_method.capitalize()),
                'cashier': row[INDEX_CASHIER] or 'غير محدد',
                'customer_name': row[INDEX_CUST_NAME] or 'غير مسجل',
                'customer_phone': row[INDEX_CUST_PHONE] or 'غير مسجل'
            })
            
        except (ValueError, IndexError) as e:
            app.logger.warning(f"خطأ في معالجة الصف {i} في البحث المتقدم: {e}")
            continue

    app.logger.info(f"البحث المتقدم: تم معالجة {processed_count} صف, وجد {matched_count} تطابق")
    
    # ترتيب النتائج حسب التاريخ (الأحدث أولاً)
    try:
        return sorted(results, key=lambda x: x['original_date'], reverse=True)
    except (TypeError, KeyError):
        app.logger.warning("فشل في ترتيب النتائج، إرجاع النتائج بدون ترتيب")
        return results

def analyze_sales_data(sales_data, time_period='all'):
    if not sales_data: return [], "لا يمكن الوصول إلى شيت المبيعات."
    INDEX_DATE, INDEX_ITEM_CODE, INDEX_DESCRIPTION, INDEX_QUANTITY = 0, 1, 2, 3
    item_summary, now = {}, datetime.now()
    for row in sales_data:
        if len(row) <= INDEX_QUANTITY: continue
        try:
            dt_object = parse_date_safely(str(row[INDEX_DATE]))
            if not dt_object: continue

            if time_period != 'all':
                deltas = {'day': 1, 'week': 7, '2weeks': 14, 'month': 30}
                if dt_object < (now - timedelta(days=deltas.get(time_period, 0))): continue

            item_code = str(row[INDEX_ITEM_CODE]).strip()
            if not item_code: continue

            quantity = float(str(row[INDEX_QUANTITY]).replace(',', '.'))
            description = str(row[INDEX_DESCRIPTION]).strip()

            if item_code not in item_summary:
                item_summary[item_code] = {'description': description, 'quantity': 0.0}
            item_summary[item_code]['quantity'] += quantity
        except (ValueError, IndexError):
            continue
    if not item_summary: return [], None
    result_list = [{'كود القطعه': c, 'الوصف': d['description'], 'الكمية': d['quantity']} for c, d in item_summary.items()]
    return sorted(result_list, key=lambda x: x['الكمية'], reverse=True), None

def get_dashboard_stats(main_data):
    if not main_data: return {'total_revenue': '0.00', 'total_invoices': 0, 'avg_invoice': '0.00', 'today_revenue': '0.00'}

    # حساب تاريخ البداية (26 من الشهر السابق)
    today = datetime.now().date()
    if today.day >= 26:
        # إذا كان اليوم الحالي 26 أو أكثر، البداية من 26 من نفس الشهر
        start_date = today.replace(day=26)
    else:
        # إذا كان اليوم الحالي أقل من 26، البداية من 26 من الشهر السابق
        if today.month == 1:
            # إذا كان الشهر يناير، نذهب للشهر 12 من السنة السابقة
            start_date = today.replace(year=today.year-1, month=12, day=26)
        else:
            start_date = today.replace(month=today.month-1, day=26)

    total_revenue, today_revenue, period_revenue, invoices, period_invoices = 0.0, 0.0, 0.0, set(), set()
    INDEX_DATE, INDEX_INVOICE, INDEX_AMOUNT = 0, 1, 2
    
    app.logger.info(f"حساب الإيرادات من {start_date} إلى {today}")
    
    for row in main_data:
        if len(row) <= INDEX_AMOUNT: continue
        try:
            amount = float(row[INDEX_AMOUNT])
            invoice_num = str(int(float(row[INDEX_INVOICE])))
            
            # إضافة لإجمالي الإيرادات (كل البيانات)
            total_revenue += amount
            invoices.add(invoice_num)
            
            dt_object = parse_date_safely(str(row[INDEX_DATE]))
            if dt_object:
                row_date = dt_object.date()
                
                # إيرادات اليوم الحالي
                if row_date == today:
                    today_revenue += amount
                
                # إيرادات الفترة المحددة (من 26 الشهر السابق لليوم)
                if start_date <= row_date <= today:
                    period_revenue += amount
                    period_invoices.add(invoice_num)
                    
        except (ValueError, IndexError):
            continue
    
    total_invoices = len(invoices)
    period_invoice_count = len(period_invoices)
    avg_invoice = period_revenue / period_invoice_count if period_invoice_count > 0 else 0
    
    app.logger.info(f"إجمالي إيرادات الفترة: {period_revenue:,.2f} من {period_invoice_count} فاتورة")
    
    return {
        'total_revenue': f"{period_revenue:,.2f}",  # تغيير لعرض إيرادات الفترة المحددة
        'total_invoices': period_invoice_count,     # عدد فواتير الفترة المحددة
        'avg_invoice': f"{avg_invoice:,.2f}", 
        'today_revenue': f"{today_revenue:,.2f}"
    }

# --- مسارات التطبيق (Routes) ---

@app.route('/')
@login_required
def home():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
@login_required
def search():
    query, search_type = request.form.get('query'), request.form.get('search_type')
    offline_mode = request.form.get('offline_mode') == 'true'
    
    main_data = get_sheet_data('main', offline_mode=offline_mode)
    
    # إضافة معلومات تشخيصية
    if not main_data:
        if offline_mode:
            flash('لا توجد بيانات محلية محفوظة. يرجى الاتصال بالإنترنت لتحديث البيانات أولاً.', 'error')
        else:
            flash('تعذر الوصول إلى بيانات Google Sheets. تحقق من الاتصال والصلاحيات.', 'error')
        return render_template('index.html', query=query, search_type=search_type, offline_mode=offline_mode)
    
    if len(main_data) == 0:
        if offline_mode:
            flash('البيانات المحلية فارغة.', 'warning')
        else:
            flash('Google Sheets فارغ أو لا يحتوي على بيانات.', 'warning')
        return render_template('index.html', query=query, search_type=search_type, offline_mode=offline_mode)
    
    search_results = search_data_for_web(query, search_type, main_data)
    
    if not search_results:
        flash(f'لم يتم العثور على نتائج للبحث: "{query}"', 'warning')
    
    return render_template('index.html', results=search_results, query=query, search_type=search_type, offline_mode=offline_mode)

@app.route('/advanced_search', methods=['GET', 'POST'])
@login_required
def advanced_search():
    if session.get('username', '').lower() != 'admin':
        return redirect(url_for('home'))

    results, search_params = [], {}
    if request.method == 'POST':
        search_params = {k: v for k, v in request.form.items() if v}
        main_data = get_sheet_data('main')
        
        # إضافة معلومات تشخيصية
        if not main_data:
            flash('تعذر الوصول إلى بيانات Google Sheets. تحقق من الاتصال والصلاحيات.', 'error')
        elif len(main_data) == 0:
            flash('Google Sheets فارغ أو لا يحتوي على بيانات.', 'warning')
        else:
            results = advanced_search_data(search_params, main_data)
            
            if not results:
                flash('لم يتم العثور على نتائج تطابق معايير البحث المحددة.', 'warning')

    return render_template('advanced_search.html', results=results, search_params=search_params, payment_methods=PAYMENT_METHOD_MAP)

@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    if session.get('username', '').lower() != 'admin':
        return redirect(url_for('home'))

    main_data = get_sheet_data('main')
    sales_data = get_sheet_data('sales')

    time_period = request.form.get('time_period', 'all')
    top_items, error = analyze_sales_data(sales_data, time_period)
    if error: flash(error, 'error')

    stats = get_dashboard_stats(main_data)

    return render_template('dashboard.html', 
                           top_items=top_items or [], 
                           selected_period=time_period,
                           stats=stats)

# --- مسارات المصادقة ---
@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if 'logged_in' in session: return redirect(url_for('home'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and user.check_password(request.form.get('password')):
            session['logged_in'] = True
            session['username'] = user.username
            return redirect(url_for('home'))
        else:
            flash('اسم المستخدم أو كلمة المرور غير صحيحة.', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
@login_required
def register_page():
    if session.get('username', '').lower() != 'admin': return redirect(url_for('home'))
    if request.method == 'POST':
        username, password = request.form.get('username'), request.form.get('password')
        if not all([username, password]):
            flash('الرجاء تعبئة جميع الحقول.', 'error')
        elif User.query.filter_by(username=username).first():
            flash('اسم المستخدم هذا موجود بالفعل.', 'error')
        else:
            new_user = User(username=username)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            flash(f'تم تسجيل المستخدم {username} بنجاح!', 'info')
            return redirect(url_for('home'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('تم تسجيل الخروج بنجاح.', 'info')
    return redirect(url_for('login_page'))

@app.route('/debug')
@login_required
def debug_info():
    if session.get('username', '').lower() != 'admin':
        return redirect(url_for('home'))
    
    debug_data = {
        'config_exists': os.path.exists('config.ini'),
        'credentials_set': bool(os.environ.get('GSPREAD_CREDENTIALS_JSON')),
        'main_data_count': 0,
        'sales_data_count': 0,
        'errors': []
    }
    
    # اختبار الوصول للبيانات
    try:
        main_data = get_sheet_data('main')
        debug_data['main_data_count'] = len(main_data) if main_data else 0
        if main_data and len(main_data) > 0:
            debug_data['sample_main_rows'] = main_data[:3]  # أول 3 صفوف كاملة
            debug_data['column_headers'] = ['DATE', 'INVOICE', 'AMOUNT', 'PAYMENT', 'CASHIER', 'CUST_NAME', 'CUST_PHONE']
    except Exception as e:
        debug_data['errors'].append(f"Main sheet error: {str(e)}")
    
    try:
        sales_data = get_sheet_data('sales')
        debug_data['sales_data_count'] = len(sales_data) if sales_data else 0
        if sales_data and len(sales_data) > 0:
            debug_data['sample_sales_rows'] = sales_data[:3]
    except Exception as e:
        debug_data['errors'].append(f"Sales sheet error: {str(e)}")
    
    return f"<pre>{json.dumps(debug_data, indent=2, ensure_ascii=False)}</pre>"

@app.route('/search_debug/<query>')
@login_required  
def search_debug(query):
    if session.get('username', '').lower() != 'admin':
        return redirect(url_for('home'))
        
    main_data = get_sheet_data('main')
    if not main_data:
        return "لا يمكن الوصول للبيانات"
    
    # البحث عن القيمة في جميع الأعمدة
    results = []
    for i, row in enumerate(main_data[:50]):  # فحص أول 50 صف فقط
        for j, cell in enumerate(row):
            if str(cell).strip() == str(query).strip():
                results.append({
                    'row_index': i,
                    'column_index': j, 
                    'value': cell,
                    'full_row': row[:7] if len(row) > 7 else row
                })
    
    return f"<pre>{json.dumps({'query': query, 'matches': results}, indent=2, ensure_ascii=False)}</pre>"

@app.route('/local_data_status')
@login_required
def local_data_status():
    if session.get('username', '').lower() != 'admin':
        return redirect(url_for('home'))
    
    status = {}
    for sheet_type in ['main', 'sales']:
        filename = f'local_data_{sheet_type}.pkl'
        if os.path.exists(filename):
            try:
                with open(filename, 'rb') as f:
                    saved_data = pickle.load(f)
                    status[sheet_type] = {
                        'exists': True,
                        'timestamp': saved_data['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
                        'rows_count': len(saved_data['data']),
                        'file_size': f"{os.path.getsize(filename) / 1024:.2f} KB"
                    }
            except Exception as e:
                status[sheet_type] = {
                    'exists': True,
                    'error': str(e)
                }
        else:
            status[sheet_type] = {'exists': False}
    
    return f"<pre>{json.dumps(status, indent=2, ensure_ascii=False)}</pre>"

@app.route('/refresh_local_data')
@login_required  
def refresh_local_data():
    if session.get('username', '').lower() != 'admin':
        return redirect(url_for('home'))
    
    try:
        # تحديث البيانات الرئيسية
        main_data = get_sheet_data('main', offline_mode=False)
        # تحديث بيانات المبيعات
        sales_data = get_sheet_data('sales', offline_mode=False)
        
        flash('تم تحديث البيانات المحلية بنجاح!', 'success')
    except Exception as e:
        flash(f'فشل في تحديث البيانات المحلية: {str(e)}', 'error')
    
    return redirect(url_for('home'))

# --- إعداد وتشغيل التطبيق ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            admin_user = User(username='admin')
            admin_user.set_password('adminpass')
            db.session.add(admin_user)
        if not User.query.filter_by(username='viewer').first():
            viewer_user = User(username='viewer')
            viewer_user.set_password('viewerpass')
            db.session.add(viewer_user)
        db.session.commit()
    app.run(host='0.0.0.0', port=5000, debug=True)