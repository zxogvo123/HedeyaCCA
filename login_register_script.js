document.addEventListener('DOMContentLoaded', () => {
    // دالة لتبديل رؤية كلمة المرور
    function setupPasswordToggle(passwordFieldId, toggleButtonId) {
        const passwordField = document.getElementById(passwordFieldId);
        const toggleButton = document.getElementById(toggleButtonId);

        if (passwordField && toggleButton) {
            toggleButton.addEventListener('click', () => {
                const type = passwordField.getAttribute('type') === 'password' ? 'text' : 'password';
                passwordField.setAttribute('type', type);

                // تبديل أيقونة العين
                toggleButton.querySelector('i').classList.toggle('fa-eye');
                toggleButton.querySelector('i').classList.toggle('fa-eye-slash');
            });
        }
    }

    // إعداد زر إظهار/إخفاء كلمة المرور لصفحة تسجيل الدخول
    setupPasswordToggle('password', 'togglePassword');

    // إعداد أزرار إظهار/إخفاء كلمة المرور لصفحة التسجيل
    setupPasswordToggle('password', 'toggleRegisterPassword');
    setupPasswordToggle('confirm_password', 'toggleConfirmPassword');


    // يمكن إضافة المزيد من JavaScript هنا لصفحات تسجيل الدخول/التسجيل إذا لزم الأمر
    // مثال: تحقق بسيط من تطابق كلمات المرور في صفحة التسجيل (قبل الإرسال)
    const registerForm = document.querySelector('.auth-form'); // هذا يجب أن يكون نموذج التسجيل
    if (registerForm && window.location.pathname.includes('/register')) { // تأكد أننا في صفحة التسجيل
        registerForm.addEventListener('submit', (event) => {
            const password = document.getElementById('password');
            const confirmPassword = document.getElementById('confirm_password');

            if (password && confirmPassword && password.value !== confirmPassword.value) {
                alert('كلمة المرور وتأكيد كلمة المرور غير متطابقين!');
                // أو يمكن عرض رسالة خطأ بشكل أجمل في الواجهة
                event.preventDefault(); // منع إرسال النموذج
            }
            // يمكن إضافة المزيد من التحققات هنا (طول كلمة المرور، تعقيدها)
        });
    }

});