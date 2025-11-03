/**
 * JavaScript for LiveClass admin form
 * Handles dynamic showing/hiding of days_of_week field based on recurrence_type
 */

document.addEventListener('DOMContentLoaded', function() {
    // Function to toggle days of week visibility
    function toggleDaysOfWeek(recurrenceType) {
        const daysOfWeekRow = document.querySelector('.field-days_of_week');
        if (daysOfWeekRow) {
            if (recurrenceType === 'weekly') {
                daysOfWeekRow.style.display = 'block';
                // Add required styling to indicate it's required
                const label = daysOfWeekRow.querySelector('label');
                if (label && !label.textContent.includes('*')) {
                    label.innerHTML += ' <span style="color: red;">*</span>';
                }
            } else {
                daysOfWeekRow.style.display = 'none';
                // Remove required indicator
                const label = daysOfWeekRow.querySelector('label');
                if (label) {
                    label.innerHTML = label.innerHTML.replace(' <span style="color: red;">*</span>', '');
                }
                // Clear selections when hidden
                const checkboxes = daysOfWeekRow.querySelectorAll('input[type="checkbox"]');
                checkboxes.forEach(checkbox => {
                    checkbox.checked = false;
                });
            }
        }
    }

    // Make function globally available
    window.toggleDaysOfWeek = toggleDaysOfWeek;

    // Initial setup
    const recurrenceSelect = document.querySelector('#id_recurrence_type');
    if (recurrenceSelect) {
        // Set initial state
        toggleDaysOfWeek(recurrenceSelect.value);
        
        // Add event listener for changes
        recurrenceSelect.addEventListener('change', function() {
            toggleDaysOfWeek(this.value);
        });
    }

    // Add some styling for better UX
    const style = document.createElement('style');
    style.textContent = `
        .field-days_of_week {
            border-left: 3px solid var(--primary);
            padding-left: 10px;
            margin-left: 5px;
            background-color: var(--darkened-bg);
            padding: 10px;
            border-radius: 4px;
        }
        
        .field-days_of_week .checkbox-row {
            display: inline-block;
            margin-right: 15px;
            margin-bottom: 5px;
            min-width: 100px;
        }
        
        .field-days_of_week label {
            font-weight: 600;
            color: var(--body-fg);
        }
        
        .field-days_of_week input[type="checkbox"] {
            margin-right: 5px;
        }
    `;
    document.head.appendChild(style);

    // Improve the layout of checkboxes
    const daysOfWeekField = document.querySelector('.field-days_of_week ul');
    if (daysOfWeekField) {
        daysOfWeekField.style.listStyle = 'none';
        daysOfWeekField.style.padding = '0';
        daysOfWeekField.style.display = 'grid';
        daysOfWeekField.style.gridTemplateColumns = 'repeat(auto-fit, minmax(120px, 1fr))';
        daysOfWeekField.style.gap = '10px';
        
        const listItems = daysOfWeekField.querySelectorAll('li');
        listItems.forEach(li => {
            li.classList.add('checkbox-row');
        });
    }
});