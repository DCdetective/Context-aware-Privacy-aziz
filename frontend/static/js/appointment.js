// Appointment scheduling functionality

document.addEventListener('DOMContentLoaded', function() {
    const appointmentForm = document.getElementById('appointmentForm');
    
    if (appointmentForm) {
        appointmentForm.addEventListener('submit', handleAppointmentSubmit);
    }
});

async function handleAppointmentSubmit(event) {
    event.preventDefault();
    
    console.log('='.repeat(60));
    console.log('FRONTEND: Appointment submission started');
    console.log('='.repeat(60));
    
    const form = event.target;
    
    // Validate form
    if (!validateForm(form)) {
        showError('Please fill in all required fields');
        return;
    }
    
    // Get form data
    const formData = {
        patient_name: document.getElementById('patientName').value.trim(),
        age: parseInt(document.getElementById('age').value),
        gender: document.getElementById('gender').value,
        symptoms: document.getElementById('symptoms').value.trim()
    };
    
    console.log('Form data collected:', {
        patient_name: formData.patient_name,
        age: formData.age,
        gender: formData.gender
    });
    
    // Disable form and show loading
    setFormDisabled(form, true);
    showLoading();
    
    try {
        console.log('Sending request to /api/appointments/schedule');
        
        // Make API call
        const response = await makeApiCall(
            '/api/appointments/schedule',
            'POST',
            formData
        );
        
        console.log('Response received:', response);
        
        if (response.success) {
            // Display success with details
            const detailsHtml = createAppointmentDetailsHtml(response);
            showSuccess(detailsHtml);
            
            console.log('Appointment scheduled successfully');
            console.log('='.repeat(60));
        } else {
            throw new Error(response.message || 'Failed to schedule appointment');
        }
        
    } catch (error) {
        console.error('Error scheduling appointment:', error);
        showError(error.message || 'An error occurred while scheduling the appointment. Please try again.');
        setFormDisabled(form, false);
    }
}

function createAppointmentDetailsHtml(response) {
    return `
        <div class="detail-grid">
            <div class="detail-item">
                <span class="detail-label">Patient Name:</span>
                <span class="detail-value">${response.patient_name}</span>
            </div>
            <div class="detail-item">
                <span class="detail-label">Appointment Time:</span>
                <span class="detail-value">${formatDateTime(response.appointment_time)}</span>
            </div>
            <div class="detail-item">
                <span class="detail-label">Consultation Duration:</span>
                <span class="detail-value">${response.consultation_duration} minutes</span>
            </div>
            <div class="detail-item">
                <span class="detail-label">Urgency Level:</span>
                <span class="detail-value urgency-${response.urgency_level}">${response.urgency_level}</span>
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
            <strong>🔒 Privacy Note:</strong> Your appointment was scheduled using privacy-preserving 
            pseudonymization. Cloud agents only saw UUID: ${response.patient_uuid.substring(0, 8)}...
        </div>
    `;
}

function setFormDisabled(form, disabled) {
    const inputs = form.querySelectorAll('input, select, textarea, button');
    inputs.forEach(input => {
        input.disabled = disabled;
    });
}
