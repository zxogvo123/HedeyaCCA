# create_db.py

import os # **هذا السطر ضروري جداً**
from main import app, db, User # استيراد التطبيق، قاعدة البيانات، ونموذج المستخدم من ملف main.py

print("Starting database creation script...")

# يجب تشغيل الأوامر داخل سياق التطبيق
with app.app_context():
    # حذف قاعدة البيانات القديمة إذا كانت موجودة (لضمان بدء نظيف)
    # هذا يضمن أنك تبدأ دائماً بقاعدة بيانات جديدة وفارغة عند تشغيل هذا السكريبت
    if os.path.exists('site.db'):
        os.remove('site.db')
        print("Existing site.db removed for a fresh start.")
    else:
        print("No existing site.db found. Creating a new one.")

    # إنشاء جميع الجداول المعرفة في النماذج (مثل User)
    db.create_all()
    print("Database tables created successfully (site.db).")

    # إضافة المستخدمين الافتراضيين (admin و viewer) فقط إذا لم يكونوا موجودين
    # (هذا سيتم في قاعدة البيانات الجديدة الفارغة بعد db.create_all())
    if not User.query.filter_by(username='admin').first():
        admin_user = User(username='admin')
        admin_user.set_password('adminpass') # كلمة المرور الافتراضية للادمن
        db.session.add(admin_user)
        db.session.commit()
        print("Default admin user 'admin' created with password 'adminpass'.")
    else:
        print("Admin user already exists (should not happen if site.db was removed).")

    if not User.query.filter_by(username='viewer').first():
        viewer_user = User(username='viewer')
        viewer_user.set_password('viewerpass') # كلمة المرور الافتراضية للفيور
        db.session.add(viewer_user)
        db.session.commit()
        print("Default viewer user 'viewer' created with password 'viewerpass'.")
    else:
        print("Viewer user already exists (should not happen if site.db was removed).")

print("Database setup script finished.")