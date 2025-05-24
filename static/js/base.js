// Initialize Material Components
document.addEventListener('DOMContentLoaded', () => {
    // Initialize all MDC components
    mdc.autoInit();

    // Initialize drawer
    const drawer = mdc.drawer.MDCDrawer.attachTo(document.querySelector('.mdc-drawer'));
    const topAppBar = mdc.topAppBar.MDCTopAppBar.attachTo(document.querySelector('.mdc-top-app-bar'));
    
    // Connect drawer to top app bar
    topAppBar.setScrollTarget(document.querySelector('.mdc-top-app-bar--fixed-adjust'));
    topAppBar.listen('MDCTopAppBar:nav', () => {
        drawer.open = !drawer.open;
    });

    // Initialize snackbar
    const snackbar = mdc.snackbar.MDCSnackbar.attachTo(document.querySelector('.mdc-snackbar'));

    // Dark mode handling
    const themeToggle = document.getElementById('theme-toggle');
    const prefersDarkScheme = window.matchMedia('(prefers-color-scheme: dark)');
    
    // Check for saved theme preference or use system preference
    const currentTheme = localStorage.getItem('theme') || 
        (prefersDarkScheme.matches ? 'dark' : 'light');
    
    // Apply theme
    document.body.setAttribute('data-theme', currentTheme);
    updateThemeIcon(currentTheme);

    // Theme toggle click handler
    themeToggle.addEventListener('click', () => {
        const newTheme = document.body.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
        document.body.setAttribute('data-theme', newTheme);
        localStorage.setItem('theme', newTheme);
        updateThemeIcon(newTheme);
    });

    // Update theme icon based on current theme
    function updateThemeIcon(theme) {
        themeToggle.textContent = theme === 'dark' ? 'light_mode' : 'dark_mode';
    }

    // Global notification function
    window.showNotification = function(message, timeout = 4000) {
        snackbar.labelText = message;
        snackbar.timeoutMs = timeout;
        snackbar.open();
    };

    // Handle form submissions with loading states
    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', () => {
            const submitButton = form.querySelector('button[type="submit"]');
            if (submitButton) {
                submitButton.disabled = true;
                submitButton.innerHTML = '<span class="loading-spinner"></span> Przetwarzanie...';
            }
        });
    });

    // Handle file input previews
    document.querySelectorAll('input[type="file"]').forEach(input => {
        input.addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (!file) return;

            const previewContainer = document.querySelector('.receipt-preview-container');
            if (!previewContainer) return;

            // Clear previous preview
            previewContainer.innerHTML = '';

            // Create preview based on file type
            if (file.type.startsWith('image/')) {
                const img = document.createElement('img');
                img.className = 'receipt-preview';
                img.file = file;
                previewContainer.appendChild(img);

                const reader = new FileReader();
                reader.onload = (e) => img.src = e.target.result;
                reader.readAsDataURL(file);
            } else if (file.type === 'application/pdf') {
                // For PDFs, we'll show a placeholder
                const placeholder = document.createElement('div');
                placeholder.className = 'mdc-card';
                placeholder.innerHTML = `
                    <div class="mdc-card__primary-action">
                        <div class="mdc-card__media mdc-card__media--16-9">
                            <div class="mdc-card__media-content">
                                <span class="material-icons" style="font-size: 48px;">picture_as_pdf</span>
                            </div>
                        </div>
                        <div class="mdc-card__primary">
                            <h2 class="mdc-typography--headline6">${file.name}</h2>
                            <h3 class="mdc-typography--subtitle2">PDF Document</h3>
                        </div>
                    </div>
                `;
                previewContainer.appendChild(placeholder);
            }
        });
    });
}); 