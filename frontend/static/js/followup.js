// Follow-up scheduling functionality

document.addEventListener('DOMContentLoaded', function() {
    const followupForm = document.getElementById('followupForm');
    
    if (followupForm) {
        followupForm.addEventListener('submit', handleFollowUpSubmit);
    }
});

async function handleFollowUpSubmit(event) {
    event.preventDefault();
    
    console.log('='.repeat(60));
    console.log('FRONTEND: Follow-up submission started');
    console.log('='.repeat(60));
    
    const form = event.target;
    
    // Validate form
    if (!validateForm(form)) {
        showError('Please fill in all required fields');
        return;
    }
    
    // Get form data
    const formData = {
        patient_name: document.getElementById('patientName').value.trim()
    };
    
    console.log('Form data collected:', formData);
    
    // Disable form and show loading
    setFormDisabled(form, true);
    showLoading();
    
    try {
        console.log('Sending request to /api/followups/schedule');
        
        // Make API call
        const response = await makeApiCall(
            '/api/followups/schedule',
            'POST',
            formData
        );
        
        console.log('Response received:', response);
        
        if (response.success) {
            // Display success with details
            const detailsHtml = createFollowUpDetailsHtml(response);
            showSuccess(detailsHtml);
            
            console.log('Follow-up scheduled successfully');
            console.log('='.repeat(60));
        } else {
            throw new Error(response.message || 'Failed to schedule follow-up');
        }
        
    } catch (error) {
        console.error('Error scheduling follow-up:', error);
        showError(error.message || 'An error occurred while scheduling the follow-up. Please try again.');
        setFormDisabled(form, false);
    }
}

function createFollowUpDetailsHtml(response) {
    return `
        <div class="detail-grid">
            <div class="detail-item">
                <span class="detail-label">Patient Name:</span>
                <span class="detail-value">${response.patient_name}</span>
            </div>
            <div class="detail-item">
                <span class="detail-label">Follow-Up Time:</span>
                <span class="detail-value">${formatDateTime(response.followup_time)}</span>
            </div>
            <div class="detail-item">
                <span class="detail-label">Previous Visits:</span>
                <span class="detail-value">${response.previous_visits || 0} visits</span>
            </div>
            <div class="detail-item">
                <span class="detail-label">Continuity Maintained:</span>
                <span class="detail-value">${response.continuity_maintained ? '✅ Yes' : '❌ No'}</span>
            </div>
            <div class="detail-item">
                <span class="detail-label">Patient UUID:</span>
                <span class="detail-value uuid">${response.patient_uuid}</span>
            </div>
            <div class="detail-item">
                <span class="detail-label">Record ID:</span>
                <span class="detail-value uuid">${response.record_id}</span>
            </div>
        </div>
        <div class="privacy-notice">
            <strong>🔒 Privacy Note:</strong> Your follow-up was scheduled using stored semantic context. 
            Cloud agents only saw UUID: ${response.patient_uuid.substring(0, 8)}...
        </div>
    `;
}

function setFormDisabled(form, disabled) {
    const inputs = form.querySelectorAll('input, select, textarea, button');
    inputs.forEach(input => {
        input.disabled = disabled;
    });
}
