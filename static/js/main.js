(function () {
    'use strict';

    const root = document.documentElement;
    const toggle = document.getElementById('themeToggle');
    const navToggle = document.getElementById('navToggle');
    const mainNav = document.getElementById('mainNav');

    function getPreferredTheme() {
        const stored = localStorage.getItem('tsut-theme');
        if (stored === 'dark' || stored === 'light') return stored;
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }

    function setTheme(theme) {
        root.setAttribute('data-theme', theme);
        localStorage.setItem('tsut-theme', theme);
    }

    setTheme(getPreferredTheme());

    if (toggle) {
        toggle.addEventListener('click', function () {
            const current = root.getAttribute('data-theme') || 'light';
            setTheme(current === 'dark' ? 'light' : 'dark');
        });
    }

    if (navToggle && mainNav) {
        navToggle.addEventListener('click', function () {
            mainNav.classList.toggle('open');
        });
    }

    // Close nav on outside click (mobile)
    document.addEventListener('click', function (e) {
        if (mainNav && mainNav.classList.contains('open') &&
            !mainNav.contains(e.target) &&
            e.target !== navToggle) {
            mainNav.classList.remove('open');
        }
    });
})();
