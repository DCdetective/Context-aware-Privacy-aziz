// Follow-Up Page JavaScript

document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('followupForm');
    
    if (form) {
        form.addEventListener('submit', handleFollowupSubmit);
    }
});

async function handleFollowupSubmit(event) {
    event.preventDefault();
    
    const formData = {
        patient_name: document.getElementById('patientName').value
    };
    
    showLoading();
    
    try {
        const result = await apiCall('/api/followups/schedule', 'POST', formData);
        
        const details = formatResultDetails({
            patient_name: result.patient_name || formData.patient_name,
            follow_up: result.follow_up || result.message || 'Your follow-up appointment has been scheduled based on your medical history.',
            message: result.note || ''
        });
        
        showSuccess(details);
    } catch (error) {
        showError(error.message);
    }
}

// Override resetForm for this page
function resetForm() {
    const form = document.getElementById('followupForm');
    if (form) {
        form.reset();
    }
    
    // Hide result sections
    document.getElementById('loadingState').style.display = 'none';
    document.getElementById('resultSection').style.display = 'none';
    document.getElementById('errorSection').style.display = 'none';
    
    // Show form again
    document.querySelector('.medical-form').style.display = 'block';
}
