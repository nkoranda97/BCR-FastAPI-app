// Function to create a bar chart
function createBarChart(canvasId, data, title, chain = 'HC') {
    const ctx = document.getElementById(canvasId).getContext('2d');
    const colors = {
        HC: {
            background: 'rgba(54, 162, 235, 0.5)',  // Blue
            border: 'rgba(54, 162, 235, 1)'
        },
        LC: {
            background: 'rgba(255, 99, 132, 0.5)',  // Red
            border: 'rgba(255, 99, 132, 1)'
        }
    };
    
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.labels,
            datasets: [{
                label: 'Count',
                data: data.values,
                backgroundColor: colors[chain].background,
                borderColor: colors[chain].border,
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            plugins: {
                title: {
                    display: true,
                    text: title
                },
                legend: {
                    display: false
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Count'
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: 'Category'
                    }
                }
            }
        }
    });
}

// Function to create a pie chart
function createPieChart(canvasId, data, title) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    new Chart(ctx, {
        type: 'pie',
        data: {
            labels: data.labels,
            datasets: [{
                data: data.values,
                backgroundColor: [
                    'rgba(255, 99, 132, 0.5)',
                    'rgba(54, 162, 235, 0.5)',
                    'rgba(255, 206, 86, 0.5)',
                    'rgba(75, 192, 192, 0.5)',
                    'rgba(153, 102, 255, 0.5)',
                    'rgba(255, 159, 64, 0.5)'
                ],
                borderColor: [
                    'rgba(255, 99, 132, 1)',
                    'rgba(54, 162, 235, 1)',
                    'rgba(255, 206, 86, 1)',
                    'rgba(75, 192, 192, 1)',
                    'rgba(153, 102, 255, 1)',
                    'rgba(255, 159, 64, 1)'
                ],
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            plugins: {
                title: {
                    display: true,
                    text: title
                },
                legend: {
                    position: 'right'
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = context.raw || 0;
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = ((value / total) * 100).toFixed(1);
                            return `${label}: ${value} (${percentage}%)`;
                        }
                    }
                }
            }
        }
    });
}

// Function to initialize all charts
function initializeCharts(chartData) {
    // Create bar charts
    createBarChart('vCallChart', chartData.v_call, 'V Gene Usage');
    createBarChart('cCallChart', chartData.c_call, 'C Gene Usage');
    createBarChart('jCallChart', chartData.j_call, 'J Gene Usage');
    createBarChart('isotypeChart', chartData.isotype, 'Isotype Distribution');

    // Create pie charts
    createPieChart('vCallPieChart', chartData.v_call, 'V Gene Distribution');
    createPieChart('cCallPieChart', chartData.c_call, 'C Gene Distribution');
    createPieChart('jCallPieChart', chartData.j_call, 'J Gene Distribution');
    createPieChart('isotypePieChart', chartData.isotype, 'Isotype Distribution');
} 