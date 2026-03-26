// upload.js - Manejo interactivo de carga

document.addEventListener('DOMContentLoaded', function() {
    initFileUpload();
});

function initFileUpload() {
    // Seleccioar todos los inputs de archivo
    const fileInputs = document.querySelectorAll('input[type="file"]');
    
    fileInputs.forEach(input => {
        const dropArea = input.previousElementSibling;
        const bandaCard = input.closest('.banda-card');
        
        dropArea.addEventListener('click', () => input.click());
        input.addEventListener('change', (e) => handleFileSelect(e.target.files[0], bandaCard, input));
        
        dropArea.addEventListener('dragover', (e) => { e.preventDefault(); dropArea.classList.add('dragover'); });
        dropArea.addEventListener('dragleave', () => dropArea.classList.remove('dragover'));
        
        dropArea.addEventListener('drop', (e) => {
            e.preventDefault();
            dropArea.classList.remove('dragover');
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                input.files = files;
                handleFileSelect(files[0], bandaCard, input);
            }
        });
    });
    
    // Validar antes de enviar
    const form = document.querySelector('.form-carga');
    if (form) {
        form.addEventListener('submit', validateForm);
    }
}


function handleFileSelect(file, bandaCard, input) {
    if (!file) return;
    
    // Lógica de validación solo para bandas
    const validExtensions = ['tif', 'tiff', 'jp2'];
    const fileName = file.name.toLowerCase();
    const extension = fileName.split('.').pop();
    
    if (!validExtensions.includes(extension)) {
        showError(bandaCard, `Formato no válido. Use ${validExtensions.join(', ')}`);
        input.value = ''; 
        return;
    }
    
    // Límite de 500MB para bandas
    const maxSize = 500 * 1024 * 1024; 
    if (file.size > maxSize) {
        showError(bandaCard, `Archivo muy grande (máx 500MB)`);
        input.value = '';
        return;
    }
    
    showFileInfo(bandaCard, file);
    updateSubmitButton();
}

function showFileInfo(bandaCard, file) {
    const existingError = bandaCard.querySelector('.error-message');
    if (existingError) existingError.remove();
    
    const dropArea = bandaCard.querySelector('.drop-area');
    if (dropArea) dropArea.style.display = 'none';
    
    let fileInfo = bandaCard.querySelector('.file-info');
    if (!fileInfo) {
        fileInfo = document.createElement('div');
        fileInfo.className = 'file-info';
        bandaCard.appendChild(fileInfo);
    }
    
    const sizeInMB = (file.size / (1024 * 1024)).toFixed(1);
    const fileName = file.name.length > 25 ? file.name.substring(0, 22) + '...' : file.name;
    
    fileInfo.innerHTML = `
        <strong>✓ ${fileName}</strong><br>
        <small>${sizeInMB} MB</small>
    `;
    fileInfo.classList.add('visible');
    fileInfo.style.display = 'block';
    bandaCard.style.borderLeft = '4px solid #4caf50';
    bandaCard.style.background = '#f1f8f4';
}

function showError(bandaCard, message) {
    const existingInfo = bandaCard.querySelector('.file-info');
    if (existingInfo) existingInfo.remove();
    
    let errorDiv = bandaCard.querySelector('.error-message');
    if (!errorDiv) {
        errorDiv = document.createElement('div');
        errorDiv.className = 'error-message';
        bandaCard.appendChild(errorDiv);
    }
    
    errorDiv.textContent = `❌ ${message}`;
    errorDiv.style.cssText = `
        color: #f44336; background: #ffebee; padding: 10px;
        border-radius: 5px; margin-top: 10px; font-size: 0.9em;
    `;
    bandaCard.style.borderLeft = '4px solid #f44336';
}

function updateSubmitButton() {
    const bandInputs = document.querySelectorAll('input[name^="band_"]');
    const submitButton = document.querySelector('#submit-bands-btn');

    if (!submitButton) return;

    let filesSelected = 0;
    bandInputs.forEach(input => {
        if (input.files.length > 0) filesSelected++;
    });

    if (filesSelected === bandInputs.length) {
        submitButton.disabled = false;
        submitButton.textContent = `✓ Cargar Bandas`;
        submitButton.style.background = 'linear-gradient(135deg, #26a69a, #00796b)';
    } else {
        submitButton.disabled = true;
        submitButton.textContent = `Se necesitan las 5 bandas`;
        submitButton.style.background = '#bbb';
    }
}

function validateForm(e) {
    const bandInputs = document.querySelectorAll('input[name^="band_"]');
    let bandFilesCount = 0;

    bandInputs.forEach(input => {
        if (input.files.length > 0) bandFilesCount++;
    });

    if (bandFilesCount < bandInputs.length) {
        e.preventDefault();
        alert('Por favor, selecciona las 5 bandas espectrales antes de continuar.');
        return false;
    }

    const submitButton = document.querySelector('#submit-bands-btn');
    if (submitButton) {
        submitButton.disabled = true;
        submitButton.innerHTML = '<span class="spinner" style="width: 20px; height: 20px; display: inline-block; margin-right: 10px;"></span> Subiendo archivos...';
    }

    return true;
}