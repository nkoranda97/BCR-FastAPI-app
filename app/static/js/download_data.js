function selectAll() {
    document.querySelectorAll('input[name="columns"]').forEach(checkbox => {
        checkbox.checked = true;
    });
}

function deselectAll() {
    document.querySelectorAll('input[name="columns"]').forEach(checkbox => {
        checkbox.checked = false;
    });
}

document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('downloadForm');
    if (!form) return;

    form.addEventListener('submit', function(e) {
        e.preventDefault();
        
        // Get selected columns
        const selectedColumns = Array.from(document.querySelectorAll('input[name="columns"]:checked'))
            .map(checkbox => checkbox.value);
        
        if (selectedColumns.length === 0) {
            alert('Please select at least one column to download');
            return;
        }
        
        // Create form data
        const formData = new FormData();
        formData.append('columns', selectedColumns.join(','));
        
        // Submit form
        fetch(this.action, {
            method: 'POST',
            body: formData
        })
        .then(response => response.blob())
        .then(blob => {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = document.getElementById('projectName').dataset.name + '_data.csv';
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            a.remove();
        })
        .catch(error => {
            console.error('Error:', error);
            alert('An error occurred while downloading the file');
        });
    });
}); 