// MedShield Frontend JavaScript - Navigation and Common Functions

// Navigation function
function navigateTo(path) {
    window.location.href = path;
}

// Reset form function (to be overridden in page-specific JS)
function resetForm() {
    const form = document.querySelector('form');
    if (form) {
        form.reset();
    }
    
    // Hide result sections
    const loadingState = document.getElementById('loadingState');
    const resultSection = document.getElementById('resultSection');
    const errorSection = document.getElementById('errorSection');
    
    if (loadingState) loadingState.style.display = 'none';
    if (resultSection) resultSection.style.display = 'none';
    if (errorSection) errorSection.style.display = 'none';
    
    // Show form again
    const formElement = document.querySelector('.medical-form');
    if (formElement) formElement.style.display = 'block';
}

// Show loading state
function showLoading() {
    const form = document.querySelector('.medical-form');
    const loadingState = document.getElementById('loadingState');
    
    if (form) form.style.display = 'none';
    if (loadingState) loadingState.style.display = 'block';
}

// Show success result
function showSuccess(details) {
    const loadingState = document.getElementById('loadingState');
    const resultSection = document.getElementById('resultSection');
    const resultDetails = document.getElementById('resultDetails');
    
    if (loadingState) loadingState.style.display = 'none';
    if (resultSection) resultSection.style.display = 'block';
    
    if (resultDetails && details) {
        resultDetails.innerHTML = details;
    }
}

// Show error
function showError(message) {
    const loadingState = document.getElementById('loadingState');
    const errorSection = document.getElementById('errorSection');
    const errorMessage = document.getElementById('errorMessage');
    
    if (loadingState) loadingState.style.display = 'none';
    if (errorSection) errorSection.style.display = 'block';
    
    if (errorMessage) {
        errorMessage.textContent = message || 'An unexpected error occurred. Please try again.';
    }
}

// Format result details as HTML
function formatResultDetails(data) {
    let html = '';
    
    if (data.patient_name) {
        html += `<p><strong>Patient:</strong> ${data.patient_name}</p>`;
    }
    
    if (data.appointment_details) {
        html += `<p><strong>Details:</strong> ${data.appointment_details}</p>`;
    }
    
    if (data.follow_up) {
        html += `<p><strong>Follow-Up:</strong> ${data.follow_up}</p>`;
    }
    
    if (data.summary) {
        html += `<p><strong>Summary:</strong></p>`;
        html += `<p>${data.summary}</p>`;
    }
    
    if (data.message) {
        html += `<p>${data.message}</p>`;
    }
    
    return html;
}

// API call helper
async function apiCall(endpoint, method, data) {
    try {
        const options = {
            method: method,
            headers: {
                'Content-Type': 'application/json',
            }
        };
        
        if (data) {
            options.body = JSON.stringify(data);
        }
        
        const response = await fetch(endpoint, options);
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
        }
        
        return await response.json();
    } catch (error) {
        console.error('API call error:', error);
        throw error;
    }
}

// Console log for debugging
console.log('MedShield frontend loaded successfully');
