// Privacy visualization functionality

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
});

function updatePrivacyVisualization(workflowSteps) {
    const privacySteps = document.getElementById('privacySteps');
    
    // Clear previous steps
    privacySteps.innerHTML = '';
    
    // Add new steps
    workflowSteps.forEach((step, index) => {
        const stepDiv = document.createElement('div');
        stepDiv.className = 'privacy-step';
        stepDiv.innerHTML = `
            <strong>Step ${index + 1}:</strong><br>
            ${escapeHtml(step)}
        `;
        privacySteps.appendChild(stepDiv);
        
        // Animate in
        setTimeout(() => {
            stepDiv.style.opacity = '1';
        }, index * 100);
    });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
