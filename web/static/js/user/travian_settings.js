// Handle the password field behavior
document.addEventListener('DOMContentLoaded', function() {
    const passwordField = document.getElementById('travian_password');
    
    // Store the original password value
    const originalValue = passwordField.value;
    
    // Clear the actual value but keep it in a data attribute
    if (originalValue === "********") {
        passwordField.value = '';
        passwordField.setAttribute('data-has-password', 'true');
        passwordField.setAttribute('placeholder', '********');
    }
    
    // When the form is submitted, if the field is empty and had a password,
    // set the value back to ******** so the backend knows to use the existing password
    const form = passwordField.closest('form');
    form.addEventListener('submit', function(event) {
        // Show loading message
        const submitButton = form.querySelector('button[type="submit"]');
        if (submitButton) {
            submitButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Saving...';
            submitButton.disabled = true;
        }
        
        if (passwordField.value === '' && passwordField.getAttribute('data-has-password') === 'true') {
            passwordField.value = '********';
        }
    });
});

// Add validation feedback for form fields
document.addEventListener('DOMContentLoaded', function() {
    const form = document.querySelector('form');
    const usernameField = document.getElementById('travian_username');
    const passwordField = document.getElementById('travian_password');
    const serverField = document.getElementById('travian_server');
    
    form.addEventListener('submit', function(event) {
        let isValid = true;
        
        // Validate username
        if (!usernameField.value.trim()) {
            usernameField.classList.add('is-invalid');
            isValid = false;
        } else {
            usernameField.classList.remove('is-invalid');
            usernameField.classList.add('is-valid');
        }
        
        // Validate password - only if it's not using the stored password
        if (passwordField.getAttribute('data-has-password') !== 'true' && !passwordField.value) {
            passwordField.classList.add('is-invalid');
            isValid = false;
        } else {
            passwordField.classList.remove('is-invalid');
            passwordField.classList.add('is-valid');
        }
        
        // Validate server URL
        if (serverField.value.trim() && !serverField.value.trim().startsWith('http')) {
            // Add http:// prefix if missing
            serverField.value = 'https://' + serverField.value.trim();
        }
        
        // Prevent form submission if validation fails
        if (!isValid) {
            event.preventDefault();
        }
    });
});

// Initialize tooltips
document.addEventListener('DOMContentLoaded', function() {
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
});

// Handle disconnect confirmation
document.addEventListener('DOMContentLoaded', function() {
    // Handle disconnect confirmation
    const confirmDisconnectBtn = document.getElementById('confirmDisconnect');
    if (confirmDisconnectBtn) {
        confirmDisconnectBtn.addEventListener('click', function() {
            document.getElementById('disconnectForm').submit();
        });
    }
});