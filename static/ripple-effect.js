
// تأثيرات تفاعلية متقدمة للموقع

document.addEventListener('DOMContentLoaded', function() {
    
    // تأثير الريبل للأزرار
    function createRipple(event) {
        const button = event.currentTarget;
        const circle = document.createElement('span');
        const diameter = Math.max(button.clientWidth, button.clientHeight);
        const radius = diameter / 2;

        circle.style.width = circle.style.height = `${diameter}px`;
        circle.style.left = `${event.clientX - button.offsetLeft - radius}px`;
        circle.style.top = `${event.clientY - button.offsetTop - radius}px`;
        circle.classList.add('ripple');

        const ripple = button.getElementsByClassName('ripple')[0];
        if (ripple) {
            ripple.remove();
        }

        button.appendChild(circle);
    }

    // إضافة تأثير الريبل لجميع الأزرار
    const buttons = document.querySelectorAll('.ripple-effect');
    buttons.forEach(button => {
        button.addEventListener('click', createRipple);
    });

    // تأثير الظهور عند التمرير
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };

    const observer = new IntersectionObserver(function(entries) {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
            }
        });
    }, observerOptions);

    // مراقبة العناصر للظهور التدريجي
    const fadeElements = document.querySelectorAll('.fade-in-scroll');
    fadeElements.forEach(element => {
        observer.observe(element);
    });

    // تأثير التوهج للبطاقات عند المرور عليها
    const cards = document.querySelectorAll('.invoice-card, .stat-card');
    cards.forEach(card => {
        card.addEventListener('mouseenter', function() {
            this.style.boxShadow = '0 30px 60px rgba(31, 38, 135, 0.4), 0 0 50px rgba(102, 126, 234, 0.6)';
        });
        
        card.addEventListener('mouseleave', function() {
            this.style.boxShadow = '';
        });
    });

    // تأثير البريق للعناصر الجديدة
    function addSparkleEffect() {
        const sparkleElements = document.querySelectorAll('.sparkle-effect');
        sparkleElements.forEach(element => {
            if (!element.querySelector('.sparkle')) {
                const sparkle = document.createElement('span');
                sparkle.classList.add('sparkle');
                sparkle.innerHTML = '✨';
                sparkle.style.cssText = `
                    position: absolute;
                    top: ${Math.random() * 80 + 10}%;
                    right: ${Math.random() * 80 + 10}%;
                    font-size: 1.2rem;
                    opacity: 0;
                    animation: sparkle 3s ease-in-out infinite;
                    animation-delay: ${Math.random() * 2}s;
                    pointer-events: none;
                    z-index: 10;
                `;
                element.appendChild(sparkle);
            }
        });
    }

    // تشغيل تأثير البريق
    addSparkleEffect();

    // تأثير تغيير الألوان للروابط
    const navLinks = document.querySelectorAll('.navbar-links a');
    const colors = ['#667eea', '#764ba2', '#f093fb', '#f5576c', '#4facfe', '#00f2fe'];
    
    navLinks.forEach((link, index) => {
        link.addEventListener('mouseenter', function() {
            this.style.background = colors[index % colors.length];
            this.style.transform = 'scale(1.1) translateY(-2px)';
        });
        
        link.addEventListener('mouseleave', function() {
            this.style.background = '';
            this.style.transform = '';
        });
    });

    // تأثير النبض للأيقونات
    const pulseIcons = document.querySelectorAll('.pulse-effect');
    pulseIcons.forEach(icon => {
        setInterval(() => {
            icon.style.transform = 'scale(1.2)';
            setTimeout(() => {
                icon.style.transform = 'scale(1)';
            }, 150);
        }, 3000);
    });

    // إضافة كلاسات للرسوم المتحركة عند تحميل الصفحة
    setTimeout(() => {
        document.body.classList.add('loaded');
        
        // تطبيق التأثيرات على العناصر الجديدة
        const newElements = document.querySelectorAll('.zoom-in');
        newElements.forEach((element, index) => {
            setTimeout(() => {
                element.style.animation = 'zoomIn 0.5s ease-out forwards';
            }, index * 100);
        });
    }, 100);

    // تحسين التمرير السلس
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });

    // تأثير الجاذبية للماوس
    document.addEventListener('mousemove', function(e) {
        const cards = document.querySelectorAll('.floating-card');
        cards.forEach(card => {
            const rect = card.getBoundingClientRect();
            const x = e.clientX - rect.left - rect.width / 2;
            const y = e.clientY - rect.top - rect.height / 2;
            const distance = Math.sqrt(x * x + y * y);
            
            if (distance < 200) {
                const force = (200 - distance) / 200;
                const moveX = x * force * 0.1;
                const moveY = y * force * 0.1;
                
                card.style.transform = `translate(${moveX}px, ${moveY}px) rotateX(${moveY * 0.5}deg) rotateY(${moveX * 0.5}deg)`;
            } else {
                card.style.transform = '';
            }
        });
    });
});

// تأثيرات إضافية للتحميل
window.addEventListener('load', function() {
    // إضافة تأثير توهج للعنوان الرئيسي
    const mainTitle = document.querySelector('.header h1');
    if (mainTitle) {
        mainTitle.classList.add('glow-text', 'gradient-text');
    }
    
    // تفعيل التأثيرات المتقدمة
    document.body.classList.add('effects-loaded');
});
