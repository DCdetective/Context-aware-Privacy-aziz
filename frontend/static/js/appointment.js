// Appointment Page JavaScript

document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('appointmentForm');
    
    if (form) {
        form.addEventListener('submit', handleAppointmentSubmit);
    }
});

async function handleAppointmentSubmit(event) {
    event.preventDefault();
    
    const formData = {
        patient_name: document.getElementById('patientName').value,
        age: parseInt(document.getElementById('age').value),
        gender: document.getElementById('gender').value,
        symptoms: document.getElementById('symptoms').value
    };
    
    showLoading();
    
    try {
        const result = await apiCall('/api/appointments/schedule', 'POST', formData);
        
        const details = formatResultDetails({
            patient_name: result.patient_name || formData.patient_name,
            appointment_details: result.appointment_details || result.message || 'Your appointment has been scheduled successfully.',
            message: result.note || ''
        });
        
        showSuccess(details);
    } catch (error) {
        showError(error.message);
    }
}

// Override resetForm for this page
function resetForm() {
    const form = document.getElementById('appointmentForm');
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
