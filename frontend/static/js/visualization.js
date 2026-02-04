// Enhanced privacy visualization functionality

document.addEventListener('DOMContentLoaded', function() {
    const toggleButton = document.getElementById('toggleSidebar');
    const showButton = document.getElementById('showPrivacyButton');
    const sidebar = document.getElementById('privacySidebar');
    
    // Toggle sidebar
    toggleButton.addEventListener('click', function() {
        sidebar.classList.add('collapsed');
        showButton.style.display = 'block';
    });
    
    // Show sidebar
    showButton.addEventListener('click', function() {
        sidebar.classList.remove('collapsed');
        showButton.style.display = 'none';
    });
    
    // Privacy report refresh button
    document.getElementById('refreshPrivacy')?.addEventListener('click', async function() {
        try {
            const response = await fetch('/api/chat/privacy-report');
            const data = await response.json();
            
            if (data.success) {
                alert(`Privacy Compliance Report:\n\nTotal Patients: ${data.report.total_patients}\nTotal Operations: ${data.report.total_operations}\nCloud Exposure: ${data.report.cloud_exposed_count}\nCompliant: ${data.report.privacy_compliant ? 'YES ✅' : 'NO ❌'}`);
            }
        } catch (error) {
            console.error('Error fetching privacy report:', error);
        }
    });
});

function updatePrivacyVisualization(workflowSteps, privacyDetails = null) {
    const privacySteps = document.getElementById('privacySteps');
    
    // Clear previous content
    privacySteps.innerHTML = '';
    
    // Add privacy indicator
    if (privacyDetails) {
        addPrivacyIndicator(privacySteps, privacyDetails);
        
        // Add PII transformation if detected
        if (privacyDetails.pii_detected) {
            addPIITransformation(privacySteps, privacyDetails);
        }
    }
    
    // Add workflow steps as timeline
    addWorkflowTimeline(privacySteps, workflowSteps);
}

function addPrivacyIndicator(container, privacyDetails) {
    const indicatorDiv = document.createElement('div');
    indicatorDiv.className = `privacy-indicator ${privacyDetails.cloud_safe ? 'safe' : 'warning'}`;
    
    const icon = privacyDetails.cloud_safe ? '✅' : '⚠️';
    const text = privacyDetails.cloud_safe 
        ? 'Privacy Protected - No PII sent to cloud'
        : 'Privacy Warning - Please review';
    
    indicatorDiv.innerHTML = `
        <span class="privacy-indicator-icon">${icon}</span>
        <span>${text}</span>
    `;
    
    container.appendChild(indicatorDiv);
}

function addPIITransformation(container, privacyDetails) {
    const transformDiv = document.createElement('div');
    transformDiv.className = 'privacy-transformation';
    
    let transformationsHtml = '<h4>🔐 PII Transformation</h4><div class="transformation-flow">';
    
    // Name transformation
    if (privacyDetails.original_contains.name && privacyDetails.original_contains.name !== 'N/A') {
        transformationsHtml += `
            <div class="transformation-item">
                <div class="original-pii">Name: ${escapeHtml(privacyDetails.original_contains.name)}</div>
                <div class="arrow">→</div>
                <div class="pseudonymized">UUID: ${escapeHtml(privacyDetails.pseudonymized_to?.substring(0, 8) + '...')}</div>
            </div>
        `;
    }
    
    // Age transformation
    if (privacyDetails.original_contains.age && privacyDetails.original_contains.age !== 'N/A') {
        const ageCategory = getAgeCategory(privacyDetails.original_contains.age);
        transformationsHtml += `
            <div class="transformation-item">
                <div class="original-pii">Age: ${privacyDetails.original_contains.age}</div>
                <div class="arrow">→</div>
                <div class="pseudonymized">Category: ${ageCategory}</div>
            </div>
        `;
    }
    
    // Gender (kept for medical relevance)
    if (privacyDetails.original_contains.gender && privacyDetails.original_contains.gender !== 'N/A') {
        transformationsHtml += `
            <div class="transformation-item">
                <div class="original-pii">Gender: ${privacyDetails.original_contains.gender}</div>
                <div class="arrow">→</div>
                <div class="pseudonymized">Preserved (medical relevance)</div>
            </div>
        `;
    }
    
    transformationsHtml += '</div>';
    transformDiv.innerHTML = transformationsHtml;
    
    container.appendChild(transformDiv);
}

function addWorkflowTimeline(container, workflowSteps) {
    const timelineDiv = document.createElement('div');
    timelineDiv.className = 'agent-reasoning';
    
    let html = '<h4>🔄 Processing Pipeline</h4><div class="timeline">';
    
    workflowSteps.forEach((step, index) => {
        html += `
            <div class="timeline-item">
                <div class="timeline-content">
                    <div class="timeline-title">Step ${index + 1}</div>
                    <div class="timeline-description">${escapeHtml(step)}</div>
                </div>
            </div>
        `;
    });
    
    html += '</div>';
    timelineDiv.innerHTML = html;
    
    container.appendChild(timelineDiv);
    
    // Animate timeline items
    const items = timelineDiv.querySelectorAll('.timeline-item');
    items.forEach((item, index) => {
        setTimeout(() => {
            item.style.opacity = '0';
            item.style.transform = 'translateX(-10px)';
            item.style.transition = 'all 0.3s ease-out';
            
            setTimeout(() => {
                item.style.opacity = '1';
                item.style.transform = 'translateX(0)';
            }, 50);
        }, index * 100);
    });
}

function getAgeCategory(age) {
    if (age < 18) return 'Pediatric';
    if (age < 65) return 'Adult';
    return 'Senior';
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Export for use in chat.js
window.updatePrivacyVisualization = updatePrivacyVisualization;
