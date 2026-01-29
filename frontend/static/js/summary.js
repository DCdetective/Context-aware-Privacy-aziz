// Medical summary generation functionality

document.addEventListener('DOMContentLoaded', function() {
    const summaryForm = document.getElementById('summaryForm');
    
    if (summaryForm) {
        summaryForm.addEventListener('submit', handleSummarySubmit);
    }
});

async function handleSummarySubmit(event) {
    event.preventDefault();
    
    console.log('='.repeat(60));
    console.log('FRONTEND: Summary generation started');
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
        console.log('Sending request to /api/summaries/generate');
        
        // Make API call
        const response = await makeApiCall(
            '/api/summaries/generate',
            'POST',
            formData
        );
        
        console.log('Response received:', response);
        
        if (response.success) {
            // Display success with details
            const detailsHtml = createSummaryDetailsHtml(response);
            showSuccess(detailsHtml);
            
            console.log('Summary generated successfully');
            console.log('='.repeat(60));
        } else {
            throw new Error(response.message || 'Failed to generate summary');
        }
        
    } catch (error) {
        console.error('Error generating summary:', error);
        showError(error.message || 'An error occurred while generating the summary. Please try again.');
        setFormDisabled(form, false);
    }
}

function createSummaryDetailsHtml(response) {
    const summary = response.summary || {};
    
    let recordTypesHtml = '';
    if (summary.record_types && summary.record_types.length > 0) {
        recordTypesHtml = summary.record_types.map(type => 
            `<span class="badge">${type}</span>`
        ).join(' ');
    } else {
        recordTypesHtml = '<span class="badge">No records</span>';
    }
    
    return `
        <div class="detail-grid">
            <div class="detail-item">
                <span class="detail-label">Patient Name:</span>
                <span class="detail-value">${response.patient_name}</span>
            </div>
            <div class="detail-item">
                <span class="detail-label">Total Visits:</span>
                <span class="detail-value">${summary.total_visits || 0}</span>
            </div>
            <div class="detail-item full-width">
                <span class="detail-label">Record Types:</span>
                <div class="detail-value">${recordTypesHtml}</div>
            </div>
            <div class="detail-item full-width">
                <span class="detail-label">Summary:</span>
                <div class="detail-value summary-text">${summary.summary_text || 'No summary available'}</div>
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
            <strong>🔒 Privacy Note:</strong> This summary was generated using cloud reasoning on 
            pseudonymized data. UUID used: ${response.patient_uuid.substring(0, 8)}...
        </div>
    `;
}

function setFormDisabled(form, disabled) {
    const inputs = form.querySelectorAll('input, select, textarea, button');
    inputs.forEach(input => {
        input.disabled = disabled;
    });
}
