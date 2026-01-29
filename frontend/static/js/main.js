// Main utility functions

function navigateTo(path) {
    window.location.href = path;
}

function showElement(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        element.style.display = 'block';
    }
}

function hideElement(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        element.style.display = 'none';
    }
}

function showLoading() {
    hideElement('resultSection');
    hideElement('errorSection');
    showElement('loadingState');
}

function hideLoading() {
    hideElement('loadingState');
}

function showSuccess(detailsHtml) {
    hideLoading();
    const resultDetails = document.getElementById('resultDetails');
    if (resultDetails) {
        resultDetails.innerHTML = detailsHtml;
    }
    showElement('resultSection');
}

function showError(errorMessage) {
    hideLoading();
    const errorElement = document.getElementById('errorMessage');
    if (errorElement) {
        errorElement.textContent = errorMessage;
    }
    showElement('errorSection');
}

function resetForm() {
    // Hide result sections
    hideElement('resultSection');
    hideElement('errorSection');
    hideElement('loadingState');
    
    // Reset form
    const forms = document.querySelectorAll('form');
    forms.forEach(form => form.reset());
    
    // Scroll to top
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function formatDateTime(isoString) {
    const date = new Date(isoString);
    return date.toLocaleString('en-US', {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

async function makeApiCall(endpoint, method, data = null) {
    const options = {
        method: method,
        headers: {
            'Content-Type': 'application/json'
        }
    };
    
    if (data) {
        options.body = JSON.stringify(data);
    }
    
    try {
        const response = await fetch(endpoint, options);
        const responseData = await response.json();
        
        if (!response.ok) {
            throw new Error(responseData.detail || 'API request failed');
        }
        
        return responseData;
    } catch (error) {
        console.error('API Error:', error);
        throw error;
    }
}

// Form validation helper
function validateForm(formElement) {
    const inputs = formElement.querySelectorAll('[required]');
    let isValid = true;
    
    inputs.forEach(input => {
        if (!input.value.trim()) {
            isValid = false;
            input.classList.add('error');
        } else {
            input.classList.remove('error');
        }
    });
    
    return isValid;
}

// Add input validation styling
document.addEventListener('DOMContentLoaded', function() {
    const inputs = document.querySelectorAll('input, select, textarea');
    
    inputs.forEach(input => {
        input.addEventListener('blur', function() {
            if (this.hasAttribute('required') && !this.value.trim()) {
                this.classList.add('error');
            } else {
                this.classList.remove('error');
            }
        });
        
        input.addEventListener('input', function() {
            this.classList.remove('error');
        });
    });
});
