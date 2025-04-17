 // Initialize charts when the DOM is loaded
 document.addEventListener('DOMContentLoaded', function() {
    // Initialize charts
    initActivityTypeChart();
    initActivityStatusChart();
    
    // Refresh logs button
    document.getElementById('refreshLogs').addEventListener('click', function() {
        location.reload();
    });
    
    // Export logs button
    document.getElementById('exportLogs').addEventListener('click', function() {
        $('#exportModal').modal('show');
    });
    
    // Handle custom date range toggle
    document.getElementById('exportDateRange').addEventListener('change', function() {
        if (this.value === 'custom') {
            document.getElementById('customDateRange').classList.remove('d-none');
        } else {
            document.getElementById('customDateRange').classList.add('d-none');
        }
    });
    
    // Handle export confirmation
    document.getElementById('confirmExport').addEventListener('click', function() {
        exportLogs();
    });
});

// Initialize activity type chart
function initActivityTypeChart() {
    const ctx = document.getElementById('activityTypeChart');
    
    // Get activity type statistics
    // This would typically come from the backend
    const activityTypes = {
        'Auto-Farm': {{ stats.auto_farm|default(0) }},
        'Troop Training': {{ stats.training|default(0) }},
        'Login': {{ stats.system|default(0) }},
        'Village': {{ stats.system|default(0) }} {# This is an approximation #},
        'Profile': {{ stats.system|default(0) }} {# This is an approximation #},
        'System': {{ stats.system|default(0) }}
    };
    
    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: Object.keys(activityTypes),
            datasets: [{
                data: Object.values(activityTypes),
                backgroundColor: [
                    '#4e73df', // Primary
                    '#1cc88a', // Success
                    '#36b9cc', // Info
                    '#f6c23e', // Warning
                    '#e74a3b', // Danger
                    '#858796'  // Secondary
                ],
                hoverOffset: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                }
            },
            cutout: '70%'
        }
    });
}

// Initialize activity status chart
function initActivityStatusChart() {
    const ctx = document.getElementById('activityStatusChart');
    
    // Get activity status statistics
    // This would typically come from the backend
    const activityStatuses = {
        'Success': {{ stats.success|default(0) }},
        'Warning': {{ stats.warning|default(0) }},
        'Error': {{ stats.error|default(0) }},
        'Info': {{ stats.system|default(0) - stats.success|default(0) - stats.warning|default(0) - stats.error|default(0) }}
    };
    
    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: Object.keys(activityStatuses),
            datasets: [{
                data: Object.values(activityStatuses),
                backgroundColor: [
                    '#1cc88a', // Success
                    '#f6c23e', // Warning
                    '#e74a3b', // Danger
                    '#36b9cc'  // Info
                ],
                hoverOffset: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                }
            },
            cutout: '70%'
        }
    });
}

// Export logs function
function exportLogs() {
    // Get form values
    const format = document.getElementById('exportFormat').value;
    const dateRange = document.getElementById('exportDateRange').value;
    const includeFilters = document.getElementById('includeFilters').checked;
    
    // Get current filters if needed
    const type = includeFilters ? "{{ filters.type }}" : "";
    const status = includeFilters ? "{{ filters.status }}" : "";
    const village = includeFilters ? "{{ filters.village }}" : "";
    
    // Get custom date range if selected
    let startDate = "";
    let endDate = "";
    
    if (dateRange === 'custom') {
        startDate = document.getElementById('startDate').value;
        endDate = document.getElementById('endDate').value;
        
        if (!startDate || !endDate) {
            alert('Please select both start and end dates for custom range');
            return;
        }
    }
    
    // Construct URL with query parameters
    let url = `/api/user/activity-logs/export?format=${format}&dateRange=${dateRange}&includeFilters=${includeFilters}`;
    
    if (includeFilters) {
        if (type) url += `&type=${type}`;
        if (status) url += `&status=${status}`;
        if (village) url += `&village=${village}`;
    }
    
    if (dateRange === 'custom') {
        url += `&startDate=${startDate}&endDate=${endDate}`;
    }
    
    // Download the file
    window.location.href = url;
    
    // Close the modal
    $('#exportModal').modal('hide');
}