// crop.js - Manejo interactivo de recorte

document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('preview-container-crop');
    const image = document.getElementById('preview-image');
    const selectionBox = document.getElementById('selection-box');
    const cropButton = document.getElementById('crop-button');
    const loadingMessage = document.getElementById('loading-message');

    // Variables de estado
    let isDrawing = false;
    let startX, startY;
    let coords = {}; // Almacena las coordenadas de la selección

    // Función para actualizar el texto del botón y el estado de habilitación
    function updateCropButton(width, height) {
        let isValid = width > 0 && height > 0 && width <= maxDim && height <= maxDim;
            
        let message = `${width}x${height} píxeles`;
        if (width > maxDim || height > maxDim) {
            message = `❌ ${message} (Máx: ${maxDim}x${maxDim})`;
        }

        cropButton.textContent = `Aplicar Recorte y Continuar (${message})`;
        cropButton.disabled = !isValid;
    }

    // --- MANEJO DEL RATÓN (SIMULACIÓN DEL RECTANGLE SELECTOR) ---

    container.addEventListener('mousedown', (e) => {
        e.preventDefault();
        isDrawing = true;
        // Coordenadas iniciales relativas al contenedor
        startX = e.offsetX; 
        startY = e.offsetY;

        // Inicializar el recuadro de selección
        selectionBox.style.left = `${startX}px`;
        selectionBox.style.top = `${startY}px`;
        selectionBox.style.width = '0';
        selectionBox.style.height = '0';
        selectionBox.style.display = 'block';

        updateCropButton(0, 0);
    });

    container.addEventListener('mousemove', (e) => {
        if (!isDrawing) return;

        // Coordenadas actuales relativas al contenedor
        const currentX = e.offsetX;
        const currentY = e.offsetY;

        // Calcular ancho y alto del recuadro
        const width = Math.abs(currentX - startX);
        const height = Math.abs(currentY - startY);
            
        // Posición (esquina superior izquierda del recuadro)
        const left = Math.min(startX, currentX);
        const top = Math.min(startY, currentY);

        // Actualizar el estilo del recuadro de selección
        selectionBox.style.left = `${left}px`;
        selectionBox.style.top = `${top}px`;
        selectionBox.style.width = `${width}px`;
        selectionBox.style.height = `${height}px`;

        // Calcular las coordenadas escaladas (píxeles originales)
        const x1_original = Math.floor(Math.min(startX, currentX) * scaleFactor);
        const y1_original = Math.floor(Math.min(startY, currentY) * scaleFactor);
        const x2_original = Math.floor(Math.max(startX, currentX) * scaleFactor);
        const y2_original = Math.floor(Math.max(startY, currentY) * scaleFactor);
            
        const finalWidth = x2_original - x1_original;
        const finalHeight = y2_original - y1_original;
            
        updateCropButton(finalWidth, finalHeight);
    });

    container.addEventListener('mouseup', (e) => {
        if (!isDrawing) return;
        isDrawing = false;

        const endX = e.offsetX;
        const endY = e.offsetY;

        // Calcular las coordenadas finales, asegurando que x1 < x2 y y1 < y2
        const x1_scaled = Math.min(startX, endX);
        const y1_scaled = Math.min(startY, endY);
        const x2_scaled = Math.max(startX, endX);
        const y2_scaled = Math.max(startY, endY);

        // Calcular las coordenadas escaladas (píxeles originales)
        coords = {
            x1: Math.floor(x1_scaled * scaleFactor), // Columna inicial
            y1: Math.floor(y1_scaled * scaleFactor), // Fila inicial
            x2: Math.floor(x2_scaled * scaleFactor), // Columna final
            y2: Math.floor(y2_scaled * scaleFactor)  // Fila final
        };
            
        const finalWidth = coords.x2 - coords.x1;
        const finalHeight = coords.y2 - coords.y1;

        updateCropButton(finalWidth, finalHeight);
    });

    // --- ENVÍO DE DATOS A FLASK ---

    cropButton.addEventListener('click', () => {
        if (cropButton.disabled) {
            alert('El área seleccionada no es válida o excede los límites.');
            return;
        }

        // Mostrar mensaje de carga y deshabilitar botón
        cropButton.style.display = 'none';
        loadingMessage.style.display = 'block';

        fetch(cropUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(coords)
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                window.location.href = data.redirect; // Redirige a /process
            } else {
                alert('Error al aplicar el recorte: ' + data.error);
                cropButton.style.display = 'block';
                loadingMessage.style.display = 'none';
            }
        })
        .catch(error => {
            alert('Error de conexión: ' + error);
            cropButton.style.display = 'block';
            loadingMessage.style.display = 'none';
        });
    });
});