// Summary Page JavaScript

document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('summaryForm');
    
    if (form) {
        form.addEventListener('submit', handleSummarySubmit);
    }
});

async function handleSummarySubmit(event) {
    event.preventDefault();
    
    const formData = {
        patient_name: document.getElementById('patientName').value
    };
    
    showLoading();
    
    try {
        const result = await apiCall('/api/summaries/generate', 'POST', formData);
        
        const details = formatResultDetails({
            patient_name: result.patient_name || formData.patient_name,
            summary: result.summary || result.message || 'Medical summary has been generated successfully.',
            message: result.note || ''
        });
        
        showSuccess(details);
    } catch (error) {
        showError(error.message);
    }
}

// Override resetForm for this page
function resetForm() {
    const form = document.getElementById('summaryForm');
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
