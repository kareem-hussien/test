// Improved JavaScript for admin/logs.html
document.addEventListener('DOMContentLoaded', function() {
    // Handle log detail modal with improved error handling
    const logDetailModal = document.getElementById('logDetailModal');
    if (logDetailModal) {
        logDetailModal.addEventListener('show.bs.modal', function(event) {
            const button = event.relatedTarget;
            const logId = button.getAttribute('data-log-id');
            
            // Clear previous data and show loading state
            document.getElementById('modalLogId').textContent = 'Loading...';
            document.getElementById('modalLogTimestamp').textContent = 'Loading...';
            document.getElementById('modalLogUser').textContent = 'Loading...';
            document.getElementById('modalLogDetails').textContent = 'Loading...';
            document.getElementById('modalLogStackTrace').textContent = 'Loading...';
            
            // Fetch log details from API with proper error handling
            fetch(`/admin/api/logs/${logId}`, {
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                }
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! Status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.success && data.log) {
                    const log = data.log;
                    document.getElementById('modalLogId').textContent = log.id || logId;
                    document.getElementById('modalLogTimestamp').textContent = log.timestamp || 'N/A';
                    document.getElementById('modalLogUser').textContent = log.user || 'system';
                    
                    // Handle message and details differently to avoid undefined
                    const details = log.details || log.message || 'No details available';
                    document.getElementById('modalLogDetails').textContent = details;
                    
                    // Handle stack trace with fallback
                    document.getElementById('modalLogStackTrace').textContent = 
                        log.stack_trace || 'No stack trace available';
                    
                    // Add category and IP information if available
                    if (log.category) {
                        const categoryElement = document.createElement('div');
                        categoryElement.innerHTML = `<strong>Category:</strong> ${log.category}`;
                        document.getElementById('modalLogDetails').parentNode.appendChild(categoryElement);
                    }
                    
                    if (log.ip_address) {
                        const ipElement = document.createElement('div');
                        ipElement.innerHTML = `<strong>IP Address:</strong> ${log.ip_address}`;
                        document.getElementById('modalLogDetails').parentNode.appendChild(ipElement);
                    }
                } else {
                    console.error('Invalid response format:', data);
                    document.getElementById('modalLogDetails').textContent = 
                        'Error loading log details: Invalid response format';
                }
            })
            .catch(error => {
                console.error('Error fetching log details:', error);
                document.getElementById('modalLogDetails').textContent = 
                    `Error loading log details: ${error.message}`;
            });
        });
    }
    
    // Toggle custom date fields in download modal
    const downloadDateRange = document.getElementById('downloadDateRange');
    const customDateFields = document.getElementById('customDateFields');
    
    if (downloadDateRange && customDateFields) {
        downloadDateRange.addEventListener('change', function() {
            if (this.value === 'custom') {
                customDateFields.style.display = 'flex';
            } else {
                customDateFields.style.display = 'none';
            }
        });
        
        // Set initial state
        if (downloadDateRange.value === 'custom') {
            customDateFields.style.display = 'flex';
        }
    }
    
    // Properly initialize the timeline chart with error handling
    initializeLogTimelineChart();
    
    // Initialize tooltips for all interactive elements
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
});

// Function to initialize the log timeline chart
function initializeLogTimelineChart() {
    const logTimelineCtx = document.getElementById('logTimelineChart');
    if (!logTimelineCtx) {
        console.warn('Log timeline chart element not found');
        return;
    }
    
    try {
        // Get chart data from embedded data attributes or global variables
        let chartData;
        
        if (window.logChartData) {
            chartData = window.logChartData;
        } else if (logTimelineCtx.dataset.labels) {
            // Try to get data from data attributes
            chartData = {
                labels: JSON.parse(logTimelineCtx.dataset.labels || '[]'),
                info_data: JSON.parse(logTimelineCtx.dataset.infoData || '[]'),
                warning_data: JSON.parse(logTimelineCtx.dataset.warningData || '[]'),
                error_data: JSON.parse(logTimelineCtx.dataset.errorData || '[]')
            };
        } else {
            // Fallback to empty data
            console.warn('No chart data found, using empty datasets');
            chartData = {
                labels: [],
                info_data: [],
                warning_data: [],
                error_data: []
            };
        }
        
        // Create chart with appropriate error handling
        new Chart(logTimelineCtx, {
            type: 'line',
            data: {
                labels: chartData.labels,
                datasets: [
                    {
                        label: 'INFO',
                        data: chartData.info_data,
                        borderColor: 'rgba(13, 110, 253, 1)',
                        backgroundColor: 'rgba(13, 110, 253, 0.1)',
                        pointBackgroundColor: 'rgba(13, 110, 253, 1)',
                        tension: 0.4,
                        fill: true
                    },
                    {
                        label: 'WARNING',
                        data: chartData.warning_data,
                        borderColor: 'rgba(255, 193, 7, 1)',
                        backgroundColor: 'rgba(255, 193, 7, 0.1)',
                        pointBackgroundColor: 'rgba(255, 193, 7, 1)',
                        tension: 0.4,
                        fill: true
                    },
                    {
                        label: 'ERROR',
                        data: chartData.error_data,
                        borderColor: 'rgba(220, 53, 69, 1)',
                        backgroundColor: 'rgba(220, 53, 69, 0.1)',
                        pointBackgroundColor: 'rgba(220, 53, 69, 1)',
                        tension: 0.4,
                        fill: true
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Log Count'
                        },
                        ticks: {
                            precision: 0
                        }
                    },
                    x: {
                        title: {
                            display: true,
                            text: 'Time of Day'
                        }
                    }
                },
                plugins: {
                    tooltip: {
                        mode: 'index',
                        intersect: false
                    },
                    legend: {
                        position: 'top',
                    }
                }
            }
        });
    } catch (error) {
        console.error('Error initializing log chart:', error);
        
        // Show error message in the chart container
        const errorMessage = document.createElement('div');
        errorMessage.className = 'alert alert-danger mt-3';
        errorMessage.textContent = 'Failed to load log chart: ' + error.message;
        
        // Insert error message after the canvas
        if (logTimelineCtx.parentNode) {
            logTimelineCtx.parentNode.appendChild(errorMessage);
        }
    }
}