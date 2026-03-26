// static/js/process.js

$(document).ready(function() {
    let debounceTimer;

    // Función para enviar la solicitud de previsualización
    function fetchPreview() {
        const data = {
            min_size_initial: parseInt($('#min_size_initial').val()),
            min_size_final: parseInt($('#min_size_final').val()),
            closing_width: parseInt($('#closing_width').val()),
            closing_height: parseInt($('#closing_height').val()),
            closing_iterations: parseInt($('#closing_iterations').val()),
            metodo_deteccion: $('#metodo_deteccion').val()
        };

        $('#loading-spinner').show();
        // GIF transparente base64 para evitar parpadeos feos
        const pixelVacio = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7";

        $.ajax({
            url: '/preview_cleaning', 
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify(data),
            success: function(response) {
                $('#preview-before').attr('src', response.imagen_antes ? 'data:image/png;base64,' + response.imagen_antes : pixelVacio);
                $('#preview-after').attr('src', response.imagen_despues ? 'data:image/png;base64,' + response.imagen_despues : pixelVacio);
            },
            error: function(xhr, status, error) {
                console.error("Error fetching preview:", error);
            },
            complete: function() {
                $('#loading-spinner').hide(); 
            }
        });
    }

    // Listeners para actualizar valores y lanzar preview
    $('#min_size_initial, #min_size_final, #closing_width, #closing_height, #closing_iterations, #metodo_deteccion').on('input change', function() {
        // Actualizar el número que se ve al lado del slider
        $(`#${this.id}_val`).text($(this).val());

        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(fetchPreview, 500); 
    });

    // Cargar inicial
    fetchPreview(); 
});