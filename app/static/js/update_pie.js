// Function to update pie chart when a bar is clicked
function update_pie(bar_source, pie_source, pie_renderer) {
    // Get the selected bar's value
    const selected = bar_source.selected.indices[0];
    if (selected === undefined) {
        return;
    }
    
    // Get the value of the selected bar
    const value = bar_source.data.value[selected];
    
    // Update pie chart data
    pie_source.data = {
        value: [value, 100 - value],
        label: ['Selected', 'Other']
    };
    
    // Trigger change event to update the pie chart
    pie_source.change.emit();
}

// Function to reset pie chart to original data
function reset_pie(original_data, pie_source) {
    pie_source.data = original_data;
    pie_source.change.emit();
}

// Function to handle bar click events
function handle_bar_click(bar_source, pie_source, pie_renderer, original_data) {
    // Add click event listener to bar chart
    bar_source.selected.on_change('indices', function() {
        if (bar_source.selected.indices.length > 0) {
            update_pie(bar_source, pie_source, pie_renderer);
        } else {
            reset_pie(original_data, pie_source);
        }
    });
} 